# QuietDesk

A voice-first AI companion on a Raspberry Pi 5 that helps you keep your phone out of reach during focused work, without missing anything important.

Built for the **Meta Global AI Developer Hackathon 2026**.

## Meta AI models (every AI model call in QuietDesk)

All AI in QuietDesk runs on the Meta Model API. The project calls no other AI model, local or cloud.

| Feature | Meta API | Model |
|---|---|---|
| Agent brain: answers, notes, reminders, reply drafts (tool calling) | Responses API | `muse-spark-1.3` |
| Deciding which phone notifications are urgent, writing digests | Responses API | `muse-spark-1.3` |
| Speech-to-text (push-to-talk voice input) | Muse Voice Transcribe | `muse-voice-transcribe-1.0` |

## OS and system features (not AI models)

| Feature | What we use |
|---|---|
| Speaking replies aloud | `espeak-ng`, the built-in Linux system voice (rule-based, not an AI model) |
| Recording and playing audio | ALSA on Raspberry Pi OS |
| Push-to-talk button and status LED | GPIO via `gpiozero` |
| E-ink screen | Waveshare driver over SPI |
| Notes and reminders storage | SQLite |
| Reading phone notifications | Android `NotificationListenerService` (OS API, no AI in the app) |
| Calling the Meta Model API | `openai` Python SDK pointed at `https://api.meta.ai/v1` (client library only, no OpenAI models) |

QuietDesk needs an internet connection, since all AI runs through the Meta Model API.

## Project layout

```
pi/        Python code that runs on the Raspberry Pi
android/   Companion app that relays phone notifications (coming soon)
```

## Run the agent on the Pi

```bash
cd ~/quietdesk
cp .env.example .env        # then paste your MODEL_API_KEY into .env
.venv/bin/python test_api.py
.venv/bin/python agent.py
```

## Hardware

Raspberry Pi 5, Waveshare 2.9" e-ink (SPI), MAX98357A I2S amp + speaker, USB mic, push button, status LED. See `QuietDesk_Components_List.pdf` for the full list and wiring pins.
