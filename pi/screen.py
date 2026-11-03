"""QuietDesk's face on the 1.5" 128x128 RGB OLED: minimal animated "glow" screens drawn with Pillow.

render(state, t) returns one 128x128 frame; hardware.py shows 30 frames a second.
  idle      : blinking eyes, 12-hour clock, next reminder; phone battery and weather on top
  focus     : a ring that empties as the focus session runs, minutes left, messages held back
  listening : wide green eyes and moving sound bars
  thinking  : eyes look up, three bouncing dots
  reply     : eyes show Muse Spark's mood (happy, calm, serious, neutral), reply text below
  alert     : a new message, a reminder that is due, or the end of a focus session

Shapes are drawn at 2x and scaled down (smooth edges); text is drawn at 1x so it stays sharp.
Eyes and rings glow: they are drawn on their own layer, blurred, and added back under themselves.
Preview without the OLED:  python screen.py   (writes PNGs and screen-preview.gif to ./preview)
"""
import math
from datetime import datetime

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

W = H = 128
SS = 2  # supersampling for shapes
BG = (0, 0, 0)
TEXT = (240, 242, 246)
MUTED = (112, 119, 134)
FAINT = (28, 32, 40)
ACCENT = (110, 215, 255)
RED = (255, 84, 84)
GREEN = (90, 230, 150)
AMBER = (255, 190, 90)
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

    def glow(self, draw, radius=6, strength=0.55):
        """Run draw() on a fresh layer, then add a blurred copy of it (the glow) and the layer itself."""
        layer = Image.new("RGB", self.big.size, BG)
        self.d = ImageDraw.Draw(layer)
        draw()
        blur = layer.filter(ImageFilter.GaussianBlur(radius * SS))
        if strength != 1.0:
            blur = blur.point([int(v * strength) for v in range(256)] * 3)
        self.big = ImageChops.add(ImageChops.add(self.big, blur), layer)
        self.d = ImageDraw.Draw(self.big)

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


def eyes(p, cy, color, w=16, h=28, open_=1.0, dx=0.0, dy=0.0, mood="neutral", gap=36, glow=0.55):
    """Two glowing pill-shaped eyes. mood changes their shape; open_ < 1 is a blink."""
    def draw():
        for cx in (64 - gap / 2 + dx, 64 + gap / 2 + dx):
            if mood == "happy":  # smiling closed eyes ^ ^
                y0 = cy + dy - h / 4
                p.arc((cx - w * 0.65, y0, cx + w * 0.65, y0 + w * 1.3), 200, 340, color, 3)
                continue
            top, bottom = cy + dy - h / 2, cy + dy + h / 2
            if mood == "calm":  # relaxed, half closed
                top = cy + dy - h / 8
            hh = max(2.5, (bottom - top) * open_)
            mid = (top + bottom) / 2
            p.rrect((cx - w / 2, mid - hh / 2, cx + w / 2, mid + hh / 2), min(w / 2, hh / 2), color)
            if mood == "serious" and open_ > 0.5:  # a slanted lid: focused
                x0, x1 = cx - w / 2 - 1, cx + w / 2 + 1
                low, high = top + h * 0.24, top - 1
                inner_low = [(x1, low), (x0, high)] if cx < 64 else [(x1, high), (x0, low)]
                p.polygon([(x0, top - 6), (x1, top - 6)] + inner_low, BG)
    p.glow(draw, radius=6, strength=glow)


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
    f = font(9, "SemiBold")
    quiet = dim(MUTED, 0.9)
    if s.get("phone"):
        if s.get("battery") is not None:
            battery_icon(p, 5, 5, s["battery"], s.get("charging"))
            p.text((23, 2), f"{s['battery']}%", f, quiet)
        else:
            p.rrect((5, 3, 11, 13), 1.5, quiet)
            p.rrect((6, 4, 10, 12), 1, BG)
    w = s.get("weather")
    if w:
        label = f"{w['temp']}°"
        x = W - 5 - p.length(label, f)
        p.text((x, 2), label, f, quiet)
        weather_icon(p, x - 14, 3, w["code"], w.get("day", True))


def counts(p, s, y):
    """Tiny glowing dots for waiting messages: red = urgent, grey = later. Nothing when all is read."""
    items = [(n, c) for n, c in ((s.get("urgent", 0), RED), (s.get("digest", 0), MUTED)) if n]
    if not items:
        return
    f = font(9, "Bold")
    widths = [8 + p.length(str(n), f) for n, _ in items]
    x = 64 - (sum(widths) + 8 * (len(items) - 1)) / 2
    dots = []
    for (n, c), w in zip(items, widths):
        dots.append((x, c))
        p.text((x + 7, y), str(n), f, c)
        x += w + 8
    p.glow(lambda: [p.ellipse((dx, y + 4, dx + 4, y + 8), fill=c) for dx, c in dots], radius=3, strength=0.7)


# ---- screens ----

def idle(p, s, t):
    status_row(p, s)
    urgent = s.get("urgent")
    color = dim(RED, 0.75 + 0.25 * math.sin(t * math.pi)) if urgent else ACCENT
    eyes(p, 40, color, open_=blink(t), dx=glance(t))
    now = s.get("now") or datetime.now()
    hm, ampm = clock(now)
    fb, fs = font(34, "Light"), font(10, "SemiBold")
    total = p.length(hm, fb) + 4 + p.length(ampm, fs)
    x = (W - total) / 2
    p.text((x, 60), hm, fb, TEXT)
    p.text((x + p.length(hm, fb) + 4, 83), ampm, fs, MUTED)
    f = font(10, "Medium")
    r = s.get("next_reminder")
    if r:
        line = p.fit(f"{r['time']} · {r['text']}", f, W - 22)
        x = (W - p.length(line, f) - 8) / 2
        p.glow(lambda: p.ellipse((x, 108, x + 4, 112), fill=AMBER), radius=3, strength=0.7)
        p.text((x + 8, 103), line, f, MUTED)
    else:
        p.center(103, now.strftime("%a, %-d %b"), f, MUTED)
    counts(p, s, 116)


def focus_screen(p, s, t):
    status_row(p, s)
    fo = s["focus"]
    total, left = fo["minutes"] * 60, fo["left_seconds"]
    frac = left / total if total else 0
    cx, cy, r = 64, 62, 38
    box = (cx - r, cy - r, cx + r, cy + r)
    p.arc(box, 0, 360, FAINT, 2)
    if frac > 0:
        a = math.radians(-90 + 360 * frac)
        gx, gy = cx + r * math.cos(a), cy + r * math.sin(a)
        k = 0.8 + 0.2 * math.sin(t * 2.5)

        def ring():
            p.arc(box, -90, -90 + 360 * frac, VIOLET, 3)
            p.ellipse((gx - 3, gy - 3, gx + 3, gy + 3), fill=dim((225, 215, 255), k))
        p.glow(ring, radius=5, strength=0.8)
    m, sec = divmod(left, 60)
    p.center(cy - 17, f"{m}:{sec:02d}", font(26, "Light"), TEXT)
    p.center(cy + 12, "FOCUS", font(9, "Bold"), dim(VIOLET, 0.85))
    held, urgent = fo.get("held", 0), fo.get("held_urgent", 0)
    f = font(10, "Medium")
    if held:
        p.center(110, f"{held} held back" + (f" · {urgent} urgent" if urgent else ""), f, RED if urgent else MUTED)
    else:
        p.center(110, "all quiet", f, dim(MUTED, 0.8))


def listening(p, s, t):
    eyes(p, 40, GREEN, w=18, h=32, glow=0.7)

    def bars():
        for i in range(11):
            x = 22 + i * 8.2
            h = 3 + 14 * abs(math.sin(t * 7 + i * 0.9)) * (0.5 + 0.5 * math.sin(t * 2.3 + i))
            p.rrect((x, 88 - h / 2, x + 3, 88 + h / 2), 1.5, GREEN)
    p.glow(bars, radius=4, strength=0.6)
    p.center(108, "Listening", font(10, "SemiBold"), GREEN)


def thinking(p, s, t):
    eyes(p, 40, VIOLET, h=22, dx=4, dy=-5, open_=blink(t + 1.3))

    def dots():
        for i in range(3):
            y = 88 - 5 * max(0.0, math.sin(t * 6 - i * 0.9))
            p.ellipse((53 + i * 9, y - 2.2, 57.4 + i * 9, y + 2.2), fill=VIOLET)
    p.glow(dots, radius=3, strength=0.7)
    p.center(108, "Thinking", font(10, "SemiBold"), VIOLET)


def reply(p, s, t):
    mood = s.get("mood", "neutral")
    color = MOOD.get(mood, TEXT)
    eyes(p, 18, color, w=11, h=17, open_=blink(t), mood=mood, gap=26, glow=0.5)
    f = font(13, "Medium")
    lines = p.wrap(s.get("reply", ""), f, W - 14)
    line_h, top, rows = 17, 38, 5
    offset = 0
    if len(lines) > rows:  # long reply: scroll slowly after a short pause
        offset = min((len(lines) - rows) * line_h, max(0.0, (s.get("reply_age", 0) - 2.5) * 7))
    for i, line in enumerate(lines):
        y = top + i * line_h - offset
        if top - 3 <= y <= H - line_h + 2:
            p.text((7, y), line, f, color)


def alert(p, s, t):
    a = s["alert"]
    kind = a.get("kind", "message")
    app = a.get("app", "Phone")
    color = APP_COLOR.get(app.lower(), ACCENT)
    p.glow(lambda: p.ellipse((7, 8, 12, 13), fill=color), radius=3, strength=0.8)
    p.text((17, 4), app, font(10, "Bold"), color)
    if a.get("urgent"):
        k = 0.6 + 0.4 * math.sin(t * 2 * math.pi)
        f = font(8, "ExtraBold")
        w = p.length("URGENT", f) + 10
        p.glow(lambda: p.rrect((W - 6 - w, 5, W - 6, 16), 5.5, dim(RED, k)), radius=4, strength=0.7)
        p.text((W - 1 - w, 5), "URGENT", f, TEXT)
    fb = font(16, "Bold")
    title = p.wrap(a.get("sender", ""), fb, W - 14)
    keep = 3 if kind == "reminder" else 1
    if len(title) > keep:
        title = title[:keep]
        title[-1] = p.fit(title[-1] + " …", fb, W - 14)
    y = 26
    for line in title:
        p.text((7, y), p.fit(line, fb, W - 14), fb, TEXT)
        y += 20
    f = font(12, "Medium" if kind != "message" else "Regular")
    lines = p.wrap(a.get("text", ""), f, W - 14)
    rows = max(1, (H - 4 - y - 2) // 15)
    if len(lines) > rows:
        lines = lines[:rows]
        lines[-1] = p.fit(lines[-1] + " …", f, W - 14)
    for line in lines:
        p.text((7, y + 2), line, f, dim(TEXT, 0.75) if kind == "message" else MUTED)
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
