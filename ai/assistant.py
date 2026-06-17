import os
import queue
import tempfile
import subprocess
import time

import numpy as np
import sounddevice as sd
from scipy.io.wavfile import write

import requests
from google import genai
from openwakeword.model import Model

# ---------- CONFIG ----------

RATE = 16000
WAKE_THRESHOLD = 0.5
CONVERSATION_IDLE_TIMEOUT = 20
MAX_RECORD_SECONDS = 30
SILENCE_TIMEOUT_SECONDS = 2

WHISPER_SERVER = os.getenv(
    "WHISPER_SERVER",
    "http://whisper:80",
)
PIPER_SERVER = os.getenv(
    "PIPER_SERVER",
    "http://piper:80",
)
#PIPER_MODEL = "/home/ha/piper/en_US-lessac-medium.onnx"

SYSTEM_PROMPT = """
You are Daisy, a friendly companion for a child.

Keep responses short.
Be cheerful and encouraging.
Tell stories when asked.
Never be scary.
"""

# ---------- GEMINI ----------

client = genai.Client(
    api_key=os.getenv("GEMINI_API_KEY")
)

# ---------- WAKEWORD ----------

print("Loading wake word model...")
wake_model = Model(
    inference_framework="onnx"
)

# ---------- AUDIO ----------

audio_queue = queue.Queue()

def callback(indata, frames, time_info, status):
    audio_queue.put(indata.copy())

# ---------- SPEAK ----------

def speak(text):

    print(f"Daisy: {text}")

    r = requests.post(
        "http://piper:8080/synthesize",
        json={
            "text": answer,
        },
        timeout=30,
    )

    r.raise_for_status()

    with open("/tmp/reply.wav", "wb") as f:
        f.write(r.content)

    # piper = subprocess.Popen(
    #     [
    #         "piper",
    #         "--model",
    #         PIPER_MODEL,
    #         "--output-raw",
    #     ],
    #     stdin=subprocess.PIPE,
    #     stdout=subprocess.PIPE,
    # )

    #audio_data, _ = piper.communicate(text.encode())

    # aplay = subprocess.Popen(
    #     [
    #         "aplay",
    #         "-r", "22050",
    #         "-f", "S16_LE",
    #         "-t", "raw",
    #     ],
    #     stdin=subprocess.PIPE,
    # )

    # aplay.communicate(audio_data)

# ---------- RECORD QUESTION ----------

def record_question():
    chunks = []

    start = time.time()
    last_voice = time.time()

    while True:
        chunk = audio_queue.get()

        chunks.append(chunk)

        volume = np.abs(chunk).mean()

        if volume > 200:
            last_voice = time.time()

        if time.time() - last_voice > SILENCE_TIMEOUT_SECONDS:
            break

        if time.time() - start > MAX_RECORD_SECONDS:
            break

    audio = np.concatenate(chunks, axis=0)

    with tempfile.NamedTemporaryFile(
        suffix=".wav",
        delete=False,
    ) as f:
        write(f.name, RATE, audio)
        return f.name

# ---------- TRANSCRIBE ----------

def transcribe(path):
    with open(path, "rb") as f:
        files = {
            "file": ("audio.wav", f, "audio/wav")
        }

        response = requests.post(
            f"{WHISPER_SERVER}/inference",
            files=files,
            timeout=60,
        )

    response.raise_for_status()

    os.unlink(path)

    data = response.json()

    return data.get("text", "").strip()

# ---------- ASK GEMINI ----------

def ask_gemini(text):
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=f"{SYSTEM_PROMPT}\n\nChild: {text}"
    )

    return response.text.strip()

def wait_for_whisper():
    while True:
        try:
            requests.get(
                f"{WHISPER_SERVER}/health",
                timeout=2,
            )
            print("whisper-server ready")
            return
        except Exception:
            print("waiting for whisper-server...")
            time.sleep(5)

# ---------- MAIN ----------

wait_for_whisper()
print("Listening for wake word...")

with sd.InputStream(
    samplerate=RATE,
    channels=1,
    dtype="int16",
    blocksize=1280,
    callback=callback,
):

    while True:

        audio = audio_queue.get()

        prediction = wake_model.predict(audio)

        score = max(prediction.values())

        if score < WAKE_THRESHOLD:
            continue

        print("Wake word detected")

        speak("Hi! What would you like to talk about?")

        conversation_deadline = time.time() + 20
        last_activity = time.time()

        while True:
            if time.time() - last_activity > 20:
            break

            wav_path = record_question()

            text = transcribe(wav_path)

            if not text:
                continue

            last_activity = time.time()

            print(f"Child: {text}")

            answer = ask_gemini(text)

            speak(answer)

            last_activity = time.time()

        print("Returning to sleep...")
