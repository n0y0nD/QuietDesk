"""Tools the QuietDesk agent can call: notes and reminders, stored in SQLite."""
import sqlite3
from datetime import datetime
from pathlib import Path

import focus

DB_PATH = Path(__file__).with_name("quietdesk.db")


def _db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("CREATE TABLE IF NOT EXISTS notes (id INTEGER PRIMARY KEY, text TEXT, created TEXT)")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS reminders "
        "(id INTEGER PRIMARY KEY, text TEXT, due TEXT, done INTEGER DEFAULT 0)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS notifications ("
        "id INTEGER PRIMARY KEY, app TEXT, sender TEXT, text TEXT, received TEXT, "
        "urgency TEXT, reason TEXT, draft TEXT, status TEXT DEFAULT 'new', reply TEXT)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS focus_log (id INTEGER PRIMARY KEY, start TEXT, minutes REAL, "
        "held INTEGER, urgent INTEGER, auto_replies INTEGER, early INTEGER)"
    )
    _add_phone_columns(conn)
    return conn


_migrated = False


def _add_phone_columns(conn) -> None:
    """Columns for real phone notifications (KDE Connect), added to older databases once."""
    global _migrated
    if _migrated:
        return
    have = {r[1] for r in conn.execute("PRAGMA table_info(notifications)")}
    for col, kind in (("source", "TEXT DEFAULT 'demo'"), ("phone_id", "TEXT"), ("reply_id", "TEXT")):
        if col not in have:
            conn.execute(f"ALTER TABLE notifications ADD COLUMN {col} {kind}")
    _migrated = True


# ---- Phone notifications (relayed by the phone, sorted by Muse Spark) ----

NOTIF_COLS = ["id", "app", "sender", "text", "received", "urgency", "reason", "draft", "status", "reply",
              "source", "phone_id", "reply_id"]


def add_notification(app: str, sender: str, text: str, urgency: str, reason: str, draft: str,
                     source: str = "demo", phone_id: str = None, reply_id: str = None) -> int:
    """source: "demo" (simulated phone on the web page) or "phone" (real phone via KDE Connect).
    reply_id: set when the phone says this notification can be answered (e.g. WhatsApp)."""
    with _db() as conn:
        cur = conn.execute(
            "INSERT INTO notifications (app, sender, text, received, urgency, reason, draft, "
            "source, phone_id, reply_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (app, sender, text, datetime.now().isoformat(timespec="minutes"), urgency, reason, draft,
             source, phone_id, reply_id or None),
        )
    return cur.lastrowid


def get_notification(notification_id: int) -> dict:
    with _db() as conn:
        row = conn.execute(f"SELECT {', '.join(NOTIF_COLS)} FROM notifications WHERE id = ?",
                           (notification_id,)).fetchone()
    return dict(zip(NOTIF_COLS, row)) if row else None


def all_notifications() -> list:
    with _db() as conn:
        rows = conn.execute(f"SELECT {', '.join(NOTIF_COLS)} FROM notifications ORDER BY id DESC").fetchall()
    return [dict(zip(NOTIF_COLS, r)) for r in rows]


def set_notification_status(notification_id: int, status: str, reply: str = None) -> None:
    with _db() as conn:
        conn.execute(
            "UPDATE notifications SET status = ?, reply = COALESCE(?, reply) WHERE id = ?",
            (status, reply, notification_id),
        )


def clear_notifications() -> None:
    with _db() as conn:
        conn.execute("DELETE FROM notifications")


def get_missed_notifications(urgency: str = "all") -> dict:
    """Notifications the user has not handled yet. urgency: urgent, digest or all."""
    items = [n for n in all_notifications() if n["status"] == "new"]
    if urgency in ("urgent", "digest"):
        items = [n for n in items if n["urgency"] == urgency]
    return {
        "notifications": [
            {**{k: n[k] for k in ("id", "app", "sender", "text", "received", "urgency", "draft")},
             "from": "real phone" if n["source"] == "phone" else "simulated phone",
             "can_reply": n["source"] != "phone" or bool(n["reply_id"])}
            for n in items
        ]
    }


def draft_reply(notification_id: int, text: str) -> dict:
    """Save a reply draft. It is NOT sent: the user must approve it on the screen."""
    with _db() as conn:
        cur = conn.execute("UPDATE notifications SET draft = ? WHERE id = ?", (text, notification_id))
    if cur.rowcount == 0:
        return {"ok": False, "error": f"no notification with id {notification_id}"}
    return {"ok": True, "status": "draft saved, waiting for the user to approve and send it"}


def save_note(text: str) -> dict:
    with _db() as conn:
        cur = conn.execute(
            "INSERT INTO notes (text, created) VALUES (?, ?)",
            (text, datetime.now().isoformat(timespec="minutes")),
        )
    return {"ok": True, "note_id": cur.lastrowid}


def list_notes(limit: int = 10) -> dict:
    with _db() as conn:
        rows = conn.execute(
            "SELECT id, text, created FROM notes ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return {"notes": [{"id": r[0], "text": r[1], "created": r[2]} for r in rows]}


def create_reminder(text: str, due: str) -> dict:
    """`due` is a local time in ISO format, e.g. 2026-10-31T17:00."""
    try:
        datetime.fromisoformat(due)
    except ValueError:
        return {"ok": False, "error": "due must be ISO format like 2026-10-31T17:00"}
    with _db() as conn:
        cur = conn.execute("INSERT INTO reminders (text, due) VALUES (?, ?)", (text, due))
    return {"ok": True, "reminder_id": cur.lastrowid, "due": due}


def list_reminders() -> dict:
    with _db() as conn:
        rows = conn.execute(
            "SELECT id, text, due FROM reminders WHERE done = 0 ORDER BY due"
        ).fetchall()
    return {"reminders": [{"id": r[0], "text": r[1], "due": r[2]} for r in rows]}


def due_reminders() -> list:
    """Reminders whose time has come and that have not gone off yet."""
    now = datetime.now()
    due = []
    for r in list_reminders()["reminders"]:
        try:
            if datetime.fromisoformat(r["due"]) <= now:
                due.append(r)
        except ValueError:
            pass
    return due


def mark_reminder_done(reminder_id: int) -> None:
    with _db() as conn:
        conn.execute("UPDATE reminders SET done = 1 WHERE id = ?", (reminder_id,))


def start_focus(minutes: int = 25) -> dict:
    return focus.start(minutes)


def stop_focus() -> dict:
    return focus.stop()


def dismiss_notifications(sender: str = "", app: str = "") -> dict:
    """Mark waiting notifications as handled (all of them, or only from one sender / app). Sends nothing."""
    items = [n for n in all_notifications() if n["status"] == "new"
             and (not sender or sender.lower().replace(" ", "") in (n["sender"] or "").lower().replace(" ", ""))
             and (not app or app.lower() == (n["app"] or "").lower())]
    for n in items:
        set_notification_status(n["id"], "dismissed")
    return {"ok": True, "dismissed": len(items)}


ring_hook = None  # web.py sets this to the phone's ring function


def ring_phone() -> dict:
    if ring_hook is None:
        return {"ok": False, "error": "no phone is linked"}
    ring_hook()
    return {"ok": True, "status": "the phone is ringing"}


def set_auto_reply(on: bool = True) -> dict:
    return focus.set_auto_reply(on)


def save_auto_reply(notification_id: int, text: str) -> None:
    """Remember the auto-reply Hush sent; the message itself still waits for the user."""
    with _db() as conn:
        conn.execute("UPDATE notifications SET reply = ? WHERE id = ?", (text, notification_id))


def log_focus(start: float, minutes: float, held: int, urgent: int, auto_replies: int, early: bool) -> None:
    with _db() as conn:
        conn.execute(
            "INSERT INTO focus_log (start, minutes, held, urgent, auto_replies, early) VALUES (?, ?, ?, ?, ?, ?)",
            (datetime.fromtimestamp(start).isoformat(timespec="minutes"), round(minutes, 1), held, urgent,
             auto_replies, int(early)),
        )


def get_focus_stats() -> dict:
    """Today's focus score: minutes focused (including a session still running), sessions,
    messages held back, urgent ones let through, auto-replies sent."""
    today = datetime.now().date().isoformat()
    with _db() as conn:
        rows = conn.execute(
            "SELECT minutes, held, urgent, auto_replies FROM focus_log WHERE start >= ?", (today,)
        ).fetchall()
    stats = {"sessions": len(rows), "minutes": sum(r[0] for r in rows), "held_back": sum(r[1] for r in rows),
             "urgent_let_through": sum(r[2] for r in rows), "auto_replies": sum(r[3] for r in rows)}
    f = focus.status()
    if f["active"]:
        stats["minutes"] += (f["minutes"] * 60 - f["left_seconds"]) / 60
        stats["running_now"] = True
    stats["minutes"] = round(stats["minutes"])
    return stats


# Tool definitions in the Responses API format (flat: type, name, description, parameters).
TOOL_SPECS = [
    {
        "type": "function",
        "name": "save_note",
        "description": "Save a short note the user wants to remember.",
        "parameters": {
            "type": "object",
            "properties": {"text": {"type": "string", "description": "The note text"}},
            "required": ["text"],
        },
    },
    {
        "type": "function",
        "name": "list_notes",
        "description": "Get the user's most recent notes.",
        "parameters": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "description": "How many notes, default 10"}},
        },
    },
    {
        "type": "function",
        "name": "create_reminder",
        "description": "Create a reminder at a specific local date and time.",
        "parameters": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "What to remind the user about"},
                "due": {"type": "string", "description": "Local time, ISO format, e.g. 2026-10-31T17:00"},
            },
            "required": ["text", "due"],
        },
    },
    {
        "type": "function",
        "name": "list_reminders",
        "description": "Get the user's upcoming reminders.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "type": "function",
        "name": "get_missed_notifications",
        "description": "Get phone notifications the user has not handled yet, already sorted into "
        "urgent or digest. Use it when the user asks what they missed or for their digest.",
        "parameters": {
            "type": "object",
            "properties": {
                "urgency": {"type": "string", "enum": ["urgent", "digest", "all"], "description": "Default all"}
            },
        },
    },
    {
        "type": "function",
        "name": "draft_reply",
        "description": "Write or change the reply draft for a notification. This never sends anything: "
        "the user reviews the draft on the screen and approves it before it is sent.",
        "parameters": {
            "type": "object",
            "properties": {
                "notification_id": {"type": "integer"},
                "text": {"type": "string", "description": "The reply text"},
            },
            "required": ["notification_id", "text"],
        },
    },
    {
        "type": "function",
        "name": "send_reply",
        "description": "Send the saved draft for a notification. Only after you read that exact draft to the "
        "user and asked whether to send it, and the user's newest message clearly says yes. "
        "QuietDesk checks this and refuses otherwise.",
        "parameters": {
            "type": "object",
            "properties": {"notification_id": {"type": "integer"}},
            "required": ["notification_id"],
        },
    },
    {
        "type": "function",
        "name": "start_focus",
        "description": "Start a focus session timer (shown on the desk screen). During it only urgent "
        "messages interrupt; the rest wait for a digest when it ends. Use when the user wants to focus, "
        "study or work for a while.",
        "parameters": {
            "type": "object",
            "properties": {"minutes": {"type": "integer", "description": "Length in minutes, default 25"}},
        },
    },
    {
        "type": "function",
        "name": "stop_focus",
        "description": "End the current focus session early.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "type": "function",
        "name": "set_auto_reply",
        "description": "Turn polite auto-replies on or off for the current focus session: each person who "
        "sends a non-urgent message on the real phone gets one short 'busy until <time>, will reply after' "
        "message, marked as an auto-reply. Turn it on only when the user clearly asks or says yes.",
        "parameters": {
            "type": "object",
            "properties": {"on": {"type": "boolean"}},
            "required": ["on"],
        },
    },
    {
        "type": "function",
        "name": "dismiss_notifications",
        "description": "Clear waiting notifications from the desk (marks them handled; nothing is sent or deleted "
        "on the phone). Leave sender and app empty to clear all, or give one to clear only those.",
        "parameters": {
            "type": "object",
            "properties": {
                "sender": {"type": "string", "description": "Name or number, optional"},
                "app": {"type": "string", "description": "e.g. WhatsApp, optional"},
            },
        },
    },
    {
        "type": "function",
        "name": "ring_phone",
        "description": "Make the user's phone ring loudly so they can find it (works even on silent).",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "type": "function",
        "name": "get_focus_stats",
        "description": "Today's focus score: minutes focused, sessions, messages held back, urgent ones "
        "let through, auto-replies sent. Use when the user asks how their day or focus went.",
        "parameters": {"type": "object", "properties": {}},
    },
]

TOOL_FUNCTIONS = {
    "save_note": save_note,
    "list_notes": list_notes,
    "create_reminder": create_reminder,
    "list_reminders": list_reminders,
    "get_missed_notifications": get_missed_notifications,
    "draft_reply": draft_reply,
    "start_focus": start_focus,
    "stop_focus": stop_focus,
    "set_auto_reply": set_auto_reply,
    "get_focus_stats": get_focus_stats,
    "ring_phone": ring_phone,
    "dismiss_notifications": dismiss_notifications,
}


def run_tool(name: str, args: dict) -> dict:
    fn = TOOL_FUNCTIONS.get(name)
    if fn is None:
        return {"ok": False, "error": f"unknown tool {name}"}
    try:
        return fn(**args)
    except Exception as e:  # report tool errors back to the model instead of crashing
        return {"ok": False, "error": str(e)}
