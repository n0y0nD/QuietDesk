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
| Text-to-speech (QuietDesk's voice), tone set by that mood | On the Raspberry Pi, open-source | Meta MMS-TTS, `facebook/mms-tts-eng` |

## OS and system features (not AI models)

| Feature | What we use |
|---|---|
| Backup voice if MMS-TTS is off or fails | `espeak-ng`, the built-in Linux system voice (rule-based, not an AI model) |
| Recording and playing audio | ALSA / PipeWire on Raspberry Pi OS |
| Speaker | Bluetooth speaker paired to the Pi (BlueZ) |
| Push-to-talk button and status LED | GPIO via `gpiozero` |
| Status screen | Waveshare 1.5" RGB OLED over SPI |
| Notes and reminders storage | SQLite |
| Reading phone notifications | Android `NotificationListenerService` (OS API, no AI in the app); a simulated phone on the web console for the demo |
| Mic for the web console | The browser's own mic (no AI) |
| Calling the Meta Model API | `openai` Python SDK pointed at `https://api.meta.ai/v1` (client library only, no OpenAI models) |

QuietDesk needs an internet connection for Muse Spark and Muse Voice Transcribe. The MMS-TTS voice runs offline on the Pi.

## Project layout

```
pi/        Python code that runs on the Raspberry Pi
android/   Companion app that relays phone notifications (coming soon)
```

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
| `pi/web.py` | Web console on the Pi; the page stands in for the phone app in the demo |
| `pi/tools.py` | SQLite storage and the tool definitions |

The agent can draft replies but can never send them. Every reply waits on the screen until the user approves it.

## Hardware

Raspberry Pi 5, Waveshare 1.5" RGB OLED (SPI), Bluetooth speaker (boAt Stone 350 Pro), push-to-talk button, two status LEDs. The laptop browser is the mic for now. `QuietDesk_Components_List.pdf` has the original parts list.
