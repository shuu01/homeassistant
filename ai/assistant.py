import io
import os
import queue
import time

import numpy as np
import sounddevice as sd
import soundfile as sf
from scipy.io.wavfile import write
from scipy.signal import resample_poly

import requests
from google import genai
from openwakeword.model import Model

# ---------- CONFIG ----------

MIC_RATE = 48000
RATE = 16000
WAKE_THRESHOLD = 0.3
CONVERSATION_IDLE_TIMEOUT = 20
MAX_RECORD_SECONDS = 30
SILENCE_TIMEOUT_SECONDS = 2

WHISPER_SERVER = os.getenv(
    "WHISPER_SERVER",
    "http://whisper:8080",
)
VOICE_SERVER = os.getenv(
    "VOICE_SERVER",
    "http://voice:8080",
)

SYSTEM_PROMPT = """
You are Alexa, a friendly companion for a 4 years old child.

Keep responses short.
Be cheerful and encouraging.
Tell stories when asked.
Never be scary.
"""

client = genai.Client(
    api_key=os.getenv("GEMINI_API_KEY")
)

print("Loading wake word model...")
wake_model = Model()

audio_queue = queue.Queue(maxsize=100)
is_speaking = False


def flush_queue():
    while True:
        try:
            audio_queue.get_nowait()
        except queue.Empty:
            break


def callback(indata, frames, time_info, status):
    if is_speaking:
        return

    try:
        audio_16k = resample_poly(
            indata.flatten(),
            up=1,
            down=3,
        ).astype(np.int16)

        audio_queue.put_nowait(audio_16k)

    except queue.Full:
        pass


def speak(text):
    global is_speaking
    print(f"Daisy: {text}")

    r = requests.post(
        f"{VOICE_SERVER}/synthesize",
        json={
            "text": text,
        },
        timeout=30,
    )

    r.raise_for_status()

    audio, sample_rate = sf.read(
        io.BytesIO(r.content),
        dtype="float32",
    )

    is_speaking = True
    try:
        sd.play(audio, sample_rate)
        sd.wait()
    finally:
        is_speaking = False
        flush_queue()


def record_question():
    chunks = []

    start = time.time()
    last_voice = time.time()

    while True:
        chunk = audio_queue.get(timeout=5)

        chunks.append(chunk)

        volume = np.abs(chunk).mean()

        if volume > 200:
            last_voice = time.time()

        if time.time() - last_voice > SILENCE_TIMEOUT_SECONDS:
            break

        if time.time() - start > MAX_RECORD_SECONDS:
            break

    audio = np.concatenate(chunks, axis=0)
    wav_buffer = io.BytesIO()
    write(wav_buffer, RATE, audio)
    wav_buffer.seek(0)

    return wav_buffer


def transcribe(wav_buffer):
    try:
        files = {
            "file": (
                "audio.wav",
                wav_buffer,
                "audio/wav",
            )
        }

        response = requests.post(
            f"{WHISPER_SERVER}/inference",
            files=files,
            timeout=60,
        )

        response.raise_for_status()
        data = response.json()
        return data.get("text", "").strip()


def ask_gemini(text):
    response = client.models.generate_content(
        model="gemini-3-flash",
        contents=f"{SYSTEM_PROMPT}\n\nChild: {text}"
    )

    return response.text.strip()


def wait_for_service(name, url):
    while True:
        try:
            response = requests.get(
                f"{url}/health",
                timeout=2,
            )
            response.raise_for_status()
            print(f"{name} ready")
            return
        except Exception:
            print(f"waiting for {name}...")
            time.sleep(5)

# ---------- MAIN ----------

wait_for_service("whisper", WHISPER_SERVER)
wait_for_service("voice", VOICE_SERVER)
print("Default device:", sd.default.device)
print(sd.query_devices(sd.default.device[0]))
print("Listening for wake word...")

with sd.InputStream(
    device=4,
    samplerate=MIC_RATE,
    channels=1,
    dtype="int16",
    blocksize=3840,
    callback=callback,
) as stream:

    print("Actual sample rate:", stream.samplerate)

    while True:

        audio = audio_queue.get()
        prediction = wake_model.predict(audio)
        score = max(prediction.values(), default=0)

        if score > 0.1:
            print(prediction)

        if score < WAKE_THRESHOLD:
            continue

        print("Wake word detected")
        speak("Hi! What would you like to talk about?")

        last_activity = time.time()

        while True:
            if time.time() - last_activity > 20:
                break

            wav_buffer = record_question()

            try:
                text = transcribe(wav_buffer)
            except Exception as e:
                print(f"Whisper failed: {e}")
                continue

            if not text:
                continue

            last_activity = time.time()

            print(f"Child: {text}")

            try:
                answer = ask_gemini(text)
            except Exception as e:
                print("Answer failed {e}")

            speak(answer)

            last_activity = time.time()

        print("Returning to sleep...")
