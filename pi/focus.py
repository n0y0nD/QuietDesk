"""Focus sessions: a timer QuietDesk runs while the phone stays out of reach.

During a session only urgent messages interrupt; everything else waits for the digest at the end.
If the user says yes, Lumi also sends one polite auto-reply per person ("busy until 5:30 PM").
"""
import os
import threading
import time
from datetime import datetime

# QUIETDESK_FOCUS_AUTO_REPLY=on: the user chose to have auto-replies on in every focus session
# (they can still say "don't auto-reply" to turn them off for one session). Otherwise Lumi asks each time.
AUTO_REPLY_DEFAULT = os.getenv("QUIETDESK_FOCUS_AUTO_REPLY", "off").strip().lower() == "on"

_lock = threading.Lock()
_session = None  # {"start", "end", "minutes", "auto_reply", "replied": set of senders, "auto_count"}
on_end = None    # web.py sets this to log each session: on_end(session, early)


def clock(ts: float) -> str:
    """12-hour time like 4:06 PM."""
    t = datetime.fromtimestamp(ts)
    return f"{t.hour % 12 or 12}:{t.minute:02d} {'AM' if t.hour < 12 else 'PM'}"


def start(minutes: int = 25) -> dict:
    global _session
    minutes = max(1, min(180, int(minutes or 25)))
    now = time.time()
    with _lock:
        old, _session = _session, {"start": now, "end": now + minutes * 60, "minutes": minutes,
                                   "auto_reply": AUTO_REPLY_DEFAULT, "replied": set(), "auto_count": 0}
    if old and on_end:
        on_end(old, True)
    return {"ok": True, "minutes": minutes, "ends_at": clock(now + minutes * 60),
            "auto_reply": AUTO_REPLY_DEFAULT}


def stop() -> dict:
    global _session
    with _lock:
        s, _session = _session, None
    if s is None:
        return {"ok": False, "error": "no focus session is running"}
    if on_end:
        on_end(s, True)
    return {"ok": True, "focused_minutes": round((time.time() - s["start"]) / 60)}


def set_auto_reply(on: bool) -> dict:
    s = _session
    if s is None:
        return {"ok": False, "error": "auto-replies only work during a focus session; start one first"}
    s["auto_reply"] = bool(on)
    return {"ok": True, "auto_reply": s["auto_reply"], "until": clock(s["end"])}


def claim_auto_reply(sender: str) -> bool:
    """True once per sender per session, while auto-replies are on (so nobody gets two)."""
    with _lock:
        s = _session
        if not s or not s["auto_reply"] or sender in s["replied"]:
            return False
        s["replied"].add(sender)
        s["auto_count"] += 1
        return True


def status() -> dict:
    s = _session
    if s is None:
        return {"active": False}
    left = max(0, s["end"] - time.time())
    return {"active": True, "minutes": s["minutes"], "left_seconds": int(left), "ends_at": clock(s["end"]),
            "start": s["start"], "auto_reply": s["auto_reply"], "auto_count": s["auto_count"]}


def pop_finished():
    """The session that just ran out (once), or None."""
    global _session
    with _lock:
        if _session and time.time() >= _session["end"]:
            s, _session = _session, None
        else:
            return None
    if on_end:
        on_end(s, False)
    return s
