"""A live list of every Meta model call QuietDesk makes, for the "Meta AI, live" panel on the web console."""
import threading
import time
from collections import deque

_lock = threading.Lock()
_calls = deque(maxlen=40)
seq = 0  # goes up with every call, so the page knows when to refresh the panel
totals = {}  # model -> number of calls since start


def record(model: str, purpose: str, ms: float, ok: bool = True, detail: str = "") -> None:
    global seq
    with _lock:
        seq += 1
        totals[model] = totals.get(model, 0) + 1
        _calls.appendleft({"seq": seq, "at": time.strftime("%H:%M:%S"), "model": model, "purpose": purpose,
                           "ms": round(ms), "ok": ok, "detail": detail})


class timed:
    """with timed(model, purpose) as t: ...; t.detail = "..."  -> recorded when the block ends."""

    def __init__(self, model: str, purpose: str):
        self.model, self.purpose, self.detail = model, purpose, ""

    def __enter__(self):
        self.t0 = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc, tb):
        record(self.model, self.purpose, (time.perf_counter() - self.t0) * 1000, exc is None,
               self.detail if exc is None else str(exc)[:80])
        return False


def snapshot() -> dict:
    with _lock:
        return {"seq": seq, "totals": dict(totals), "calls": list(_calls)}
