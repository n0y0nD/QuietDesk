"""QuietDesk desk hardware: push-to-talk button, two status LEDs and the animated 1.5" RGB OLED face.

Wiring (physical pin numbers):
  Button  : Pin 13 (GPIO27) and GND
  Green   : Pin 15 (GPIO22) -> 330 ohm -> LED -> GND   (listening / thinking)
  Red     : Pin 16 (GPIO23) -> 330 ohm -> LED -> GND   (message light: steady when all is read,
                                                        breathes while messages wait, faster if urgent)
  OLED    : VCC Pin 1, GND Pin 6, DIN Pin 19, CLK Pin 23, CS Pin 24, DC Pin 22 (GPIO25), RST Pin 18 (GPIO24)

If the hardware or its libraries are missing, everything here quietly does nothing,
so the rest of QuietDesk still runs (for example on a laptop).
"""
import threading
import time

import screen

FPS = 30  # a frame takes ~3 ms to draw and send, so 30 fps is easy for the Pi
ALERT_SECONDS = {"urgent": 15, "digest": 8, "reminder": 30, "focus": 12}  # how long each card stays


class Hardware:
    def __init__(self):
        self.ok = False
        self.button_down = False
        self.presses = 0  # goes up on every press, so the web page can spot new presses
        self._state = "ready"
        self._urgent = 0
        self._digest = 0
        self._reply = ""
        self._mood = "neutral"
        self._reply_at = 0.0     # when the last reply arrived (it stays on screen for a while)
        self._alert = None       # new message card: dict(app, sender, text, urgent, until)
        self.info = None  # set by web.py: function returning phone, weather, reminder and focus details
        self._wake = threading.Event()
        self._running = True
        try:
            from gpiozero import LED, Button, PWMLED

            self.green = LED(22)
            self.red = PWMLED(23)  # PWM so it can fade in and out ("breathing")
            self.red.on()
            self.button = Button(27, bounce_time=0.05)
            self.button.when_pressed = self._pressed
            self.button.when_released = self._released
            self.ok = True
        except Exception as e:
            print(f"  hardware: GPIO not available ({e})")
        self.oled = None
        try:
            from luma.core.interface.serial import spi
            from luma.oled.device import ssd1351

            serial = spi(port=0, device=0, gpio_DC=25, gpio_RST=24, bus_speed_hz=16000000)
            self.oled = ssd1351(serial, width=128, height=128, bgr=True)
        except Exception as e:
            print(f"  hardware: OLED not available ({e})")
        if self.oled is not None:
            threading.Thread(target=self._screen_loop, daemon=True, name="oled").start()

    # ---- button ----
    def _pressed(self):
        self.button_down = True
        self.presses += 1
        self.set_state("listening")

    def _released(self):
        self.button_down = False

    # ---- status updates from the web console ----
    def set_state(self, state: str):
        self._state = state
        if self.ok:
            if state == "listening":
                self.green.on()
            elif state == "thinking":
                self.green.blink(on_time=0.15, off_time=0.15)
            else:
                self.green.off()
        self._draw()

    def set_counts(self, urgent: int, digest: int):
        if (urgent, digest) == (self._urgent, self._digest):
            return
        self._urgent, self._digest = urgent, digest
        if self.ok:
            if urgent:
                self.red.pulse(fade_in_time=0.5, fade_out_time=0.5)  # quick breath: something urgent waits
            elif digest:
                self.red.pulse(fade_in_time=1.5, fade_out_time=1.5)  # slow breath: messages for later
            else:
                self.red.on()  # all read: steady light
        self._draw()

    def set_reply(self, text: str, mood: str = "neutral"):
        """Show QuietDesk's answer with eyes in Muse Spark's mood; it stays until read, then the face returns."""
        self._reply, self._mood, self._reply_at = text or "", mood, time.monotonic()
        self._alert = None
        self._draw()

    def show_alert(self, app: str, sender: str, text: str, urgent: bool = False, kind: str = "message"):
        """A card for a few seconds: kind "message" (new phone message), "reminder" or "focus" (session ended)."""
        secs = ALERT_SECONDS[kind if kind != "message" else ("urgent" if urgent else "digest")]
        self._alert = dict(kind=kind, app=app, sender=sender, text=text, urgent=urgent,
                           until=time.monotonic() + secs)
        self._draw()

    # ---- OLED screen: animated, drawn by screen.py ----
    def _draw(self):
        self._wake.set()  # redraw now instead of waiting for the next frame

    def _snapshot(self) -> dict:
        now = time.monotonic()
        if self._alert and (now > self._alert["until"] or self._state == "listening"):
            self._alert = None
        words = len(self._reply.split())
        reply_secs = min(25, 5 + 0.45 * words)  # long enough to read it
        s = dict(self.info() or {}) if self.info else {}
        s.update(state=self._state, urgent=self._urgent, digest=self._digest,
                 mood=self._mood, reply=self._reply, reply_age=now - self._reply_at,
                 show_reply=bool(self._reply) and now - self._reply_at < reply_secs, alert=self._alert)
        return s

    def _screen_loop(self):
        start = time.monotonic()
        while self._running:
            try:
                self.oled.display(screen.render(self._snapshot(), time.monotonic() - start))
            except Exception as e:
                print(f"  hardware: screen error ({e})")
                time.sleep(1)
            self._wake.wait(1 / FPS)
            self._wake.clear()

    def close(self):
        self._running = False
        if self.oled is not None:
            time.sleep(2 / FPS)
            self.oled.clear()
        if self.ok:
            self.green.off()
            self.red.off()
