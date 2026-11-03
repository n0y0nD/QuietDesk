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

# How long Muse Spark thinks before answering. Desk tasks are short, and on a voice device speed
# matters most: "minimal" answered in about 1.5 s in our tests vs about 7 s with the default.
EFFORT = os.getenv("QUIETDESK_EFFORT", "minimal")


def create(**kwargs):
    """Responses API call with QuietDesk's reasoning effort."""
    return client.responses.create(reasoning={"effort": EFFORT}, **kwargs)


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


KEEP_TURNS = 6  # how many past questions (with their tool calls) QuietDesk remembers


class Agent:
    """Muse Spark with tools. The conversation is kept here on the Pi and sent with each call:
    in our tests that was 2-10x faster and more reliable than the API's previous_response_id."""

    def __init__(self):
        self.turns = []  # each turn = list of input items: user message, tool calls, tool results, reply
        self.mood = "neutral"  # tone Muse Spark picked for the last reply
        self.tool_log = []

    def reset(self) -> None:
        self.turns = []

    def _call(self, items: list):
        history = [item for turn in self.turns[-KEEP_TURNS:] for item in turn]
        kwargs = dict(model=MODEL, instructions=instructions(), input=history + items, tools=TOOL_SPECS)
        try:
            return create(**kwargs)
        except APIStatusError as e:
            if e.status_code < 500:
                raise
            print(f"  API {e.status_code}, retrying once")  # server hiccup: keep the demo going
            time.sleep(0.5)
            return create(**kwargs)

    def ask(self, user_text: str) -> str:
        self.tool_log = []  # tool calls made for this question, shown on the web page
        turn = [{"role": "user", "content": user_text}]
        resp = self._call(turn)
        for _ in range(5):  # at most 5 rounds of tool calls
            calls = [item for item in resp.output if item.type == "function_call"]
            if not calls:
                break
            for call in calls:
                args = json.loads(call.arguments or "{}")
                result = run_tool(call.name, args)
                print(f"  [tool] {call.name}({args}) -> {result}")
                self.tool_log.append({"name": call.name, "args": args})
                turn.append({"type": "function_call", "call_id": call.call_id,
                             "name": call.name, "arguments": call.arguments or "{}"})
                turn.append({"type": "function_call_output", "call_id": call.call_id, "output": json.dumps(result)})
            resp = self._call(turn)
        text = resp.output_text
        turn.append({"role": "assistant", "content": text})
        self.turns.append(turn)
        self.mood, reply = split_mood(text)
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
