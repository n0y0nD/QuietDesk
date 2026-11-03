# QuietDesk

A voice-first AI companion on a Raspberry Pi 5 that helps you keep your phone out of reach during focused work, without missing anything important. Its voice and face are called **Lumi**.

Built for the **Meta Global AI Developer Hackathon 2026**.

## What I built during the hackathon, and what I used

All code in this repository was written during the hackathon (it started Oct 26; the first commit is Oct 30, 2026). Every AI model QuietDesk calls is a Meta model.

**Built during the hackathon (my work):**
- **Lumi, the agent**: Muse Spark with tool calling for notes, reminders, missed messages, reply drafts, focus sessions, auto-replies, focus score, phone music, focus sounds, find my phone and clearing notifications.
- **Message sorting**: each phone notification goes to Muse Spark, which decides urgent or digest and drafts a reply. Only messaging apps are sent, and OTPs and passwords are filtered out first.
- **The "yes" safety check, in code**: a reply goes out only after Lumi has read the draft aloud and you said yes in your next turn.
- **Focus sessions**: countdown, auto-replies (one per person, marked as auto-replies), the digest when focus ends, and the daily focus score.
- **The desk device**: wiring of the button, the two LEDs (one breathes while messages wait) and the OLED; Lumi's animated screens (face, clock, app logos, focus ring, alerts), drawn in code at 30 fps.
- **Phone integration code**: reading notifications, replying, clearing, ringing, music control and battery, all through KDE Connect's D-Bus interface.
- **The QuietDesk window** on the laptop: push-to-talk with the laptop mic, focus sounds made in code, and the live "Meta AI" panel; plus auto-start on the Pi and the laptop.

**Used, not built by me:**
- **Meta AI models**: Muse Spark and Muse Voice Transcribe (Meta Model API), and MMS-TTS (open-source Meta model, runs on the Pi).
- **Open-source software**: KDE Connect (phone link), PyTorch and transformers (to run MMS-TTS), Pillow and luma.oled (OLED drawing and driver), gpiozero (GPIO), dbus-python, python-dotenv, numpy, the `openai` client library (pointed at the Meta Model API), espeak-ng (backup voice), SQLite, the Nunito Sans font.
- **Services and platforms**: Open-Meteo (weather API), Raspberry Pi OS and systemd, Microsoft Edge (app window), the browser's Web Audio and built-in local voices, SSH.
- **Hardware**: Raspberry Pi 5, Waveshare 1.5" RGB OLED, button, LEDs, breadboard.

## What it does

- **Your real phone, sorted by Muse Spark.** WhatsApp, Instagram, Gmail and other messages arrive from your Android phone over Wi-Fi (KDE Connect). Muse Spark decides for each one: *urgent now* or *saved for the digest*, and drafts a reply.
- **Push to talk.** Hold the button on the desk and ask: "What did I miss?", "Remind me to call Mom at 6", "Start a 45 minute focus session". Muse Voice Transcribe turns speech into text; Muse Spark answers with tools.
- **Replies that need your yes.** Lumi reads a draft out loud and asks "Should I send it?". Only after you say yes does the reply go out from your phone (WhatsApp's own quick reply). Or edit and press "Approve & send" on the screen.
- **Focus sessions.** A glowing ring on the desk screen counts down. Only urgent messages interrupt. Lumi tells people who message you that you're busy until a set time (one short auto-reply each, marked as an auto-reply): Lumi asks first, or does it in every session if you switch that on. When the session ends, Lumi reads a digest and today's focus score.
- **A desk you can glance at.** An animated face with glowing eyes, the time, your next reminder, the logos of apps with unread messages, phone battery and weather. A red light breathes while messages wait (faster if urgent).
- **Reminders that ring** at their time, with a chime and a card on the screen.
- **Your phone, controlled from the desk.** "Where's my phone?" makes it ring, even on silent. "Clear all notifications" (or only one person's, or one app's) clears them from the desk and from the phone's notification bar. "Play music", "next song", "what's playing?" control the music app on the phone.
- **Focus sounds.** "Play rain sounds": rain, ocean waves or brown noise from the desk speaker, made live in code (no audio files). It gets quieter while Lumi talks, goes silent while you talk, and stops when the focus session ends.
- **Ask Lumi anything.** General questions get a short spoken answer, up to three sentences when you ask for an explanation. Lumi has no internet search, so it says so for live things like news or scores instead of guessing.
- **Every Meta AI call, live.** The "Meta AI, live" panel in the QuietDesk window lists each Meta model call as it happens: which model, what it was for, how long it took and how many tokens it used.

## Meta AI models (every AI model call in QuietDesk)

Every AI model in QuietDesk is a Meta model. The project calls no other AI model, local or cloud.

| Feature | Where it runs | Meta model |
|---|---|---|
| Agent brain "Lumi": answers and general questions, notes, reminders, focus sessions, reply drafts, choosing the right tool (phone music, focus sounds, find my phone, clearing notifications) | Meta Model API (Responses API) | `muse-spark-1.3` |
| Deciding which phone notifications are urgent, writing digests | Meta Model API (Responses API) | `muse-spark-1.3` |
| Writing focus auto-replies ("busy until 5:30 PM") | Meta Model API (Responses API) | `muse-spark-1.3` |
| Speech-to-text (push-to-talk voice input) | Meta Model API (Muse Voice Transcribe) | `muse-voice-transcribe-1.0` |
| Picking the mood of each spoken reply (happy, calm, serious, neutral) | Meta Model API (Responses API) | `muse-spark-1.3` |
| Text-to-speech option "Meta MMS-TTS (Pi)", tone set by that mood | On the Raspberry Pi, open-source | Meta MMS-TTS, `facebook/mms-tts-eng` |

## OS and system features (not AI models)

| Feature | What we use |
|---|---|
| Default voice in the web console | The browser's built-in **local** voice (on Windows: Microsoft David, Mark or Zira desktop voices). Not an AI model call. The page only offers local voices: online / "Natural" neural voices are filtered out in code. Rate and pitch follow Muse Spark's mood. |
| Backup voice on the Pi if MMS-TTS fails | `espeak-ng`, the built-in Linux system voice (rule-based, not an AI model) |
| Recording and playing audio | Browser mic and speakers on the laptop; ALSA / PipeWire on the Pi |
| Optional speaker on the Pi | Bluetooth speaker paired to the Pi (BlueZ), with `QUIETDESK_SPEAK_ON=pi` |
| Push-to-talk button and status LEDs (green: listening / thinking; red: steady when all is read, breathes while messages wait) | GPIO via `gpiozero` (software PWM for the breathing) |
| Desk screen (Lumi's animated face, 12-hour clock, app logos, focus ring, message cards) | Waveshare 1.5" RGB OLED over SPI, frames drawn with Pillow at 30 fps. App logos are simple shapes drawn in code. |
| Weather on the desk screen | [Open-Meteo](https://open-meteo.com/) weather API (free, no key, not an AI model); set `QUIETDESK_CITY` in `.env` |
| Phone battery on the desk screen | KDE Connect battery plugin |
| Notes, reminders, focus timer and focus score | SQLite and Python timers on the Pi; reminders ring at their time |
| Reading phone notifications and sending replies | [KDE Connect](https://kdeconnect.kde.org/) (open-source Android app + Linux daemon over Wi-Fi, no AI). QuietDesk reads it over D-Bus and replies through the phone app's own quick reply. A simulated phone on the web console is kept for testing, and its cards are labelled "simulated". |
| Find my phone, clearing notifications on the phone, phone music control | KDE Connect plugins over D-Bus: Find my phone, the notification's own dismiss, and the media remote (play, pause, next, previous, volume, now playing) |
| Focus sounds (rain, ocean, brown noise) | Web Audio API in the QuietDesk window: filtered random noise made live, no audio files, not an AI model |
| "Meta AI, live" panel | Every Meta model call is timed and its token count recorded on the Pi (`pi/metalog.py`), then shown in the QuietDesk window |
| Starting by itself | systemd user service on the Pi; a small Edge window on the laptop at sign-in |
| Calling the Meta Model API | `openai` Python SDK pointed at `https://api.meta.ai/v1` (client library only, no OpenAI models) |

QuietDesk needs an internet connection for Muse Spark and Muse Voice Transcribe. The MMS-TTS voice runs offline on the Pi. Pick the voice from the "Voice" menu at the top of the web console.

## Safety and privacy

- **Nothing is sent without your yes.** On screen you press "Approve & send". By voice, Lumi reads the draft and asks first; the check is in code (`agent.py`), not left to the model: the draft must have been read out in the previous reply, your answer must contain a yes and no "no", and a draft is never sent in the same turn it was written.
- **Auto-replies only with your consent**: Lumi asks when a focus session starts, or you turn them on for every session once with `QUIETDESK_FOCUS_AUTO_REPLY=on` (say "don't auto-reply" to skip one session). Only during focus, at most one per person, never to urgent messages, always marked "(auto-reply from Lumi)".
- **Only messaging apps reach the model** (`QUIETDESK_PHONE_APPS`), and anything that looks like an OTP or password is never sent to it.
- **Clearing is careful.** Lumi only clears notifications it received itself, never other apps' notifications. Before clearing one on the phone it checks that it is still the same sender, and it skips ones the phone won't let go (like an ongoing call).
- The web console only listens on the Pi itself; the laptop reaches it through an SSH tunnel.

## Project layout

```
pi/                        Python code that runs on the Raspberry Pi
start-desk.ps1             Laptop: keeps the tunnel open and runs the QuietDesk app window (mic + speaker)
install-desk-startup.ps1   Laptop: start QuietDesk at every Windows sign-in
install-app-shortcut.ps1   Laptop: "QuietDesk" shortcut on the Desktop and Start menu (opens the app window)
open-quietdesk-app.ps1     Laptop: what the shortcut runs (brings the window back, or starts QuietDesk)
```

The phone needs no custom app: it runs KDE Connect from the Play Store.

## Run it

**On the Pi** (Raspberry Pi OS trixie, Python 3.13), once:

```bash
cd ~/quietdesk
sudo apt install -y espeak-ng python3-gpiozero python3-lgpio python3-rpi-lgpio python3-spidev python3-dbus
sudo raspi-config nonint do_spi 0                     # turn on SPI for the OLED
python3 -m venv --system-site-packages .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/pip install torch==2.15.0 --index-url https://download.pytorch.org/whl/cpu
.venv/bin/pip install --no-deps luma.oled==3.16.0 luma.core==2.6.0 smbus2==0.4.3 cbor2
cp .env.example .env        # then paste your MODEL_API_KEY into .env (and QUIETDESK_CITY for weather)
.venv/bin/python test_api.py
./install-service.sh        # start QuietDesk now and at every boot (later: ./start-web.sh to restart, log in web.log)
```

**Real phone** (optional; without it the simulated phone on the web console still works):

1. On the Pi: `sudo apt install -y kdeconnect`. It runs in the Pi's desktop session, so the Pi should boot to the desktop.
2. On the Android phone: install **KDE Connect** from the Play Store, same Wi-Fi as the Pi.
3. Pair from the Pi (`kdeconnect-cli --list-available`, then `kdeconnect-cli --pair -d <device id>`) and accept on the phone.
4. In the phone app, open the Pi → **Notification sync** → allow notification access. Keep **Multimedia control receiver**, **Find my phone** and **Battery report** on too (music, ringing, battery). On phones that close background apps, allow KDE Connect to run in the background.
5. For music control, open your music app (Spotify, YouTube Music...) on the phone once.

`QUIETDESK_PHONE=off` in `.env` turns the phone link off.

**On the laptop** (Windows, with SSH key access to the Pi):

- QuietDesk app: run `start-desk.ps1`. It keeps the tunnel to the Pi open (and reconnects) and opens QuietDesk in its own app window (an Edge app window with QuietDesk's icon, no address bar), minimised. That window is QuietDesk's mic and speaker: press the button on the desk and talk. Click it in the taskbar to see the full console. The first time, click "Allow" for the microphone. Run `install-desk-startup.ps1` once to start it at every Windows sign-in, and `install-app-shortcut.ps1` once for a QuietDesk shortcut on the Desktop and Start menu.
- Or in any browser:

```bash
ssh -N -L 8000:localhost:8000 admin@raspberrypi5.local    # then open http://localhost:8000
```

Other ways to run it on the Pi:

```bash
.venv/bin/python agent.py            # text chat with Lumi in the terminal
.venv/bin/python voice.py --button   # push-to-talk with a USB mic on the Pi and the GPIO27 button
.venv/bin/python screen.py           # preview every desk screen as PNGs and a GIF
```

## How it works

| File | What it does |
|---|---|
| `pi/agent.py` | Lumi: Muse Spark with tool calling (notes, reminders, missed notifications, drafts, send after a yes, focus, auto-replies, focus score, phone music, focus sounds, find my phone, clearing notifications) |
| `pi/triage.py` | Muse Spark sorts each notification (urgent or digest, with a reply draft) and writes focus auto-replies |
| `pi/voice.py` | Muse Voice Transcribe (speech-to-text) |
| `pi/tts.py` | Meta MMS-TTS on the Pi with mood-based tone, espeak-ng as backup |
| `pi/phone.py` | Real phone link: new notifications from KDE Connect go to Muse Spark; approved replies go back through the phone; clearing, ringing, music control, phone battery |
| `pi/metalog.py` | Records every Meta model call (model, purpose, time, tokens) for the live panel |
| `pi/static/index.html` | The QuietDesk window: console, push-to-talk with the laptop mic, voices, focus sounds, the live Meta AI panel |
| `pi/web.py` | Web console and the desk's brain: push-to-talk, notifications, approve and send, reminders, focus, events for the laptop window |
| `pi/tools.py` | SQLite storage and the tool definitions |
| `pi/focus.py` | Focus sessions, auto-reply switch, one reply per person |
| `pi/hardware.py`, `pi/screen.py` | Button, LEDs, and Lumi's animated OLED screens (start-up, idle, focus, listening, thinking, reply, alerts) |
| `pi/weather.py` | Current weather for the desk screen (Open-Meteo) |

## Hardware

| Part | Wiring (physical pins) |
|---|---|
| Raspberry Pi 5 | |
| Waveshare 1.5" RGB OLED (SSD1351, SPI) | VCC 1, GND 6, DIN 19, CLK 23, CS 24, DC 22 (GPIO25), RST 18 (GPIO24) |
| Push-to-talk button | pin 13 (GPIO27) and GND |
| Green LED (listening / thinking) | pin 15 (GPIO22) → 330 Ω → LED → GND |
| Red LED (messages waiting) | pin 16 (GPIO23) → 330 Ω → LED → GND |
| Android phone | KDE Connect over the same Wi-Fi |
| Laptop | mic and speaker (desk window) |
| Optional | Bluetooth speaker on the Pi |

