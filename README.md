# QuietDesk

A voice-first AI companion on a Raspberry Pi 5 that helps you keep your phone out of reach during focused work, without missing anything important.

Built for the **Meta Global AI Developer Hackathon 2026**.

## Meta AI models (every AI model call in QuietDesk)

Every AI model in QuietDesk is a Meta model. The project calls no other AI model, local or cloud.

| Feature | Where it runs | Meta model |
|---|---|---|
| Agent brain: answers, notes, reminders, reply drafts (tool calling) | Meta Model API (Responses API) | `muse-spark-1.3` |
| Deciding which phone notifications are urgent, writing digests | Meta Model API (Responses API) | `muse-spark-1.3` |
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
| Push-to-talk button and status LEDs | GPIO via `gpiozero` |
| Status screen | Waveshare 1.5" RGB OLED over SPI |
| Notes and reminders storage | SQLite |
| Reading phone notifications and sending replies | [KDE Connect](https://kdeconnect.kde.org/) (open-source Android app + Linux daemon over Wi-Fi, no AI). QuietDesk reads it over D-Bus and replies through the phone app's own quick reply. A simulated phone on the web console is kept for testing, and its cards are labelled "simulated". |
| Mic for the web console | The browser's own mic (no AI) |
| Calling the Meta Model API | `openai` Python SDK pointed at `https://api.meta.ai/v1` (client library only, no OpenAI models) |

QuietDesk needs an internet connection for Muse Spark and Muse Voice Transcribe. The MMS-TTS voice runs offline on the Pi. Pick the voice from the "Voice" menu at the top of the web console.

## Project layout

```
pi/        Python code that runs on the Raspberry Pi
```

The phone needs no custom app: it runs KDE Connect from the Play Store.

## Run it

On the Pi, once:

```bash
cd ~/quietdesk
cp .env.example .env        # then paste your MODEL_API_KEY into .env
sudo apt install -y espeak-ng
.venv/bin/pip install openai python-dotenv transformers numpy
.venv/bin/pip install torch --index-url https://download.pytorch.org/whl/cpu
.venv/bin/python test_api.py
```

Real phone notifications (optional; without it the simulated phone still works):

1. On the Pi: `sudo apt install -y kdeconnect`. It runs in the Pi's desktop session, so the Pi should boot to the desktop.
2. On the Android phone: install **KDE Connect** from the Play Store, same Wi-Fi as the Pi.
3. Pair from the Pi (`kdeconnect-cli --list-available`, then `kdeconnect-cli --pair -d <device id>`) and accept on the phone.
4. In the phone app, open the Pi → **Notification sync** → allow notification access. On phones that close background apps, allow KDE Connect to run in the background.

Only messaging apps are passed on (`QUIETDESK_PHONE_APPS` in `.env`, default WhatsApp, Messages, Telegram, Signal, Slack, Discord, Gmail, Instagram), and anything that looks like an OTP or password is never sent to the model. `QUIETDESK_PHONE=off` turns the phone link off.

Web console (voice + notifications). The laptop browser is the mic and speaker; all AI runs on the Pi. From the laptop, run `open-quietdesk.ps1`, or by hand:

```bash
ssh admin@raspberrypi5.local "~/quietdesk/start-web.sh"
ssh -N -L 8000:localhost:8000 admin@raspberrypi5.local    # then open http://localhost:8000
```

Other ways to run it on the Pi:

```bash
.venv/bin/python agent.py            # text chat in the terminal
.venv/bin/python voice.py            # push-to-talk with a USB mic on the Pi
.venv/bin/python voice.py --button   # same, with the GPIO27 button
```

## How it works

| File | What it does |
|---|---|
| `pi/agent.py` | Muse Spark agent with tool calling (notes, reminders, missed notifications, reply drafts) |
| `pi/triage.py` | Muse Spark sorts each notification: urgent now or saved for the digest, plus a reply draft |
| `pi/voice.py` | Push-to-talk: record → Muse Voice Transcribe → agent → spoken reply |
| `pi/tts.py` | QuietDesk's voice: Meta MMS-TTS on the Pi, espeak-ng as backup |
| `pi/phone.py` | Real phone link: new notifications from KDE Connect go to Muse Spark; approved replies go back through the phone |
| `pi/web.py` | Web console on the Pi: push-to-talk, the phone's notifications, approve and send |
| `pi/tools.py` | SQLite storage and the tool definitions |

Nothing is sent without the user's yes. A reply goes out in one of two ways:

- **On screen:** the user edits the draft and presses "Approve & send".
- **By voice:** QuietDesk reads the draft out loud and asks "Should I send it?", then sends only if the user's next words say yes. That check is in code (`agent.py`), not left to the model: the draft must have been read out in the previous reply, the answer must contain a yes and no "no", and a draft can never be sent in the same turn it was written.

## Hardware

Raspberry Pi 5, Waveshare 1.5" RGB OLED (SPI), Bluetooth speaker (boAt Stone 350 Pro), push-to-talk button, two status LEDs, and the user's Android phone (KDE Connect). The laptop browser is the mic for now. `QuietDesk_Components_List.pdf` has the original parts list.
