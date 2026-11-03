"""QuietDesk voice loop.

Push-to-talk -> record (arecord) -> Muse Voice Transcribe -> Muse Spark agent -> espeak-ng.

Run:
    .venv/bin/python voice.py                 # press Enter to start/stop talking
    .venv/bin/python voice.py --button        # use the GPIO27 push button (hold to talk)
    .venv/bin/python voice.py --file x.wav    # transcribe a WAV file once (for testing)
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).with_name(".env"))

from agent import Agent  # noqa: E402  (needs .env loaded first)

ASR_URL = "https://api.meta.ai/v1/asr/transcribe"
ASR_MODEL = "muse-voice-transcribe-1.0"
SAMPLE_RATE = 16000  # Muse Voice Transcribe wants mono 16-bit PCM WAV at 16 or 24 kHz
MIC_DEVICE = os.getenv("QUIETDESK_MIC", "")  # e.g. "plughw:2,0"; empty = ALSA default

led = None


def set_led(on: bool) -> None:
    if led is not None:
        led.on() if on else led.off()


def transcribe(wav_path: str) -> str:
    """Send a WAV file to Muse Voice Transcribe and return the text."""
    settings = {
        "model": ASR_MODEL,
        "mode": "PUSH_TO_TALK",
        "audioEncoding": "WAV",
        "languageBias": ["English"],
        "keywords": ["QuietDesk", "Lumi"],
    }
    # The key goes in through stdin so it never shows up in the process list.
    cmd = [
        "curl", "-sS", "--fail-with-body", "--max-time", "60",
        ASR_URL,
        "-H", "@-",
        "-F", f"request={json.dumps(settings)};type=application/json",
        "-F", f"audio=@{wav_path};type=audio/wav",
    ]
    header = f"Authorization: Bearer {os.environ['MODEL_API_KEY']}\n"
    result = subprocess.run(cmd, input=header, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Transcribe failed: {result.stdout or result.stderr}")
    return json.loads(result.stdout).get("transcript", "").strip()


def speak(text: str, mood: str = "neutral") -> None:
    """Say the reply with Meta MMS-TTS on the Pi (espeak-ng as backup)."""
    print(f"QuietDesk: {text}")
    import tts  # loaded here so web.py can import transcribe() without loading the voice model twice

    tts.play(text, mood)


def start_recording(wav_path: str) -> subprocess.Popen:
    cmd = ["arecord", "-q", "-f", "S16_LE", "-r", str(SAMPLE_RATE), "-c", "1", "-t", "wav"]
    if MIC_DEVICE:
        cmd += ["-D", MIC_DEVICE]
    return subprocess.Popen(cmd + [wav_path])


def stop_recording(proc: subprocess.Popen) -> None:
    proc.terminate()
    proc.wait()


def handle_audio(agent: Agent, wav_path: str) -> None:
    print("  transcribing...")
    text = transcribe(wav_path)
    if not text:
        speak("Sorry, I didn't catch that.")
        return
    print(f"You said: {text}")
    reply = agent.ask(text)
    speak(reply, agent.mood)


def loop_keyboard(agent: Agent) -> None:
    print("Press Enter to start talking, Enter again to stop. Type 'q' then Enter to quit.")
    while True:
        if input("\n[ready] ").strip().lower() == "q":
            return
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            wav = f.name
        proc = start_recording(wav)
        set_led(True)
        input("[recording... press Enter to stop] ")
        stop_recording(proc)
        set_led(False)
        try:
            handle_audio(agent, wav)
        except Exception as e:  # keep the loop alive during a demo
            print(f"  error: {e}")
            speak("Sorry, something went wrong.")
        finally:
            os.unlink(wav)


def loop_button(agent: Agent) -> None:
    from gpiozero import Button  # only needed on the Pi with the button wired

    button = Button(27)
    print("Hold the button to talk, release to send. Ctrl+C to quit.")
    while True:
        button.wait_for_press()
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            wav = f.name
        proc = start_recording(wav)
        set_led(True)
        button.wait_for_release()
        stop_recording(proc)
        set_led(False)
        try:
            handle_audio(agent, wav)
        except Exception as e:
            print(f"  error: {e}")
            speak("Sorry, something went wrong.")
        finally:
            os.unlink(wav)


def main() -> None:
    global led
    parser = argparse.ArgumentParser(description="QuietDesk voice loop")
    parser.add_argument("--button", action="store_true", help="use the GPIO27 push button")
    parser.add_argument("--file", help="transcribe this WAV file once and answer it")
    args = parser.parse_args()

    agent = Agent()

    if args.file:
        handle_audio(agent, args.file)
        return

    if args.button:
        from gpiozero import LED
        led = LED(22)
        loop_button(agent)
    else:
        loop_keyboard(agent)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
