"""QuietDesk desk hardware: push-to-talk button, two status LEDs and the 1.5" RGB OLED.

Wiring (physical pin numbers):
  Button  : Pin 13 (GPIO27) and GND
  Green   : Pin 15 (GPIO22) -> 330 ohm -> LED -> GND   (listening / thinking)
  White   : Pin 16 (GPIO23) -> 330 ohm -> LED -> GND   (urgent notification waiting)
  OLED    : VCC Pin 1, GND Pin 6, DIN Pin 19, CLK Pin 23, CS Pin 24, DC Pin 22 (GPIO25), RST Pin 18 (GPIO24)

If the hardware or its libraries are missing, everything here quietly does nothing,
so the rest of QuietDesk still runs (for example on a laptop).
"""
import textwrap
import threading

STATE_TEXT = {"ready": "Ready", "listening": "Listening...", "thinking": "Thinking...", "speaking": "Speaking"}
MOOD_COLOR = {"happy": "yellow", "calm": "deepskyblue", "serious": "orangered", "neutral": "white"}


class Hardware:
    def __init__(self):
        self.ok = False
        self.button_down = False
        self.presses = 0  # goes up on every press, so the web page can spot new presses
        self._state = "ready"
        self._urgent = 0
        self._digest = 0
        self._reply = "Hold the button and talk."
        self._mood = "neutral"
        self._lock = threading.Lock()
        try:
            from gpiozero import LED, Button

            self.green = LED(22)
            self.white = LED(23)
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
        self._draw()

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
            self.white.on() if urgent else self.white.off()
        self._draw()

    def set_reply(self, text: str, mood: str = "neutral"):
        self._reply, self._mood = text or "", mood
        self._draw()

    # ---- OLED screen ----
    def _draw(self):
        if self.oled is None:
            return
        from luma.core.render import canvas

        with self._lock, canvas(self.oled) as d:
            d.text((4, 2), "QuietDesk", fill="white")
            d.text((4, 16), STATE_TEXT.get(self._state, self._state),
                   fill="lime" if self._state == "listening" else "cyan")
            d.line((0, 30, 127, 30), fill="gray")
            d.text((4, 35), f"Urgent: {self._urgent}", fill="orangered" if self._urgent else "gray")
            d.text((70, 35), f"Digest: {self._digest}", fill="white" if self._digest else "gray")
            d.line((0, 49, 127, 49), fill="gray")
            color = MOOD_COLOR.get(self._mood, "white")
            for i, line in enumerate(textwrap.wrap(self._reply, 20)[:6]):
                d.text((4, 54 + i * 12), line, fill=color)

    def close(self):
        if self.oled is not None:
            self.oled.clear()
        if self.ok:
            self.green.off()
            self.white.off()
