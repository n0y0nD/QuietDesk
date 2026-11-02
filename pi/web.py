"""QuietDesk web console: voice + notification demo, served from the Pi.

The laptop browser acts as the mic and speaker (the Pi has no mic yet). All AI runs here on the Pi:
Muse Voice Transcribe for speech-to-text, Muse Spark for answers and triage, espeak-ng for the voice.

Run on the Pi:   .venv/bin/python web.py
On the laptop:   ssh -L 8000:localhost:8000 admin@raspberrypi5.local
Then open:       http://localhost:8000
(The server only listens on the Pi itself; the SSH tunnel is what lets the laptop in,
and it makes the page count as "localhost" so the browser allows the mic.)
"""
import base64
import json
import os
import re
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).with_name(".env"))

import tools  # noqa: E402
import tts  # noqa: E402
from agent import Agent  # noqa: E402
from triage import classify  # noqa: E402
from voice import transcribe  # noqa: E402

HOST, PORT = "127.0.0.1", int(os.getenv("QUIETDESK_PORT", "8000"))
INDEX = Path(__file__).with_name("static") / "index.html"
MAX_UPLOAD = 20 * 1024 * 1024

agent = Agent()
agent_lock = threading.Lock()  # one conversation, one question at a time

# Where replies are spoken: "pi" = the Pi's own speaker (e.g. a Bluetooth speaker paired to it),
# "browser" = sent back to the laptop browser to play.
SPEAK_ON = os.getenv("QUIETDESK_SPEAK_ON", "pi")
speak_lock = threading.Lock()  # so two replies never talk over each other


def _speak_on_pi(text: str, ding: bool, mood: str) -> None:
    with speak_lock:
        if ding:
            tts.chime()
        tts.play(text, mood)


def say(text: str, ding: bool = False, mood: str = "neutral") -> str:
    """Speak a reply (Meta MMS-TTS in the given mood, espeak-ng as backup), with an optional chime.
    Returns base64 WAV for the browser, or "" when the Pi speaks it itself."""
    if not text:
        return ""
    if SPEAK_ON == "pi":
        threading.Thread(target=_speak_on_pi, args=(text, ding, mood), daemon=True).start()
        return ""
    return base64.b64encode(tts.wav_bytes(text, mood)).decode()


def ask_agent(text: str) -> dict:
    with agent_lock:
        reply = agent.ask(text)
        used = list(agent.tool_log)
        mood = agent.mood
    return {"reply": reply, "mood": mood, "tools": used, "audio": say(reply, mood=mood)}


def state() -> dict:
    return {
        "notifications": tools.all_notifications(),
        "notes": tools.list_notes(5)["notes"],
        "reminders": tools.list_reminders()["reminders"],
        "voice": True,
    }


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, data: dict, code: int = 200) -> None:
        self._send(code, json.dumps(data).encode(), "application/json")

    def _body(self) -> bytes:
        length = int(self.headers.get("Content-Length", 0))
        if length > MAX_UPLOAD:
            raise ValueError("upload too large")
        return self.rfile.read(length)

    def do_GET(self):
        if self.path == "/":
            self._send(200, INDEX.read_bytes(), "text/html; charset=utf-8")
        elif self.path == "/api/state":
            self._json(state())
        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self):
        try:
            if self.path == "/api/voice":
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                    f.write(self._body())
                    wav = f.name
                try:
                    heard = transcribe(wav)
                finally:
                    os.unlink(wav)
                if not heard:
                    msg = "Sorry, I didn't catch that."
                    return self._json({"heard": "", "reply": msg, "tools": [], "audio": say(msg)})
                return self._json({"heard": heard, **ask_agent(heard)})

            data = json.loads(self._body() or b"{}")

            if self.path == "/api/ask":
                return self._json(ask_agent(str(data.get("text", "")).strip()))

            if self.path == "/api/notify":
                app = str(data.get("app", "")).strip() or "Messages"
                sender = str(data.get("sender", "")).strip() or "Unknown"
                text = str(data.get("text", "")).strip()
                result = classify(app, sender, text)
                nid = tools.add_notification(app, sender, text, **result)
                audio = ""
                if result["urgency"] == "urgent":
                    audio = say(f"Urgent message from {sender} on {app}.", ding=True, mood="serious")
                return self._json({"id": nid, **result, "audio": audio})

            if self.path == "/api/reset":  # clean slate between demo takes
                tools.clear_notifications()
                agent.last_response_id = None
                return self._json({"ok": True})

            m = re.fullmatch(r"/api/notifications/(\d+)/(send|dismiss)", self.path)
            if m:
                nid, action = int(m.group(1)), m.group(2)
                if action == "send":
                    # Demo: marks it sent. In the full build the Android app sends it with RemoteInput.
                    tools.set_notification_status(nid, "sent", str(data.get("text", "")).strip())
                else:
                    tools.set_notification_status(nid, "dismissed")
                return self._json({"ok": True})

            self._json({"error": "not found"}, 404)
        except Exception as e:  # show errors on the page instead of dropping the request
            print(f"  error: {e}")
            self._json({"error": str(e)}, 500)

    def log_message(self, fmt, *args):  # keep the terminal quiet except for errors and tool calls
        pass


if __name__ == "__main__":
    print(f"QuietDesk web console on http://localhost:{PORT} (open it through the SSH tunnel)")
    tts.warm_up()
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
