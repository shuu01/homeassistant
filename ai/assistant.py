import io
import os
import time
import json
import re
import random
import threading
import numpy as np
import sounddevice as sd
import soundfile as sf

from queue import Queue, Full
from pathlib import Path
from scipy.io.wavfile import write
from scipy.signal import resample_poly
from dataclasses import dataclass

import requests
from openwakeword.model import Model

from llm import LLM
from db import DbRequest, db_worker, db_queue
from client import Service

import logging

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

GREETINGS_DIR = Path(os.getenv("GREETINGS_DIR", "./"))
GREETINGS = list(GREETINGS_DIR.glob("*.wav"))

MIC_RATE = 44100
OUTPUT_RATE = 48000
RATE = 16000
INPUT_DEVICE = int(os.getenv("INPUT_DEVICE", "0"))
OUTPUT_DEVICE = int(os.getenv("OUTPUT_DEVICE", "4"))
WAKE_THRESHOLD = float(os.getenv("WAKE_THRESHOLD", "0.5"))
VOLUME_THRESHOLD = int(os.getenv("VOLUME_THRESHOLD", "200"))
MAX_RECORD_SECONDS = 20
SILENCE_TIMEOUT_SECONDS = 3
WAIT_FOR_SPEECH_TIMEOUT = 10

STT_SERVER = os.getenv(
    "STT_SERVER",
    "http://whisper:8080",
)
TTS_SERVER = os.getenv(
    "TTS_SERVER",
    "http://kokoro:8080",
)

chunks = []

tts_queue = Queue()
audio_output_queue = Queue()
audio_input_queue = Queue(maxsize=20)
wakeword_queue = Queue(maxsize=20)
speaking_event = threading.Event()
wake_event = threading.Event()
recording_event = threading.Event()
recording_done = threading.Event()


def split_sentences(text):
    return re.split(r'(?<=[.!?])\s+', text.strip())


def sentence_pause(text):
    if text.endswith("?"):
        return 1

    if text.endswith("!"):
        return 0.9

    return 0.7


def callback(indata, frames, time_info, status):

    if speaking_event.is_set():
        return

    if status:
        logger.debug(f"Audio status: {status}")

    block = indata.copy()
    try:
        audio_input_queue.put_nowait(block)
    except Full:
        pass
    if not recording_event.is_set():
        try:
            wakeword_queue.put_nowait(block)
        except Full:
            pass


def record_worker():
    last_voice = 0
    record_start = 0
    speech_started = False
    wait_start = 0

    while True:
        audio = audio_input_queue.get()
        if not recording_event.is_set():
            continue

        if wait_start == 0:
            wait_start = time.time()

        audio = resample_poly(
            audio.flatten(),
            RATE,
            MIC_RATE,
        ).astype(np.int16)

        volume = np.abs(audio).mean()

        if not speech_started:

            if volume > VOLUME_THRESHOLD:
                logger.info("Speech detected")
                speech_started = True
                record_start = time.time()
                last_voice = time.time()
                chunks.clear()
                chunks.append(audio)
            elif time.time() - wait_start > WAIT_FOR_SPEECH_TIMEOUT:
                logger.info("No speech detected")
                recording_event.clear()
                recording_done.set()
                speech_started = False
                wait_start = 0
                record_start = 0
                last_voice = 0
            continue

        chunks.append(audio)

        if volume > VOLUME_THRESHOLD:
            logger.info(f"Voice volume={volume:.0f}")
            last_voice = time.time()

        stop_recording = (
            (time.time() - last_voice > SILENCE_TIMEOUT_SECONDS)
            or
            (time.time() - record_start > MAX_RECORD_SECONDS)
        )

        if not stop_recording:
            continue

        logger.info("User stopped speaking")
        recording_event.clear()
        recording_done.set()
        speech_started = False
        wait_start = 0
        record_start = 0
        last_voice = 0


def wakeword_worker():

    wake_model = Model()
    wake_hits = 0

    while True:

        audio = wakeword_queue.get()

        if recording_event.is_set():
            continue
        if speaking_event.is_set():
            continue

        audio = resample_poly(
            audio.flatten(),
            RATE,
            MIC_RATE,
        ).astype(np.int16)

        prediction = wake_model.predict(audio)
        score = prediction.get("alexa", 0.0)
        logger.debug(score)

        if score > WAKE_THRESHOLD:
            logger.info(f"prediction score: {score}")
            wake_hits += 1
        else:
            wake_hits = 0

        if wake_hits >= 3:
            logger.info("Wake word detected")
            wake_event.set()
            wake_hits = 0
            wake_model.reset()


def tts_worker():
    while True:
        text = tts_queue.get()

        try:
            if text is None:
                return
            logger.info(f"Assistant: {text}")

            response = tts.post(
                "/synthesize",
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
                audio = resample_poly(audio, OUTPUT_RATE, sample_rate)

            pause = np.zeros(
                int(OUTPUT_RATE * sentence_pause(text)),
                dtype=np.float32,
            )
            audio = np.concatenate([audio, pause])

            audio_output_queue.put(audio)

        except Exception as e:
            logger.error(f"TTS failed: {e}")
        finally:
            tts_queue.task_done()


def audio_worker():
    while True:
        audio = audio_output_queue.get()
        if audio is None:
            break

        speaking_event.set()
        sd.play(audio.astype("float32"), OUTPUT_RATE, device=OUTPUT_DEVICE)
        sd.wait()
        audio_output_queue.task_done()
        speaking_event.clear()


def greeting():
    if not GREETINGS:
        logger.warning("No greeting samples found")
        tts_queue.put(
            "Hi! What would you like to talk about?"
        )
        return
    filename = random.choice(GREETINGS)
    audio, sample_rate = sf.read(filename, dtype="float32")
    if sample_rate != OUTPUT_RATE:
        audio = resample_poly(audio, OUTPUT_RATE, sample_rate)
    audio_output_queue.put(audio)


def transcribe(stt, wav_buffer):
    try:
        files = {
            "file": (
                "audio.wav",
                wav_buffer,
                "audio/wav",
            )
        }

        response = stt.post(
            "/inference",
            files=files,
            timeout=60,
        )

        response.raise_for_status()
        data = response.json()
        text = data.get("text", "").strip()
        # filter gibberish
        if re.fullmatch(r"\([^)]*\)", text):
            return ""
        if re.fullmatch(r"\[[^\]]*\]", text):
            return ""
        if len(text) < 3:
            return ""
        return text
    except Exception as e:
        logger.error(e)


def compose_prompt():
    pass
    # prompt = f"""
    #     Recent conversation:
    #     {conversation_text}

    #     Child facts:
    #     {facts_text}

    #     Current question:
    #     {text}
    #     """

def main():

    stt = Service("whisper", STT_SERVER)
    tts = Service("kokoro", TTS_SERVER)

    stt.wait_until_ready()
    tts.wait_until_ready()

    threading.Thread(target=tts_worker, daemon=True, name="tts").start()
    threading.Thread(target=audio_worker, daemon=True, name="audio").start()
    threading.Thread(target=wakeword_worker, daemon=True, name="wakeword").start()
    threading.Thread(target=record_worker, daemon=True, name="record").start()
    #threading.Thread(target=db_worker, args=("assistant.db",), name="db").start()

    llm = LLM()

    stream = sd.InputStream(
        device=INPUT_DEVICE,
        samplerate=MIC_RATE,
        channels=1,
        dtype="int16",
        blocksize=3840,
        callback=callback,
        latency="high",
    )
    logger.info(f"Actual sample rate: {stream.samplerate}")

    stream.start()
    logger.info("Listening for wake word...")

    while True:

        wake_event.clear()
        wake_event.wait()

        greeting()
        tts_queue.join()
        audio_output_queue.join()
        while not audio_input_queue.empty():
            audio_input_queue.get_nowait()
        recording_event.set()
        recording_done.clear()
        recording_done.wait()

        if not chunks:
            logger.info("No speech captured")
            continue

        try:
            wav_buffer = io.BytesIO()
            write(wav_buffer, RATE, np.concatenate(chunks, axis=0))
            wav_buffer.seek(0)

            sf.write(
                "/tmp/debug.wav",
                np.concatenate(chunks),
                RATE,
            )

            try:
                text = transcribe(stt, wav_buffer)
            except Exception as e:
                logger.error(f"STT failed: {e}")
                continue

            if text:
                #facts = get_facts()
                #mesages = get_messages(20)
                facts = []
                messages = {}
                logger.info(f"Child: {text}")
                try:
                    response = llm.ask(text, facts, messages)
                    response = re.sub(r"^```json\s*", "", response.strip())
                    response = re.sub(r"\s*```$", "", response)
                    answer = response
                    logger.debug(answer)
                    try:
                        data = json.loads(response)
                        if isinstance(data, dict):
                            answer = data.get("answer", "")
                            facts = data.get("facts", [])
                            logger.info(f"facts: {facts}")
                            #update_facts(facts)
                            #update_messages(text)
                    except Exception as e:
                        pass
                except Exception as e:
                    logger.error(f"Answer failed {e}")
                    raise

                for sentence in split_sentences(answer):
                    if sentence.strip():
                        tts_queue.put(sentence)

        except Exception as e:
            logger.error(e)
        tts_queue.join()
        audio_output_queue.join()
        chunks.clear()
        logger.info("Returning to sleep...")

    #db_queue.put(None)   # Tell worker to stop
    #db_thread.join()     # Wait until it finishes

if __name__ == "__main__":
    main()
