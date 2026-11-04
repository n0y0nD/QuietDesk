"""QuietDesk voice on the Pi: SVOX Pico (default), Meta MMS-TTS, or espeak-ng as backup.

MMS-TTS only knows letters, so for it numbers and symbols are turned into words first.
"""
import io
import os
import queue
import re
import shutil
import subprocess
import tempfile
import threading
import wave

import metalog

# Which voice QuietDesk uses:
#   mms    = Meta MMS-TTS, open-source Meta model running on the Pi (male, default)
#   pico   = SVOX Pico, built-in system voice (female)
#   espeak = espeak-ng, built-in Linux voice
VOICE = os.getenv("QUIETDESK_TTS", "mms")

# Voice moods for MMS. Muse Spark picks one per reply (see agent.py).
#   pitch: 1.06 = about one semitone higher   rate: 1.1 = 10% faster
#   noise: more rise and fall in the voice     dur: more variation in word timing
#   pause: how long it stops at commas / full stops
# Tuned against a reference voice (pitch, pitch range and words per second measured per mood),
# keeping pitch shifts small so the voice doesn't sound like a cartoon.
MOODS = {
    "neutral": dict(pitch=1.10, rate=1.16, noise=0.65, dur=0.80, pause=(0.12, 0.25)),
    "happy":   dict(pitch=1.18, rate=1.21, noise=1.00, dur=0.90, pause=(0.10, 0.22)),
    "calm":    dict(pitch=1.02, rate=1.10, noise=0.60, dur=0.75, pause=(0.18, 0.35)),
    "serious": dict(pitch=1.05, rate=1.25, noise=0.40, dur=0.70, pause=(0.12, 0.25)),
}
PICO_LANG = os.getenv("QUIETDESK_PICO_LANG", "en-US")
MMS_MODEL = os.getenv("QUIETDESK_TTS_MODEL", "facebook/mms-tts-eng")
USE_MMS = VOICE == "mms"

_model = None
_tokenizer = None
_load_lock = threading.Lock()

ONES = "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen " \
       "sixteen seventeen eighteen nineteen".split()
TENS = "_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()


def number_words(n: int) -> str:
    if n < 20:
        return ONES[n]
    if n < 100:
        return TENS[n // 10] + ("" if n % 10 == 0 else " " + ONES[n % 10])
    if n < 1000:
        rest = n % 100
        return ONES[n // 100] + " hundred" + ("" if rest == 0 else " " + number_words(rest))
    if n < 100000:
        rest = n % 1000
        return number_words(n // 1000) + " thousand" + ("" if rest == 0 else " " + number_words(rest))
    if n < 10000000:
        rest = n % 100000
        return number_words(n // 100000) + " lakh" + ("" if rest == 0 else " " + number_words(rest))
    return " ".join(ONES[int(d)] for d in str(n))


def normalize(text: str) -> str:
    """Make text speakable for MMS-TTS: numbers, times and symbols become words."""
    t = text
    t = re.sub(r"(\d|\b(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve))\s*([ap])\.?m\b",
               r"\1 \2 m", t, flags=re.I)  # "5 pm" -> "5 p m", but "I am" stays
    t = re.sub(r"(\d{1,2}):(\d{2})", lambda m: number_words(int(m.group(1))) +
               ("" if m.group(2) == "00" else " " + (("oh " + ONES[int(m.group(2))]) if m.group(2)[0] == "0"
                                                    else number_words(int(m.group(2))))), t)
    t = re.sub(r"(\d),(?=\d)", r"\1", t)                       # 24,999 -> 24999
    t = re.sub(r"(?:\brs\.?|₹)\s*", "rupees ", t, flags=re.I)
    t = t.replace("%", " percent").replace("&", " and ").replace("@", " at ")
    t = re.sub(r"\d+", lambda m: number_words(int(m.group(0))) if len(m.group(0)) <= 7
               else " ".join(ONES[int(d)] for d in m.group(0)), t)
    t = re.sub(r"[—–]", ", ", t)
    t = re.sub(r"[^A-Za-z',.?! -]", " ", t)                    # drop emoji and anything MMS can't say
    return re.sub(r"\s+", " ", t).strip()


def _load():
    global _model, _tokenizer
    with _load_lock:
        if _model is None:
            import torch
            from transformers import AutoTokenizer, VitsModel

            torch.set_num_threads(4)
            _tokenizer = AutoTokenizer.from_pretrained(MMS_MODEL)
            _model = VitsModel.from_pretrained(MMS_MODEL).eval()
    return _model, _tokenizer


_synth_lock = threading.Lock()  # mood settings live on the shared model, so one synthesis at a time


MMS_RATE = 16000  # MMS-TTS output sample rate


def _mms_phrases(text: str, mood: str = "neutral"):
    """MMS-TTS with a mood, one phrase at a time (yields 16 kHz 16-bit PCM bytes per phrase).

    MMS ignores punctuation, so we speak phrase by phrase and add the pauses ourselves, and we
    raise or lower the pitch by resampling (the speaking rate is adjusted to make up for it).
    Yielding per phrase lets playback start as soon as the first phrase is ready."""
    import numpy as np
    import torch

    m = MOODS.get(mood, MOODS["neutral"])
    model, tokenizer = _load()
    for i, phrase in enumerate(p for p in re.split(r"(?<=[,;:.!?])\s+", text.strip()) if p):
        inputs = tokenizer(normalize(phrase), return_tensors="pt")
        if inputs["input_ids"].shape[-1] == 0:
            continue
        with _synth_lock:
            model.speaking_rate = m["rate"] / m["pitch"]  # resampling below speeds it up by `pitch`
            model.noise_scale = m["noise"]
            model.noise_scale_duration = m["dur"]
            torch.manual_seed(i)  # same text and mood, same voice every time
            with torch.no_grad():
                audio = model(**inputs).waveform[0].numpy()
        gap = m["pause"][1] if phrase[-1] in ".!?" else m["pause"][0]
        audio = np.concatenate([audio, np.zeros(int(MMS_RATE * gap * m["pitch"]), dtype=np.float32)])
        if m["pitch"] != 1.0:  # play the samples faster/slower = higher/lower voice
            n = len(audio)
            audio = np.interp(np.linspace(0, n - 1, int(n / m["pitch"])), np.arange(n), audio)
        yield (np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes()


def _mms_wav(text: str, mood: str = "neutral") -> bytes:
    with metalog.timed("facebook/mms-tts-eng", "Voice (on the Pi)") as t:  # live Meta AI panel
        pcm = b"".join(_mms_phrases(text, mood))
        t.detail = f"{len(pcm) / 2 / MMS_RATE:.1f} s of speech, {mood}"
    if not pcm:
        return b""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(MMS_RATE)
        w.writeframes(pcm)
    return buf.getvalue()


def _espeak_wav(text: str) -> bytes:
    if not shutil.which("espeak-ng"):
        return b""
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        path = f.name
    try:
        subprocess.run(["espeak-ng", "-v", "en-us", "-s", "160", "-w", path, text], check=True)
        with open(path, "rb") as f:
            return f.read()
    finally:
        os.unlink(path)


# Spellings that help the voice say names right (what it reads -> what it should hear).
PRONOUNCE = {"Priya": "Preeya", "QuietDesk": "Quiet Desk", "WhatsApp": "Whats App", "OTP": "O T P"}


def _pico_wav(text: str) -> bytes:
    """SVOX Pico: the built-in voice from older Android phones (not an AI model). Female, clear."""
    if not shutil.which("pico2wave"):
        return b""
    for word, say_as in PRONOUNCE.items():
        text = re.sub(rf"\b{word}\b", say_as, text)
    text = re.sub(r"[^\w\s,.?!'%:-]", " ", text)  # drop emoji
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        path = f.name
    try:
        subprocess.run(["pico2wave", "-l", PICO_LANG, "-w", path, text], check=True)
        with open(path, "rb") as f:
            return f.read()
    finally:
        os.unlink(path)


def wav_bytes(text: str, mood: str = "neutral") -> bytes:
    """Spoken reply as WAV bytes, using the voice picked in QUIETDESK_TTS; espeak-ng if that fails.
    `mood` (neutral, happy, calm, serious) changes the tone of the MMS voice."""
    if not text:
        return b""
    try:
        if VOICE == "pico":
            data = _pico_wav(text)
            if data:
                return data
        elif VOICE == "mms":
            return _mms_wav(text, mood)
    except Exception as e:
        print(f"  {VOICE} voice failed, using espeak-ng: {e}")
    return _espeak_wav(text)


def _play_wav(data: bytes) -> None:
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        f.write(data)
        path = f.name
    try:
        if shutil.which("pw-play"):
            subprocess.run(["pw-play", path])
        else:
            subprocess.run(["aplay", "-q", path])
    finally:
        os.unlink(path)


def _stream_mms(text: str, mood: str) -> None:
    """Play MMS speech as one continuous audio stream: phrase 1 plays while phrase 2 is generated."""
    ready = queue.Queue(maxsize=4)

    def produce():
        try:
            for pcm in _mms_phrases(text, mood):
                ready.put(pcm)
        finally:
            ready.put(None)

    threading.Thread(target=produce, daemon=True).start()
    # pw-cat in raw mode reads audio from stdin and plays it on the default (Bluetooth) speaker.
    cmd = ["pw-cat", "--playback", "--raw", "--rate", str(MMS_RATE), "--channels", "1", "--format", "s16", "-"]
    player = None
    try:
        while (pcm := ready.get()) is not None:
            if player is None:  # start the player only when there is sound to play
                player = subprocess.Popen(cmd, stdin=subprocess.PIPE)
            player.stdin.write(pcm)
            player.stdin.flush()
    finally:
        if player is not None:
            player.stdin.close()
            player.wait()


def play(text: str, mood: str = "neutral") -> None:
    """Speak on the Pi's own speaker (default audio output, e.g. the paired Bluetooth speaker).
    With MMS the reply is streamed phrase by phrase, so it starts after about one phrase of work."""
    if not text or not text.strip():
        return
    if VOICE == "mms":
        try:
            return _stream_mms(text, mood)
        except Exception as e:
            print(f"  MMS streaming failed, using espeak-ng: {e}")
            data = _espeak_wav(text)
    else:
        data = wav_bytes(text, mood)
    if data:
        _play_wav(data)


def _chime_wav() -> bytes:
    """A soft two-note "ding" (pure sine tones, made in code), played before alerts."""
    import math

    rate, notes = 22050, [(880.0, 0.0), (1318.5, 0.12)]  # A5 then E6, slightly overlapping
    length = int(rate * 0.75)
    samples = [0.0] * length
    for freq, start in notes:
        s0 = int(start * rate)
        for i in range(length - s0):
            t = i / rate
            env = math.exp(-t * 6.0) * min(1.0, t * 200)  # quick attack, gentle fade
            samples[s0 + i] += 0.35 * env * math.sin(2 * math.pi * freq * t)
    pcm = b"".join(int(max(-1, min(1, v)) * 32767).to_bytes(2, "little", signed=True) for v in samples)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    return buf.getvalue()


CHIME = _chime_wav()


def chime() -> None:
    _play_wav(CHIME)


def warm_up() -> None:
    """Load the model and run it once in the background, so the first real reply isn't slow.
    Not shown on the live Meta AI panel: it is a start-up step, not a reply."""
    if USE_MMS:
        threading.Thread(target=lambda: b"".join(_mms_phrases("QuietDesk is ready.")), daemon=True).start()


if __name__ == "__main__":
    import sys

    play(" ".join(sys.argv[1:]) or "Hello, I am QuietDesk. Mom sent an urgent message at 5:30 pm.")
