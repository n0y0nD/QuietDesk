"""QuietDesk agent: Muse Spark (Meta Model API) with tool calling.

Run:  python agent.py          -> chat with the agent in the terminal
"""
import json
import os
from datetime import datetime

from dotenv import load_dotenv
from openai import OpenAI

from tools import TOOL_SPECS, run_tool

load_dotenv()

MODEL = os.getenv("QUIETDESK_MODEL", "muse-spark-1.3")
client = OpenAI(base_url="https://api.meta.ai/v1", api_key=os.environ["MODEL_API_KEY"])


def instructions() -> str:
    now = datetime.now().strftime("%A %Y-%m-%d %H:%M")
    return (
        "You are QuietDesk, a calm voice assistant on a desk device that helps the user "
        "stay focused while their phone is out of reach. Replies are spoken aloud, so keep "
        "them short (1-3 sentences), no markdown or lists. Use the tools to save notes and "
        "create or read reminders, read missed phone notifications, and draft replies. "
        "You can never send a message yourself: drafts wait on the screen until the user "
        "approves them, so say the draft is ready for review. "
        "Reply in the user's language (English or Hinglish). "
        f"Current local time: {now}."
    )


class Agent:
    def __init__(self):
        self.last_response_id = None  # lets the API remember the conversation

    def ask(self, user_text: str) -> str:
        self.tool_log = []  # tool calls made for this question, shown on the web page
        resp = client.responses.create(
            model=MODEL,
            instructions=instructions(),
            input=user_text,
            tools=TOOL_SPECS,
            previous_response_id=self.last_response_id,
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
        return resp.output_text


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
