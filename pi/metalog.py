"""A live list of every Meta model call QuietDesk makes, for the "Meta AI, live" panel on the web console."""
import threading
import time
from collections import deque

_lock = threading.Lock()
_calls = deque(maxlen=40)
seq = 0  # goes up with every call, so the page knows when to refresh the panel
totals = {}  # model -> number of calls since start
stats = {}   # model -> {"calls", "ms", "tokens"} since start


def record(model: str, purpose: str, ms: float, ok: bool = True, detail: str = "",
           tokens: int = 0, result: str = "") -> None:
    """detail: small facts (tokens, words heard); result: what the call decided, in plain words."""
    global seq
    with _lock:
        seq += 1
        totals[model] = totals.get(model, 0) + 1
        s = stats.setdefault(model, {"calls": 0, "ms": 0, "tokens": 0})
        s["calls"] += 1
        s["ms"] += round(ms)
        s["tokens"] += tokens
        _calls.appendleft({"seq": seq, "at": time.strftime("%H:%M:%S"), "ts": time.time(), "model": model,
                           "purpose": purpose, "ms": round(ms), "ok": ok, "detail": detail,
                           "tokens": tokens, "result": result})


def add_result(purpose: str, result: str) -> None:
    """Add what a call decided once it is known (e.g. triage: urgent), to the newest call with that purpose."""
    global seq
    with _lock:
        for c in _calls:
            if c["purpose"] == purpose:
                c["result"] = result
                seq += 1  # so the page shows it
                break


class timed:
    """with timed(model, purpose) as t: ...; t.detail = "..."  -> recorded when the block ends."""

    def __init__(self, model: str, purpose: str):
        self.model, self.purpose, self.detail, self.tokens, self.result = model, purpose, "", 0, ""

    def __enter__(self):
        self.t0 = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc, tb):
        record(self.model, self.purpose, (time.perf_counter() - self.t0) * 1000, exc is None,
               self.detail if exc is None else str(exc)[:80], self.tokens, self.result)
        return False


def clear() -> None:
    """Empty the panel (the Reset button, between demo takes)."""
    global seq
    with _lock:
        _calls.clear()
        totals.clear()
        stats.clear()
        seq += 1


def snapshot() -> dict:
    with _lock:
        return {"seq": seq, "totals": dict(totals), "stats": {k: dict(v) for k, v in stats.items()},
                "calls": list(_calls), "now": time.time()}
