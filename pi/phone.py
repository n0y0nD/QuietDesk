"""Real phone notifications through KDE Connect (open-source app + Linux daemon, no AI in it).

The phone runs the KDE Connect Android app, the Pi runs the kdeconnect daemon, both on the same Wi-Fi.
The daemon mirrors the phone's notifications onto the Pi's D-Bus; this file reads them, hands each new
one to QuietDesk (Muse Spark sorts it), and sends a reply back through the phone when the user approves.

Run on its own to watch notifications arrive:   .venv/bin/python phone.py
"""
import os
import re
import threading
import time

# The daemon lives on the desktop user's session bus. When QuietDesk is started over SSH that
# address is not set, so point at the standard one.
os.environ.setdefault("DBUS_SESSION_BUS_ADDRESS", f"unix:path=/run/user/{os.getuid()}/bus")

SERVICE = "org.kde.kdeconnect"
DAEMON_PATH = "/modules/kdeconnect"
DEVICE_IFACE = "org.kde.kdeconnect.device"
NOTIFS_IFACE = "org.kde.kdeconnect.device.notifications"
PROPS_IFACE = "org.freedesktop.DBus.Properties"
POLL_SECONDS = 1.5

# Only these apps reach QuietDesk (and Muse Spark). Set QUIETDESK_PHONE_APPS=all to allow every app.
APPS = os.getenv("QUIETDESK_PHONE_APPS",
                 "WhatsApp,WhatsApp Business,Messages,Telegram,Signal,Slack,Discord,Gmail,Instagram")
ALLOWED = None if APPS.strip().lower() == "all" else {a.strip().lower() for a in APPS.split(",") if a.strip()}

# Never forward one-time codes or passwords to the cloud model.
PRIVATE = re.compile(r"\b(otp|one[- ]time|verification code|passcode|password|cvv)\b", re.I)

# Summary lines like "5 new messages" or "3 messages from 2 chats" carry no message.
SUMMARY = re.compile(r"^\d+ (new )?messages?( from \d+ chats?)?$", re.I)


class Phone:
    """Watches the paired phone. `on_notification(app, sender, text, phone_id, reply_id)` is called
    for every new message; `reply(reply_id, text)` answers one on the phone."""

    def __init__(self, on_notification=None):
        self.on_notification = on_notification or (lambda *a: print("  phone:", a))
        self.device = None      # KDE Connect device id of the phone
        self.name = None        # e.g. "realme C21 Y"
        self.connected = False
        self._seen = {}         # phone notification id -> (title, text) already handled
        self._primed = False    # notifications already on the phone at start are not re-announced
        self._bus = None
        self._error = None
        self._sent = []         # replies we sent: WhatsApp echoes them back as "You: ..."
        self.battery = None     # phone battery %, read every few seconds
        self.charging = False
        self._battery_at = 0.0

    # ---- D-Bus helpers ----
    def _obj(self, path):
        return self._bus.get_object(SERVICE, path, introspect=False)  # no log spam while the phone is away

    def _find_phone(self):
        """First paired phone that is reachable right now, or None."""
        import dbus

        daemon = self._obj(DAEMON_PATH)
        for dev in daemon.devices(True, True, dbus_interface="org.kde.kdeconnect.daemon"):
            props = self._obj(f"{DAEMON_PATH}/devices/{dev}")
            try:
                self.name = str(props.Get(DEVICE_IFACE, "name", dbus_interface=PROPS_IFACE))
            except dbus.DBusException:
                self.name = str(dev)
            return str(dev)
        return None

    def _notification(self, pid: str) -> dict:
        obj = self._obj(f"{DAEMON_PATH}/devices/{self.device}/notifications/{pid}")
        return {str(k): v for k, v in obj.GetAll("", dbus_interface=PROPS_IFACE).items()}

    # ---- main loop ----
    def start(self) -> "Phone":
        threading.Thread(target=self._run, daemon=True, name="phone").start()
        return self

    def _run(self):
        import dbus

        while True:
            try:
                if self._bus is None:
                    self._bus = dbus.SessionBus()
                self.device = self._find_phone()
                self.connected = self.device is not None
                if self.connected:
                    self._poll()
                    if time.time() - self._battery_at > 20:
                        self._read_battery()
                    self._error = None
            except dbus.DBusException as e:  # daemon restarted or phone left the Wi-Fi: try again
                self.connected = False
                self._bus = None
                if str(e) != self._error:
                    print(f"  phone: {e.get_dbus_message() or e}")
                    self._error = str(e)
            except Exception as e:
                print(f"  phone error: {e}")
            time.sleep(POLL_SECONDS)

    def _poll(self):
        notifs = self._obj(f"{DAEMON_PATH}/devices/{self.device}/notifications")
        ids = [str(i) for i in notifs.activeNotifications(dbus_interface=NOTIFS_IFACE)]
        for pid in ids:
            n = self._notification(pid)
            app = str(n.get("appName", "")).strip()
            sender = str(n.get("title", "")).strip()
            text = str(n.get("text", "")).strip()
            key = (sender, text)
            if self._seen.get(pid) == key:
                continue  # nothing new in this one
            self._seen[pid] = key
            if not self._primed or not self._wanted(app, sender, text) or text in self._sent:
                continue
            print(f"  phone: {app} / {sender}: {text[:60]}")
            self.on_notification(app or "Phone", sender or app or "Unknown", text[:600],
                                 pid, str(n.get("replyId", "") or ""))
        self._primed = True
        for pid in set(self._seen) - set(ids):  # forget notifications cleared on the phone
            del self._seen[pid]

    @staticmethod
    def _wanted(app: str, sender: str, text: str) -> bool:
        if not text or SUMMARY.match(text) or app.lower() == "kde connect":
            return False
        if sender.lower() in ("you", "me"):  # the user's own message (e.g. after replying)
            return False
        if ALLOWED is not None and app.lower() not in ALLOWED:
            return False
        return not PRIVATE.search(f"{sender} {text}")

    # ---- replying ----
    def reply(self, reply_id: str, text: str) -> None:
        """Send `text` as the reply to a phone notification (the phone's own quick-reply, e.g. WhatsApp)."""
        if not (self.connected and self.device):
            raise RuntimeError("The phone is not connected (open KDE Connect on the phone, same Wi-Fi).")
        notifs = self._obj(f"{DAEMON_PATH}/devices/{self.device}/notifications")
        notifs.sendReply(reply_id, text, dbus_interface=NOTIFS_IFACE)
        self._sent = (self._sent + [text])[-10:]

    def ring(self) -> None:
        """Make the phone ring loudly (KDE Connect "Find my phone"), even if it is on silent."""
        if not (self.connected and self.device):
            raise RuntimeError("The phone is not connected (open KDE Connect on the phone, same Wi-Fi).")
        self._obj(f"{DAEMON_PATH}/devices/{self.device}/findmyphone").ring(
            dbus_interface="org.kde.kdeconnect.device.findmyphone")

    def _read_battery(self):
        import dbus

        self._battery_at = time.time()
        try:
            b = self._obj(f"{DAEMON_PATH}/devices/{self.device}/battery")
            props = b.GetAll("org.kde.kdeconnect.device.battery", dbus_interface=PROPS_IFACE)
            charge = int(props.get("charge", -1))
            self.battery = charge if 0 <= charge <= 100 else None
            self.charging = bool(props.get("isCharging", False))
        except dbus.DBusException:
            self.battery = None  # battery plugin off on the phone

    def status(self) -> dict:
        on = self.connected
        return {"connected": on, "name": self.name if on else None,
                "battery": self.battery if on else None, "charging": self.charging and on}


if __name__ == "__main__":
    p = Phone().start()
    print("Watching phone notifications (Ctrl+C to stop)...")
    try:
        while True:
            time.sleep(5)
    except KeyboardInterrupt:
        pass
