"""Tools the QuietDesk agent can call: notes and reminders, stored in SQLite."""
import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).with_name("quietdesk.db")


def _db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("CREATE TABLE IF NOT EXISTS notes (id INTEGER PRIMARY KEY, text TEXT, created TEXT)")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS reminders "
        "(id INTEGER PRIMARY KEY, text TEXT, due TEXT, done INTEGER DEFAULT 0)"
    )
    return conn


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
]

TOOL_FUNCTIONS = {
    "save_note": save_note,
    "list_notes": list_notes,
    "create_reminder": create_reminder,
    "list_reminders": list_reminders,
}


def run_tool(name: str, args: dict) -> dict:
    fn = TOOL_FUNCTIONS.get(name)
    if fn is None:
        return {"ok": False, "error": f"unknown tool {name}"}
    try:
        return fn(**args)
    except Exception as e:  # report tool errors back to the model instead of crashing
        return {"ok": False, "error": str(e)}
