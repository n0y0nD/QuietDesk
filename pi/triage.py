"""Notification triage with Muse Spark: urgent now, or saved for the digest."""
import json
import re
from datetime import datetime

from agent import MODEL, create

TRIAGE_INSTRUCTIONS = (
    "You sort phone notifications for someone in a focused work session whose phone is out of reach. "
    "Mark a notification 'urgent' only if waiting an hour could cause real harm or a missed obligation: "
    "family emergencies, health, someone waiting on them right now, security alerts like OTPs they did not "
    "request, a manager asking for something due soon. If a real person explicitly says it is urgent, "
    "asks for something right now or ASAP, or is clearly waiting on the user, it is 'urgent'. "
    "Everything else is 'digest': promotions, social "
    "media, group chat banter, newsletters, routine updates. "
    "If a person is asking something and a reply makes sense, write a short, natural reply draft in the "
    "same language and tone as the message, otherwise leave draft empty. Never invent facts or promises. "
    'Respond with ONLY a JSON object: {"urgency": "urgent" or "digest", "reason": "<one short sentence>", '
    '"draft": "<reply or empty string>"}'
)


def _parse(text: str) -> dict:
    match = re.search(r"\{.*\}", text, re.S)
    data = json.loads(match.group(0)) if match else {}
    urgency = data.get("urgency", "digest")
    return {
        "urgency": urgency if urgency in ("urgent", "digest") else "digest",
        "reason": str(data.get("reason", "")).strip(),
        "draft": str(data.get("draft", "")).strip(),
    }


def classify(app: str, sender: str, text: str) -> dict:
    now = datetime.now().strftime("%A %H:%M")
    resp = create(
        model=MODEL,
        instructions=TRIAGE_INSTRUCTIONS,
        input=f"Time: {now}\nApp: {app}\nFrom: {sender}\nMessage: {text}",
    )
    try:
        return _parse(resp.output_text)
    except (json.JSONDecodeError, AttributeError):
        return {"urgency": "digest", "reason": "Could not sort this one, saved for the digest.", "draft": ""}
