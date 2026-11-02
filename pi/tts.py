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

# Which voice QuietDesk uses:
#   mms    = Meta MMS-TTS, open-source Meta model running on the Pi (male, default)
#   pico   = SVOX Pico, built-in system voice (female)
#   espeak = espeak-ng, built-in Linux voice
VOICE = os.getenv("QUIETDESK_TTS", "mms")

# Voice moods for MMS. Muse Spark picks one per reply (see agent.py).
#   pitch: 1.06 = about one semitone higher   rate: 1.1 = 10% faster
#   noise: more rise and fall in the voice     dur: more variation in word timing
#   pause: how long it stops at commas / full stops
MOODS = {
    "neutral": dict(pitch=1.00, rate=1.05, noise=0.80, dur=0.85, pause=(0.18, 0.32)),
    "happy":   dict(pitch=1.07, rate=1.12, noise=0.95, dur=0.90, pause=(0.12, 0.25)),
    "calm":    dict(pitch=0.95, rate=0.90, noise=0.55, dur=0.70, pause=(0.25, 0.45)),
    "serious": dict(pitch=0.97, rate=1.00, noise=0.60, dur=0.75, pause=(0.20, 0.38)),
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


def _mms_wav(text: str, mood: str = "neutral") -> bytes:
    """MMS-TTS with a mood. MMS ignores punctuation, so we speak phrase by phrase and add pauses,
    and we raise or lower the pitch by resampling (the speaking rate is adjusted to make up for it)."""
    import numpy as np
    import torch

    m = MOODS.get(mood, MOODS["neutral"])
    model, tokenizer = _load()
    sr = model.config.sampling_rate
    parts = [p for p in re.split(r"(?<=[,;:.!?])\s+", text.strip()) if p]
    pieces = []
    with _synth_lock:
        model.speaking_rate = m["rate"] / m["pitch"]  # resampling below speeds it up by `pitch`
        model.noise_scale = m["noise"]
        model.noise_scale_duration = m["dur"]
        for i, phrase in enumerate(parts):
            inputs = tokenizer(normalize(phrase), return_tensors="pt")
            if inputs["input_ids"].shape[-1] == 0:
                continue
            torch.manual_seed(i)  # same text and mood, same voice every time
            with torch.no_grad():
                pieces.append(model(**inputs).waveform[0].numpy())
            gap = m["pause"][1] if phrase[-1] in ".!?" else m["pause"][0]
            pieces.append(np.zeros(int(sr * gap * m["pitch"]), dtype=np.float32))
    if not pieces:
        return b""
    audio = np.concatenate(pieces)
    if m["pitch"] != 1.0:  # play the samples faster/slower = higher/lower voice
        n = len(audio)
        audio = np.interp(np.linspace(0, n - 1, int(n / m["pitch"])), np.arange(n), audio).astype(np.float32)
    pcm = (audio.clip(-1, 1) * 32767).astype("<i2").tobytes()
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(model.config.sampling_rate)
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


def play(text: str, mood: str = "neutral") -> None:
    """Speak on the Pi's own speaker (default audio output, e.g. the paired Bluetooth speaker).

    Sentence by sentence: the first sentence starts playing while the next one is generated,
    so the user hears the reply sooner.
    """
    sentences = [s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s]
    if not sentences:
        return
    ready = queue.Queue(maxsize=2)

    def produce():
        for s in sentences:
            ready.put(wav_bytes(s, mood))
        ready.put(None)

    threading.Thread(target=produce, daemon=True).start()
    while (data := ready.get()) is not None:
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
    """Load the model and run it once in the background, so the first real reply isn't slow."""
    if USE_MMS:
        threading.Thread(target=lambda: wav_bytes("QuietDesk is ready."), daemon=True).start()


if __name__ == "__main__":
    import sys

    play(" ".join(sys.argv[1:]) or "Hello, I am QuietDesk. Mom sent an urgent message at 5:30 pm.")
