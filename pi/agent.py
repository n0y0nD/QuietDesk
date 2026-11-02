"""QuietDesk agent: Muse Spark (Meta Model API) with tool calling.

Run:  python agent.py          -> chat with the agent in the terminal
"""
import json
import os
import re
import time
from datetime import datetime

from dotenv import load_dotenv
from openai import APIStatusError, OpenAI

from tools import TOOL_SPECS, run_tool

load_dotenv()

MODEL = os.getenv("QUIETDESK_MODEL", "muse-spark-1.3")
client = OpenAI(base_url="https://api.meta.ai/v1", api_key=os.environ["MODEL_API_KEY"])


def instructions() -> str:
    now = datetime.now().strftime("%A %Y-%m-%d %H:%M")
    return (
        "You are QuietDesk, a calm voice assistant on a desk device that helps the user "
        "stay focused while their phone is out of reach. Replies are spoken aloud by a simple "
        "voice, so answer in ONE short sentence (two only if really needed), plain words, "
        "no markdown, lists, emoji or abbreviations. "
        "Start every reply with a mood tag that sets the tone of the voice: [happy] for good news, "
        "greetings and things done; [calm] for gentle, sad or worrying news, or when the user sounds "
        "stressed; [serious] for urgent warnings and deadlines; [neutral] for everything else. "
        "The tag is removed before the user sees or hears the reply. Use the tools to save notes and "
        "create or read reminders, read missed phone notifications, and draft replies. "
        "You can never send a message yourself: drafts wait on the screen until the user "
        "approves them, so say the draft is ready for review. "
        "Reply in the user's language (English or Hinglish). "
        f"Current local time: {now}."
    )


class Agent:
    def __init__(self):
        self.last_response_id = None  # lets the API remember the conversation
        self.mood = "neutral"  # tone Muse Spark picked for the last reply

    def ask(self, user_text: str) -> str:
        self.tool_log = []  # tool calls made for this question, shown on the web page
        try:
            resp = client.responses.create(
                model=MODEL,
                instructions=instructions(),
                input=user_text,
                tools=TOOL_SPECS,
                previous_response_id=self.last_response_id,
            )
        except APIStatusError as e:
            if e.status_code < 500:
                raise
            # Server-side hiccup (e.g. 503): try once more as a fresh conversation, so a demo keeps going.
            print(f"  API {e.status_code}, retrying without conversation history")
            time.sleep(1)
            resp = client.responses.create(
                model=MODEL, instructions=instructions(), input=user_text, tools=TOOL_SPECS
            )
        for _ in range(5):  # at most 5 rounds of tool calls
            calls = [item for item in resp.output if item.type == "function_call"]
            if not calls:
                break
            outputs = []
            for call in calls:
                args = json.loads(call.arguments or "{}")
                result = run_tool(call.name, args)
                print(f"  [tool] {call.name}({args}) -> {result}")
                self.tool_log.append({"name": call.name, "args": args})
                outputs.append(
                    {"type": "function_call_output", "call_id": call.call_id, "output": json.dumps(result)}
                )
            resp = client.responses.create(
                model=MODEL,
                instructions=instructions(),
                input=outputs,
                tools=TOOL_SPECS,
                previous_response_id=resp.id,
            )
        self.last_response_id = resp.id
        self.mood, reply = split_mood(resp.output_text)
        return reply


MOODS = ("happy", "calm", "serious", "neutral")


def split_mood(text: str) -> tuple:
    """Take the [mood] tag Muse Spark puts at the start of a reply. Returns (mood, reply)."""
    m = re.match(r"\s*\[(\w+)\]\s*", text or "")
    if m and m.group(1).lower() in MOODS:
        return m.group(1).lower(), text[m.end():].strip()
    return "neutral", re.sub(r"\[\w+\]\s*", "", text or "").strip()


if __name__ == "__main__":
    agent = Agent()
    print(f"QuietDesk agent ({MODEL}). Type 'exit' to quit.")
    while True:
        try:
            text = input("\nYou: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if text.lower() in {"exit", "quit"}:
            break
        if text:
            print("QuietDesk:", agent.ask(text))
