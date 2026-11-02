"""QuietDesk voice: Meta MMS-TTS (open-source Meta model) running on the Pi, espeak-ng as backup.

MMS-TTS only knows letters, so numbers and symbols are turned into words first.
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

MMS_MODEL = os.getenv("QUIETDESK_TTS_MODEL", "facebook/mms-tts-eng")
USE_MMS = os.getenv("QUIETDESK_TTS", "mms") == "mms"

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


def _mms_wav(text: str) -> bytes:
    import torch

    model, tokenizer = _load()
    inputs = tokenizer(normalize(text), return_tensors="pt")
    if inputs["input_ids"].shape[-1] == 0:
        return b""
    torch.manual_seed(0)  # same text, same voice every time
    with torch.no_grad():
        audio = model(**inputs).waveform[0].numpy()
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


def wav_bytes(text: str) -> bytes:
    """Spoken reply as WAV bytes. Meta MMS-TTS first, espeak-ng if MMS is off or fails."""
    if not text:
        return b""
    if USE_MMS:
        try:
            return _mms_wav(text)
        except Exception as e:
            print(f"  MMS-TTS failed, using espeak-ng: {e}")
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


def play(text: str) -> None:
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
            ready.put(wav_bytes(s))
        ready.put(None)

    threading.Thread(target=produce, daemon=True).start()
    while (data := ready.get()) is not None:
        if data:
            _play_wav(data)


def warm_up() -> None:
    """Load the model and run it once in the background, so the first real reply isn't slow."""
    if USE_MMS:
        threading.Thread(target=lambda: wav_bytes("QuietDesk is ready."), daemon=True).start()


if __name__ == "__main__":
    import sys

    play(" ".join(sys.argv[1:]) or "Hello, I am QuietDesk. Mom sent an urgent message at 5:30 pm.")
