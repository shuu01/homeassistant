import io
import os
import time

import numpy as np
import sounddevice as sd
import soundfile as sf
from scipy.io.wavfile import write
from scipy.signal import resample_poly
from dataclasses import dataclass

import requests
from google import genai
from groq import Groq
from openai import OpenAI
from openwakeword.model import Model

MIC_RATE = 48000
OUTPUT_RATE = 48000
RATE = 16000
AUDIO_DEVICE = int(os.getenv("AUDIO_DEVICE", "4"))
WAKE_THRESHOLD = float(os.getenv("WAKE_THRESHOLD", "0.5"))
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

SYSTEM_PROMPT = os.getenv("SYSTEM_PROMPT", """
You are Alexa, a friendly companion for a 4 years old child.

Keep responses short.
Be cheerful and encouraging.
Tell stories when asked.
Never be scary.
No emojis in responses.
""")

STATE_SLEEP = "sleep"
STATE_RECORD = "record"
providers = []
current_provider = 0


@dataclass
class Provider:
    name: str
    client: object
    fn: callable
    model: str


def speak(text):
    print(f"Assistant: {text}")

    response = requests.post(
        f"{VOICE_SERVER}/synthesize",
        json={
            "text": text,
            "voice": "af_heart",
        },
        timeout=30,
    )

    response.raise_for_status()

    audio, sample_rate = sf.read(
        io.BytesIO(response.content),
        dtype="float32",
    )

    if sample_rate != OUTPUT_RATE:
        print("Resample audio")
        audio = resample_poly(
            audio,
            OUTPUT_RATE,
            sample_rate,
        )

    sd.play(
        audio.astype("float32"),
        OUTPUT_RATE,
        device=AUDIO_DEVICE,
    )

    sd.wait()


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
    except Exception as e:
        print(e)


def ask_gemini(client, text, model):

    try:
        return client.models.generate_content(
            model=model,
            contents=text
        ).text.strip()

    except Exception as e:
        print(f"Gemini failed ({model}): {e}")

    raise RuntimeError("Gemini unavailable")


def ask_groq(client, text, model):

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": text}
            ]
        )

        return response.choices[0].message.content.strip()

    except Exception as e:
        print(f"Groq failed ({model}): {e}")

    raise RuntimeError("Groq unavailable")


def ask_openai(client, text, model):

    try:
        response = client.responses.create(
            model=model,
            instructions=SYSTEM_PROMPT,
            input=text,
        )

        return response.output_text.strip()

    except Exception as e:
        print(f"OpenAI failed ({model}): {e}")

    raise RuntimeError("OpenAI unavailable")


def ask_openrouter(client, text, model):

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": text}
            ]
        )

        return response.choices[0].message.content.strip()

    except Exception as e:
        print(f"OpenRouter failed ({model}): {e}")

    raise RuntimeError("OpenRouter unavailable")


def ask_llm(text):
    global current_provider

    if not providers:
        return "No AI providers configured."

    prompt = f"Child: {text}"

    for offset in range(len(providers)):
        idx = (current_provider + offset) % len(providers)

        try:
            provider = providers[idx]
            if provider.name == "gemini":
                prompt = f"{SYSTEM_PROMPT}\n\n{prompt}"
            result = provider.fn(provider.client, prompt, provider.model)
            current_provider = idx
            return result

        except Exception as e:
            print(f"{provider.name} failed: {e}")

    return "Sorry, I'm not available right now."


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

def main():

    wait_for_service("whisper", WHISPER_SERVER)
    wait_for_service("voice", VOICE_SERVER)

    global providers

    if key := os.getenv("GEMINI_API_KEY"):
        providers.append(
            Provider(
                name = "gemini",
                client = genai.Client(api_key=key),
                fn = ask_gemini,
                model = "models/gemini-2.5-flash",
            )
        )

    if key := os.getenv("GROQ_API_KEY"):
        providers.append(
            Provider(
                name = "groq",
                client = Groq(api_key=key),
                fn = ask_groq,
                model = "llama-3.3-70b-versatile",
            )
        )

    if key := os.getenv("OPENROUTER_API_KEY"):
        providers.append(
            Provider(
                name = "openrouter",
                client = OpenAI(
                    api_key=key,
                    base_url="https://openrouter.ai/api/v1"
                ),
                fn = ask_openrouter,
                model = "openrouter/free",
            )
        )

    if key := os.getenv("OPENAI_API_KEY"):
        providers.append(
            Provider(
                name = "openai",
                client = OpenAI(api_key=key),
                fn = ask_openai,
                model = "gpt-5-nano",
            )
        )

    print("Enabled providers:")

    for provider in providers:
        print(f"  - {provider.name}")

    # Sleep mode
    # stream.read()
    # wake_model.predict()

    # Record mode
    # stream.read()
    # accumulate chunks

    # Stop stream
    # transcribe
    # ask_llm
    # speak

    # Recreate wake model
    # start stream again

    global state
    state = STATE_SLEEP

    print("Loading wake word model...")
    wake_model = Model(
        wakeword_model_paths=['alexa'],
        vad_threshold=0.5
    )

    stream = sd.InputStream(
        device=AUDIO_DEVICE,
        samplerate=MIC_RATE,
        channels=1,
        dtype="int16",
        blocksize=3840,
    )
    print("Actual sample rate:", stream.samplerate)

    stream.start()
    print("Listening for wake word...")

    state = STATE_SLEEP
    chunks = []
    heard_voice = False
    last_voice = 0
    ignore_wake_until = 0
    wake_hits = 0

    while True:

        audio, overflowed = stream.read(3840)

        # if overflowed:
        #     print("Audio overflow")

        audio = resample_poly(
            audio.flatten(),
            up=1,
            down=3,
        ).astype(np.int16)

        if state == STATE_SLEEP:

            prediction = wake_model.predict(audio)
            score = prediction.get('alexa', 0.0)

            if score > WAKE_THRESHOLD:
                print(prediction)
                wake_hits += 1
            else:
                wake_hits = 0

            if wake_hits < 3:
                continue

            print("Wake word detected")
            stream.stop()
            speak("Hi! What would you like to talk about?")
            stream.start()

            chunks = []
            last_voice = time.time()
            record_start = time.time()
            heard_voice = False
            state = STATE_RECORD
            continue

        chunks.append(audio)
        volume = np.abs(audio).mean()

        if volume > 200:
            if not heard_voice: print("Speech detected")

            last_voice = time.time()
            heard_voice = True

        stop_recording = (
            (heard_voice and time.time() - last_voice > SILENCE_TIMEOUT_SECONDS)
            or
            (time.time() - record_start > MAX_RECORD_SECONDS)
        )

        if not stop_recording:
            continue

        print("User stopped speaking")
        stream.stop()

        try:
            wav_buffer = io.BytesIO()
            write(wav_buffer, RATE, np.concatenate(chunks, axis=0))
            wav_buffer.seek(0)

            try:
                text = transcribe(wav_buffer)
            except Exception as e:
                print(f"Whisper failed: {e}")
                continue

            if text:
                print(f"Child: {text}")
                try:
                    answer = ask_llm(text)
                except Exception as e:
                    print(f"Answer failed {e}")
                    raise

                speak(answer)

        except Exception as e:
            print(e)

        chunks = []
        heard_voice = False
        last_voice = 0
        record_start = 0
        wake_hits = 0
        print("Returning to sleep...")
        #wake_model.reset()
        wake_model = Model() # reset doesn't work
        stream.start()
        state = STATE_SLEEP

if __name__ == "__main__":
    main()
