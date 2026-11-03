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

import focus
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
        "You are Lumi, the calm, warm voice of QuietDesk, a desk device that helps the user "
        "stay focused while their phone is out of reach. If asked your name, you are Lumi. "
        "Replies are spoken aloud by a simple "
        "voice, so answer in ONE short sentence (two only if really needed), plain words, "
        "no markdown, lists, emoji or abbreviations. "
        "Start every reply with a mood tag that sets the tone of the voice: [happy] for good news, "
        "greetings and things done; [calm] for gentle, sad or worrying news, or when the user sounds "
        "stressed; [serious] for urgent warnings and deadlines; [neutral] for everything else. "
        "The tag is removed before the user sees or hears the reply. Use the tools to save notes and "
        "create or read reminders, read missed phone notifications, and draft replies. "
        "Replying to a message always takes two steps. Step one: call draft_reply, then say who it is for "
        "and read the draft word for word, and ask if you should send it, e.g. 'Draft for Rahul: I am busy, "
        "will call later. Should I send it?'. Step two, only in your next turn and only if the user clearly "
        "says yes: call send_reply. If they want changes, draft again and ask again. Never send in the same "
        "turn you drafted. If it is unclear which message the user means, ask (name the senders). "
        "Prefer messages from the real phone over the simulated phone. "
        "When you start a focus session, also ask whether to tell people who message that the user is busy "
        "(auto-reply); call set_auto_reply with on=true only if the user asked for it or says yes. "
        "Once it is on, say you will let people know when they message (nobody has been told yet). "
        "When asked how the day or focus went, use get_focus_stats and say it in hours and minutes. "
        "Reply in the user's language (English or Hinglish), always in Latin letters, never in Devanagari, "
        "because the voice can only read Latin letters (the user may be shown to you in Devanagari). "
        "Say times in 12-hour form like 4:30 PM. "
        f"Current local time: {now}. {focus_line()}"
    )


def focus_line() -> str:
    f = focus.status()
    if not f["active"]:
        return "No focus session is running."
    return f"A {f['minutes']} minute focus session is running, {f['left_seconds'] // 60} minutes left (ends {f['ends_at']})."


KEEP_TURNS = 6  # how many past questions (with their tool calls) QuietDesk remembers

# Sending a message by voice needs a clear yes from the user, checked here in code (not left to the model).
YES_EN = re.compile(r"\b(yes|yeah|yep|yup|haan?|haa|han|haanji|ha|ji|send|sent|bhej\w*|ok|okay|sure|go ahead|kar do|do it)\b", re.I)
NO_EN = re.compile(r"\b(no|nope|nahi|nahin|nhi|mat|don'?t|cancel|wait|ruko|stop|change|badal\w*)\b", re.I)
# Muse Voice Transcribe may write Hindi in Devanagari ("हाँ, भेज दो"). Short words need spaces around them,
# so "हा" inside "कहाँ" is not read as a yes.
_EDGE_L, _EDGE_R = r"(?:^|[\s,.!?।])", r"(?=$|[\s,.!?।])"
YES_HI = re.compile(_EDGE_L + r"(हाँ|हां|हा|हाँजी|जी|ओके)" + _EDGE_R + r"|भेज|ठीक है|बता द|कर द")
NO_HI = re.compile(r"नहीं|नही|रुको|रुकिए|बदल|" + _EDGE_L + r"(मत|ना)" + _EDGE_R)


class _Either:
    """Matches if either the English (Latin letters) or the Hindi (Devanagari) pattern matches."""

    def __init__(self, *patterns):
        self.patterns = patterns

    def search(self, text):
        return next((m for p in self.patterns if (m := p.search(text or ""))), None)


YES = _Either(YES_EN, YES_HI)
NO = _Either(NO_EN, NO_HI)
# Auto-replies go on only if the user's own words say yes or ask for them.
ASKED_AUTO = _Either(YES_EN, YES_HI, re.compile(r"\b(busy|auto.?repl\w*|tell (them|people|everyone)|reply|bata\w*)\b", re.I),
                     re.compile(r"बिज़ी|बिजी|व्यस्त|बता|रिप्लाई"))


class Agent:
    """Muse Spark with tools. The conversation is kept here on the Pi and sent with each call:
    in our tests that was 2-10x faster and more reliable than the API's previous_response_id.

    `send` is a function(notification_id, text) that really sends a reply; without it QuietDesk can only draft."""

    def __init__(self, send=None):
        self.turns = []  # each turn = list of input items: user message, tool calls, tool results, reply
        self.mood = "neutral"  # tone Muse Spark picked for the last reply
        self.tool_log = []
        self.send = send
        self.offered = {}  # drafts read to the user in the last reply: notification id -> draft text

    def reset(self) -> None:
        self.turns = []
        self.offered = {}

    def _send_reply(self, args: dict, user_text: str) -> dict:
        """send_reply, guarded: the draft must have been read out in the previous reply, and the
        user's newest message must say yes (and not no). Otherwise nothing is sent."""
        nid = args.get("notification_id")
        draft = self.offered.get(nid)
        if draft is None:
            return {"ok": False, "error": "Not sent, and that is expected: a reply can only be sent in the turn "
                    "after the user heard the draft. Do not call send_reply or draft_reply again now. Just read the "
                    "draft to the user word for word and ask 'Should I send it?'."}
        if not YES.search(user_text) or NO.search(user_text):
            return {"ok": False, "error": "Not sent: the user did not clearly say yes. Ask again."}
        if self.send is None:
            return {"ok": False, "error": "Sending is only available in the web console."}
        try:
            self.send(nid, draft)
        except Exception as e:
            return {"ok": False, "error": f"Not sent: {e}"}
        del self.offered[nid]
        return {"ok": True, "status": f"sent: {draft}"}

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
        drafted = {}  # drafts made in this turn; they can only be sent after the user hears them
        resp = self._call(turn)
        for _ in range(5):  # at most 5 rounds of tool calls
            calls = [item for item in resp.output if item.type == "function_call"]
            if not calls:
                break
            for call in calls:
                args = json.loads(call.arguments or "{}")
                if call.name == "send_reply":
                    result = self._send_reply(args, user_text)
                elif call.name == "set_auto_reply" and args.get("on") and (
                        not ASKED_AUTO.search(user_text) or NO.search(user_text)):
                    # Turning auto-replies on needs the user's own yes or request, checked here in code.
                    result = {"ok": False, "error": "Not turned on: ask the user first; turn it on only after they say yes."}
                else:
                    result = run_tool(call.name, args)
                    if call.name == "draft_reply" and result.get("ok"):
                        drafted[args.get("notification_id")] = args.get("text", "")
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
        # Only drafts this reply actually read out can be sent on the next "yes".
        self.offered = {nid: d for nid, d in drafted.items() if d and _norm(d) in _norm(reply)}
        return reply


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


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
