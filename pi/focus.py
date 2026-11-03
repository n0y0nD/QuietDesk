"""Focus sessions: a timer QuietDesk runs while the phone stays out of reach.

During a session only urgent messages interrupt; everything else waits for the digest at the end.
"""
import threading
import time
from datetime import datetime

_lock = threading.Lock()
_session = None  # {"start": epoch seconds, "end": epoch seconds, "minutes": int}


def clock(ts: float) -> str:
    """12-hour time like 4:06 PM."""
    t = datetime.fromtimestamp(ts)
    return f"{t.hour % 12 or 12}:{t.minute:02d} {'AM' if t.hour < 12 else 'PM'}"


def start(minutes: int = 25) -> dict:
    global _session
    minutes = max(1, min(180, int(minutes or 25)))
    now = time.time()
    with _lock:
        _session = {"start": now, "end": now + minutes * 60, "minutes": minutes}
    return {"ok": True, "minutes": minutes, "ends_at": clock(now + minutes * 60)}


def stop() -> dict:
    global _session
    with _lock:
        s, _session = _session, None
    if s is None:
        return {"ok": False, "error": "no focus session is running"}
    return {"ok": True, "focused_minutes": round((time.time() - s["start"]) / 60)}


def status() -> dict:
    s = _session
    if s is None:
        return {"active": False}
    left = max(0, s["end"] - time.time())
    return {"active": True, "minutes": s["minutes"], "left_seconds": int(left),
            "ends_at": clock(s["end"]), "start": s["start"]}


def pop_finished():
    """The session that just ran out (once), or None."""
    global _session
    with _lock:
        if _session and time.time() >= _session["end"]:
            s, _session = _session, None
            return s
    return None
