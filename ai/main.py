import io
import os
import time
import re
import random
import threading
import signal
import numpy as np
import sounddevice as sd
import soundfile as sf

from queue import Queue, Full
from pathlib import Path
from scipy.io.wavfile import write
from scipy.signal import resample_poly

from openwakeword.model import Model

from ai import AI
from storage import GistStorage
from memory import Memory
from conversation import Conversation
from logger import logger

GREETINGS_DIR = Path(os.getenv("GREETINGS_DIR", "./greetings"))
FALLBACKS_DIR = Path(os.getenv("FALLBACKS_DIR", "./fallbacks"))

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
LAST_MESSAGES = int(os.getenv("LAST_MESSAGES", "20"))

chunks = []

tts_queue = Queue()
audio_output_queue = Queue()
audio_input_queue = Queue(maxsize=20)
wakeword_queue = Queue(maxsize=20)
speaking_event = threading.Event()
wake_event = threading.Event()
recording_event = threading.Event()
recording_done = threading.Event()
tts_failed = threading.Event()
shutdown = threading.Event()


def handle_shutdown(signum, frame):
    logger.info("Received signal %s", signum)
    shutdown.set()


def compose_prompt(text, messages=None, facts=None):

    sections = []

    if messages:

        messages_text = "\n".join(
            f'{m["role"]}: {m["text"]}'
            for m in messages
        )

        sections.append(
            f"Recent conversation:\n{messages_text}"
        )

    if facts:

        facts_text = "\n".join(
            f"{key}: {value}"
            for key, value in facts.items()
        )

        sections.append(
            f"Child facts:\n{facts_text}"
        )

    sections.append(
        f"Current question:\nChild: {text}"
    )

    return "\n".join(sections)


def split_sentences(text):
    text = text.replace('"', '').replace("'", "")
    return [
        sentence.strip()
        for sentence in re.findall(r'[^.!?]+[.!?]?', text)
        if sentence.strip()
    ]


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
        if audio is None:
            return
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
        if audio is None:
            return

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


def tts_worker(ai, fallbacks):
    speed = float(os.getenv("SPEECH_SPEED", "1.0"))
    while True:
        text = tts_queue.get()

        try:
            if text is None:
                return
            logger.info(f"Assistant: {text}")

            content = ai.synthesize(text, speed=speed)

            audio, sample_rate = sf.read(
                io.BytesIO(content),
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
            if not tts_failed.is_set():
                tts_failed.set()
                play(fallbacks)
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


def play(files):
    filename = random.choice(files)
    audio, sample_rate = sf.read(filename, dtype="float32")
    if sample_rate != OUTPUT_RATE:
        audio = resample_poly(audio, OUTPUT_RATE, sample_rate)
    audio_output_queue.put(audio)
    audio_output_queue.join()


def load_wav_files(path):
    if not path.exists():
        raise RuntimeError(
            f"{path} directory does not exist"
        )

    files = list(path.glob("*.wav"))

    if not files:
        raise RuntimeError(
            f"No WAV files found in {path}"
        )
    logger.info(f"WAV from {path} are loaded")
    return files


def main():

    signal.signal(signal.SIGTERM, handle_shutdown)
    signal.signal(signal.SIGINT, handle_shutdown)

    greetings = load_wav_files(GREETINGS_DIR)
    fallbacks = load_wav_files(FALLBACKS_DIR)

    ai = AI()
    storage = GistStorage()
    memory = Memory(storage)
    conversation = Conversation(storage)
    #speaker = Speaker(ai, speaking_event)

    threading.Thread(target=tts_worker, daemon=True, name="tts", args=(ai, fallbacks)).start()
    threading.Thread(target=audio_worker, daemon=True, name="audio").start()
    threading.Thread(target=wakeword_worker, daemon=True, name="wakeword").start()
    threading.Thread(target=record_worker, daemon=True, name="record").start()

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

    while not shutdown.is_set():

        if not wake_event.wait(timeout=1):
            continue

        wake_event.clear()

        while not audio_input_queue.empty():
            audio_input_queue.get_nowait()
        while not wakeword_queue.empty():
            wakeword_queue.get_nowait()

        play(greetings)

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
                user_text = ai.transcribe(wav_buffer)
            except Exception as e:
                logger.error(f"STT failed: {e}")
                play(fallbacks)
                continue

            if user_text:
                logger.info(f"user: {user_text}")
                facts = memory.facts
                messages = conversation.recent_messages()
                prompt = compose_prompt(user_text, messages, facts)
                try:
                    response = ai.ask(prompt)
                    answer = response.get('answer')
                    new_facts = response.get('facts')
                    conversation.add("child", user_text)
                    conversation.add("assistant", answer)
                    memory.update(new_facts)
                    logger.info(f"facts: {new_facts}")
                except Exception as e:
                    logger.error(f"Answer failed: {e}")
                    play(fallbacks)
                    continue

                tts_failed.clear()
                for sentence in split_sentences(answer):
                    if sentence.strip():
                        tts_queue.put(sentence)

        except Exception as e:
            logger.error(e)

        tts_queue.join()
        audio_output_queue.join()
        chunks.clear()
        logger.info("Returning to sleep...")

    logger.info("Stopping InputStream...")
    stream.stop()
    stream.close()
    wakeword_queue.put(None)
    audio_input_queue.put(None)
    audio_output_queue.put(None)
    tts_queue.put(None)
    logger.info("Stopping AI...")
    ai.stop()
    logger.info("Stopping Storage...")
    storage.stop()
    logger.info("Shutdown complete.")


if __name__ == "__main__":
    main()
