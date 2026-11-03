"""QuietDesk's face on the 1.5" 128x128 RGB OLED: minimal animated screens drawn with Pillow.

render(state, t) returns one 128x128 frame; hardware.py shows 30 frames a second.
  idle      : blinking eyes, 12-hour clock, next reminder; phone battery and weather on top
  focus     : a ring that empties as the focus session runs, minutes left, messages held back
  listening : wide green eyes and moving sound bars
  thinking  : eyes look up, three bouncing dots
  reply     : eyes show Muse Spark's mood (happy, calm, serious, neutral), reply text below
  alert     : a new message, a reminder that is due, or the end of a focus session

Shapes are drawn at 2x and scaled down (smooth edges); text is drawn at 1x so it stays sharp.
Preview without the OLED:  python screen.py   (writes PNGs and screen-preview.gif to ./preview)
"""
import math
from datetime import datetime

from PIL import Image, ImageDraw, ImageFont

W = H = 128
SS = 2  # supersampling for shapes
BG = (0, 0, 0)
TEXT = (236, 238, 243)
MUTED = (112, 119, 134)
FAINT = (40, 44, 52)
ACCENT = (96, 205, 255)
RED = (255, 84, 84)
GREEN = (80, 222, 140)
AMBER = (255, 184, 77)
VIOLET = (170, 145, 255)
MOOD = {"happy": (255, 209, 102), "calm": (124, 199, 255), "serious": (255, 128, 96), "neutral": TEXT}
APP_COLOR = {"whatsapp": (37, 211, 102), "whatsapp business": (37, 211, 102), "slack": (224, 30, 90),
             "telegram": (42, 171, 238), "instagram": (225, 48, 108), "gmail": (234, 67, 53),
             "messages": (66, 133, 244), "sms": (66, 133, 244), "discord": (88, 101, 242),
             "signal": (58, 118, 240), "reminder": AMBER, "focus": VIOLET}

NUNITO = "/usr/share/fonts/truetype/nunito-sans/NunitoSans-VariableFont_YTLC,opsz,wdth,wght.ttf"
_fonts = {}


def font(size: int, weight: str = "Regular"):
    """Nunito Sans (rounded, friendly) if installed, DejaVu Sans otherwise."""
    key = (size, weight)
    if key not in _fonts:
        try:
            f = ImageFont.truetype(NUNITO, size)
            f.set_variation_by_name(weight)
        except Exception:
            try:
                bold = "-Bold" if weight in ("Bold", "ExtraBold", "Black") else ""
                f = ImageFont.truetype(f"/usr/share/fonts/truetype/dejavu/DejaVuSans{bold}.ttf", size)
            except Exception:
                f = ImageFont.load_default()
        _fonts[key] = f
    return _fonts[key]


def dim(color, k):
    return tuple(int(c * k) for c in color)


def clock(now: datetime):
    return f"{now.hour % 12 or 12}:{now.minute:02d}", "AM" if now.hour < 12 else "PM"


class Pen:
    """Draws shapes on a 2x canvas and queues text for the final 1x frame. Coordinates are 128-based."""

    def __init__(self):
        self.big = Image.new("RGB", (W * SS, H * SS), BG)
        self.d = ImageDraw.Draw(self.big)
        self.texts = []
        self._measure = ImageDraw.Draw(Image.new("RGB", (1, 1)))

    def _s(self, box):
        return [v * SS for v in box]

    def rrect(self, box, r, fill):
        self.d.rounded_rectangle(self._s(box), radius=r * SS, fill=fill)

    def ellipse(self, box, fill=None, outline=None, width=1):
        self.d.ellipse(self._s(box), fill=fill, outline=outline, width=width * SS)

    def arc(self, box, start, end, fill, width):
        self.d.arc(self._s(box), start, end, fill=fill, width=int(width * SS))

    def line(self, pts, fill, width=1):
        self.d.line([(x * SS, y * SS) for x, y in pts], fill=fill, width=max(1, int(width * SS)))

    def polygon(self, pts, fill):
        self.d.polygon([(x * SS, y * SS) for x, y in pts], fill=fill)

    def text(self, xy, s, f, fill):
        self.texts.append((xy, s, f, fill))

    def length(self, s, f):
        return self._measure.textlength(s, font=f)

    def center(self, y, s, f, fill, cx=W / 2):
        self.text((cx - self.length(s, f) / 2, y), s, f, fill)

    def wrap(self, s, f, width):
        lines, line = [], ""
        for word in (s or "").split():
            test = f"{line} {word}".strip()
            if self.length(test, f) <= width:
                line = test
            else:
                if line:
                    lines.append(line)
                line = word
        if line:
            lines.append(line)
        return lines

    def fit(self, s, f, width):
        """Cut a line to the width with an ellipsis."""
        if self.length(s, f) <= width:
            return s
        while s and self.length(s + "…", f) > width:
            s = s[:-1]
        return s.rstrip() + "…"

    def frame(self):
        img = self.big.resize((W, H), Image.LANCZOS)
        d = ImageDraw.Draw(img)
        for xy, s, f, fill in self.texts:
            d.text(xy, s, font=f, fill=fill)
        return img


# ---- eyes ----

def blink(t: float) -> float:
    """1 = open, 0 = shut: a quick blink every few seconds, sometimes a double blink."""
    period = 4.3
    phase = t % period
    for start in ((0.0, 0.3) if int(t / period) % 3 == 2 else (0.0,)):
        if start <= phase < start + 0.16:
            return max(0.06, abs(phase - start - 0.08) / 0.08)
    return 1.0


def glance(t: float) -> float:
    """Where the eyes look: mostly ahead, now and then left or right, with a short smooth move."""
    spots = [0, 0, -6, 0, 0, 5, 0, -3]
    i = int(t / 1.9)
    k = min(1.0, (t % 1.9) / 0.12)  # 0.12 s to move
    a, b = spots[(i - 1) % 8], spots[i % 8]
    return a + (b - a) * k


def eyes(p, cy, color, w=20, h=26, open_=1.0, dx=0.0, dy=0.0, mood="neutral", gap=44):
    for cx in (64 - gap / 2 + dx, 64 + gap / 2 + dx):
        if mood == "happy":  # smiling closed eyes ^ ^
            y0 = cy + dy - h / 4
            p.arc((cx - w / 2, y0, cx + w / 2, y0 + w), 195, 345, color, 3.5)
            continue
        top, bottom = cy + dy - h / 2, cy + dy + h / 2
        if mood == "calm":
            top = cy + dy - h / 6
        hh = max(2.5, (bottom - top) * open_)
        mid = (top + bottom) / 2
        p.rrect((cx - w / 2, mid - hh / 2, cx + w / 2, mid + hh / 2), min(w * 0.38, hh / 2), color)
        if mood == "serious" and open_ > 0.5:  # a slanted lid: focused
            x0, x1 = cx - w / 2 - 1, cx + w / 2 + 1
            low, high = top + h * 0.26, top - 1
            inner_low = [(x1, low), (x0, high)] if cx < 64 else [(x1, high), (x0, low)]
            p.polygon([(x0, top - 6), (x1, top - 6)] + inner_low, BG)


# ---- small icons (drawn as shapes, so they scale cleanly) ----

def battery_icon(p, x, y, pct, charging):
    p.rrect((x, y, x + 13, y + 7), 1.5, MUTED)
    p.rrect((x + 1, y + 1, x + 12, y + 6), 1, BG)
    p.rrect((x + 13.5, y + 2, x + 15, y + 5), 0.5, MUTED)
    color = GREEN if charging else (RED if pct <= 15 else TEXT)
    fill = max(1, 10 * pct / 100)
    p.rrect((x + 2, y + 2, x + 2 + fill, y + 5), 0.5, dim(color, 0.85))


def weather_icon(p, x, y, code, day):
    """10x10 icon at (x, y) for a WMO weather code."""
    cx, cy = x + 5, y + 5
    if code in (0, 1):
        if day:
            p.ellipse((cx - 2.6, cy - 2.6, cx + 2.6, cy + 2.6), fill=AMBER)
            for k in range(8):
                a = k * math.pi / 4
                p.line([(cx + 4 * math.cos(a), cy + 4 * math.sin(a)), (cx + 5.4 * math.cos(a), cy + 5.4 * math.sin(a))],
                       AMBER, 1)
        else:
            p.ellipse((cx - 4, cy - 4, cx + 4, cy + 4), fill=(200, 210, 230))
            p.ellipse((cx - 2, cy - 5, cx + 5, cy + 2), fill=BG)
        return
    cloud = (190, 198, 212)
    p.ellipse((x, y + 3, x + 6, y + 9), fill=cloud)
    p.ellipse((x + 3, y + 1, x + 10, y + 8), fill=cloud)
    p.rrect((x + 1, y + 5, x + 10, y + 9), 2, cloud)
    if code in (45, 48):
        p.line([(x - 1, y + 11), (x + 11, y + 11)], MUTED, 1)
    elif 51 <= code <= 67 or 80 <= code <= 82:
        for k in range(3):
            p.line([(x + 2 + k * 3, y + 10.5), (x + 1 + k * 3, y + 12.5)], ACCENT, 1)
    elif 71 <= code <= 77 or code in (85, 86):
        for k in range(3):
            p.ellipse((x + 1.5 + k * 3, y + 10.5, x + 2.8 + k * 3, y + 11.8), fill=TEXT)
    elif code >= 95:
        p.polygon([(x + 5, y + 9), (x + 3, y + 12.5), (x + 5, y + 12), (x + 4, y + 14.5), (x + 7, y + 11), (x + 5, y + 11.3)],
                  AMBER)


def status_row(p, s):
    """Top row, kept quiet: phone battery on the left, weather on the right."""
    f = font(10, "SemiBold")
    if s.get("phone"):
        if s.get("battery") is not None:
            battery_icon(p, 4, 4.5, s["battery"], s.get("charging"))
            p.text((22, 1), f"{s['battery']}%", f, MUTED)
        else:
            p.rrect((4, 3, 10, 13), 1.5, MUTED)
            p.rrect((5, 4, 9, 12), 1, BG)
    w = s.get("weather")
    if w:
        label = f"{w['temp']}°"
        x = W - 4 - p.length(label, f)
        p.text((x, 1), label, f, MUTED)
        weather_icon(p, x - 14, 2.5, w["code"], w.get("day", True))


def counts(p, s, y):
    """Tiny dots for waiting messages: red = urgent, grey = later. Nothing when all is read."""
    items = [(n, c) for n, c in ((s.get("urgent", 0), RED), (s.get("digest", 0), MUTED)) if n]
    if not items:
        return
    f = font(10, "Bold")
    widths = [9 + p.length(str(n), f) for n, _ in items]
    x = 64 - (sum(widths) + 8 * (len(items) - 1)) / 2
    for (n, c), w in zip(items, widths):
        p.ellipse((x, y + 4, x + 5, y + 9), fill=c)
        p.text((x + 8, y), str(n), f, c)
        x += w + 8


# ---- screens ----

def idle(p, s, t):
    status_row(p, s)
    urgent = s.get("urgent")
    color = dim(RED, 0.7 + 0.3 * math.sin(t * math.pi)) if urgent else ACCENT
    eyes(p, 37, color, open_=blink(t), dx=glance(t))
    now = s.get("now") or datetime.now()
    hm, ampm = clock(now)
    fb, fs = font(32, "Bold"), font(11, "Bold")
    total = p.length(hm, fb) + 3 + p.length(ampm, fs)
    x = (W - total) / 2
    p.text((x, 56), hm, fb, TEXT)
    p.text((x + p.length(hm, fb) + 3, 77), ampm, fs, MUTED)
    r = s.get("next_reminder")
    f = font(10, "SemiBold")
    if r:
        p.ellipse((6, 102, 10, 106), fill=AMBER)
        p.text((14, 97), p.fit(f"{r['time']} · {r['text']}", f, W - 18), f, MUTED)
    else:
        p.center(97, now.strftime("%a, %d %b"), f, MUTED)
    counts(p, s, 112)


def focus_screen(p, s, t):
    status_row(p, s)
    fo = s["focus"]
    total, left = fo["minutes"] * 60, fo["left_seconds"]
    frac = left / total if total else 0
    cx, cy, r = 64, 60, 36
    p.arc((cx - r, cy - r, cx + r, cy + r), 0, 360, FAINT, 4)
    if frac > 0:
        p.arc((cx - r, cy - r, cx + r, cy + r), -90, -90 + 360 * frac, VIOLET, 4)
        a = math.radians(-90 + 360 * frac)  # a soft glowing dot at the end of the ring
        gx, gy = cx + r * math.cos(a), cy + r * math.sin(a)
        k = 0.75 + 0.25 * math.sin(t * 2.5)
        p.ellipse((gx - 3.2, gy - 3.2, gx + 3.2, gy + 3.2), fill=dim((220, 205, 255), k))
    m, sec = divmod(left, 60)
    p.center(cy - 15, f"{m}:{sec:02d}", font(22, "Bold"), TEXT)
    p.center(cy + 9, "focus", font(10, "SemiBold"), MUTED)
    held, urgent = fo.get("held", 0), fo.get("held_urgent", 0)
    f = font(10, "SemiBold")
    if held:
        p.center(108, f"{held} held back" + (f" · {urgent} urgent" if urgent else ""), f, RED if urgent else MUTED)
    else:
        p.center(108, "all quiet", f, dim(MUTED, 0.8))


def listening(p, s, t):
    eyes(p, 40, GREEN, w=22, h=30)
    for i in range(11):
        x = 21 + i * 8.2
        h = 3 + 15 * abs(math.sin(t * 7 + i * 0.9)) * (0.5 + 0.5 * math.sin(t * 2.3 + i))
        p.rrect((x, 88 - h / 2, x + 3.5, 88 + h / 2), 1.75, GREEN)
    p.center(108, "Listening", font(11, "Bold"), GREEN)


def thinking(p, s, t):
    eyes(p, 40, VIOLET, h=20, dx=5, dy=-5, open_=blink(t + 1.3))
    for i in range(3):
        y = 88 - 5 * max(0.0, math.sin(t * 6 - i * 0.9))
        p.ellipse((52 + i * 10, y - 2.5, 57 + i * 10, y + 2.5), fill=VIOLET)
    p.center(108, "Thinking", font(11, "Bold"), VIOLET)


def reply(p, s, t):
    mood = s.get("mood", "neutral")
    color = MOOD.get(mood, TEXT)
    eyes(p, 17, color, w=15, h=17, open_=blink(t), mood=mood, gap=34)
    f = font(13, "SemiBold")
    lines = p.wrap(s.get("reply", ""), f, W - 12)
    line_h, top, rows = 17, 38, 5
    offset = 0
    if len(lines) > rows:  # long reply: scroll slowly after a short pause
        offset = min((len(lines) - rows) * line_h, max(0.0, (s.get("reply_age", 0) - 2.5) * 7))
    for i, line in enumerate(lines):
        y = top + i * line_h - offset
        if top - 3 <= y <= H - line_h + 2:
            p.text((6, y), line, f, color)


def alert(p, s, t):
    a = s["alert"]
    kind = a.get("kind", "message")
    app = a.get("app", "Phone")
    color = APP_COLOR.get(app.lower(), ACCENT)
    p.ellipse((6, 7, 12, 13), fill=color)
    p.text((17, 3), app, font(11, "Bold"), color)
    if a.get("urgent"):
        k = 0.55 + 0.45 * math.sin(t * 2 * math.pi)
        f = font(9, "ExtraBold")
        w = p.length("URGENT", f) + 10
        p.rrect((W - 6 - w, 4, W - 6, 16), 6, dim(RED, k))
        p.text((W - 1 - w, 4), "URGENT", f, TEXT)
    fb = font(16, "Bold")
    title = p.wrap(a.get("sender", ""), fb, W - 12)
    keep = 3 if kind == "reminder" else 1
    if len(title) > keep:
        title = title[:keep]
        title[-1] = p.fit(title[-1] + " …", fb, W - 12)
    y = 25
    for line in title:
        p.text((6, y), p.fit(line, fb, W - 12), fb, TEXT)
        y += 20
    f = font(12, "SemiBold" if kind != "message" else "Regular")
    lines = p.wrap(a.get("text", ""), f, W - 12)
    rows = max(1, (H - 4 - y - 2) // 15)
    if len(lines) > rows:
        lines = lines[:rows]
        lines[-1] = p.fit(lines[-1] + " …", f, W - 12)
    for line in lines:
        p.text((6, y + 2), line, f, dim(TEXT, 0.78) if kind == "message" else MUTED)
        y += 15


def render(s: dict, t: float) -> Image.Image:
    """One frame. s: state, urgent, digest, phone, battery, charging, weather, next_reminder,
    focus, mood, reply, reply_age, show_reply, alert, now."""
    p = Pen()
    state = s.get("state", "ready")
    if state == "listening":
        listening(p, s, t)
    elif state == "thinking":
        thinking(p, s, t)
    elif s.get("alert"):
        alert(p, s, t)
    elif state == "speaking" or s.get("show_reply"):
        reply(p, s, t)
    elif (s.get("focus") or {}).get("active"):
        focus_screen(p, s, t)
    else:
        idle(p, s, t)
    return p.frame()


if __name__ == "__main__":  # preview every screen as PNGs and one animated GIF
    import os
    import time

    os.makedirs("preview", exist_ok=True)
    base = {"phone": True, "battery": 72, "charging": False, "urgent": 0, "digest": 3,
            "weather": {"temp": 27, "code": 2, "day": True}, "now": datetime(2026, 11, 3, 16, 6),
            "next_reminder": {"time": "5:00 PM", "text": "Call Mom about the doctor visit"}}
    scenes = [
        ("idle", base),
        ("idle-urgent", {**base, "urgent": 1, "weather": {"temp": 24, "code": 61, "day": True}}),
        ("focus", {**base, "focus": {"active": True, "minutes": 25, "left_seconds": 1104, "held": 3, "held_urgent": 0}}),
        ("listening", {**base, "state": "listening"}),
        ("thinking", {**base, "state": "thinking"}),
        ("reply-happy", {**base, "show_reply": True, "mood": "happy", "reply": "Done! Your note is saved."}),
        ("reply-calm", {**base, "show_reply": True, "mood": "calm",
                        "reply": "Your mom says Papa is not feeling well. Maybe give her a call."}),
        ("reply-serious", {**base, "show_reply": True, "mood": "serious",
                           "reply": "Draft for Priya: I will send the demo link before 5 pm. Should I send it?"}),
        ("alert-urgent", {**base, "alert": {"app": "WhatsApp", "sender": "Mom", "urgent": True,
                                            "text": "Beta, call me when you can. Papa ki tabiyat thodi kharab hai."}}),
        ("alert-reminder", {**base, "alert": {"kind": "reminder", "app": "Reminder", "sender": "Call Mom about the doctor visit",
                                              "text": "Now · 5:00 PM"}}),
        ("alert-focus", {**base, "alert": {"kind": "focus", "app": "Focus", "sender": "Focus done",
                                           "text": "25 minutes. 3 messages waiting, none urgent."}}),
    ]
    t0 = time.time()
    n = 0
    frames = []
    for name, s in scenes:
        render(s, 1.0).resize((W * 3, H * 3), Image.NEAREST).save(f"preview/{name}.png")
        for i in range(36):  # 1.2 s of each screen at 30 fps
            frames.append(render({**s, "reply_age": i / 30}, 0.4 + i / 30).resize((W * 2, H * 2), Image.NEAREST))
            n += 1
    print(f"render: {n / (time.time() - t0):.0f} frames/s (incl. resize)")
    frames[0].save("preview/screen-preview.gif", save_all=True, append_images=frames[1:], duration=33, loop=0)
    print("wrote preview/*.png and preview/screen-preview.gif")
