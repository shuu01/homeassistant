import io
import os
import re
import threading
from queue import Queue

import numpy as np
import sounddevice as sd
import soundfile as sf
from scipy.signal import resample_poly

from logger import logger


class TTS:

    def __init__(
        self,
        ai,
        output_device,
        output_rate=48000,
    ):

        self.ai = ai

        self.output_device = output_device
        self.output_rate = output_rate

        self.speed = float(
            os.getenv("SPEECH_SPEED", "1.0")
        )

        self.queue = Queue()
        self.audio_queue = Queue()

        self.speaking = threading.Event()

        self.tts_thread = threading.Thread(
            target=self._tts_worker,
            daemon=True,
            name="tts",
        )
        self.tts_thread.start()

        self.audio_thread = threading.Thread(
            target=self._audio_worker,
            daemon=True,
            name="audio",
        )
        self.audio_thread.start()

    def stop(self):

        self.queue.put(None)
        self.audio_queue.put(None)

        self.tts_thread.join()
        self.audio_thread.join()

    def speak(self, text):

        self.queue.put(text)

    def wait(self):

        self.queue.join()
        self.audio_queue.join()

    def _tts_worker(self):

        while True:

            text = self.queue.get()

            try:

                if text is None:
                    return

                for sentence in self._split_sentences(text):

                    if not sentence.strip():
                        continue

                    sentence = self._strip_markdown(sentence)

                    logger.info(
                        f"Assistant: {sentence}"
                    )

                    content = self.ai.synthesize(
                        sentence,
                        speed=self.speed,
                    )

                    audio, sample_rate = sf.read(
                        io.BytesIO(content),
                        dtype="float32",
                    )

                    if sample_rate != self.output_rate:
                        audio = resample_poly(
                            audio,
                            self.output_rate,
                            sample_rate,
                        )

                    pause = np.zeros(
                        int(
                            self.output_rate
                            * self._pause(sentence)
                        ),
                        dtype=np.float32,
                    )

                    audio = np.concatenate(
                        [audio, pause]
                    )

                    self.audio_queue.put(audio)

            except Exception as e:
                logger.error(
                    f"TTS failed: {e}"
                )

            finally:
                self.queue.task_done()

    def _audio_worker(self):

        while True:

            audio = self.audio_queue.get()

            if audio is None:
                return

            self.speaking.set()

            try:

                sd.play(
                    audio.astype(np.float32),
                    self.output_rate,
                    device=self.output_device,
                )

                sd.wait()

            finally:

                self.audio_queue.task_done()
                self.speaking.clear()

    @staticmethod
    def _split_sentences(text):

        return re.split(
            r'(?<=[.!?]["\']?)\s*',
            text.strip(),
        )

    @staticmethod
    def _pause(text):

        if text.endswith("?"):
            return 1.0

        if text.endswith("!"):
            return 0.9

        return 0.7

    @staticmethod
    def _strip_markdown(text):

        text = re.sub(
            r"\*\*(.*?)\*\*",
            r"\1",
            text,
        )

        text = re.sub(
            r"\*(.*?)\*",
            r"\1",
            text,
        )

        text = re.sub(
            r"__(.*?)__",
            r"\1",
            text,
        )

        text = re.sub(
            r"_(.*?)_",
            r"\1",
            text,
        )

        text = re.sub(
            r"`(.*?)`",
            r"\1",
            text,
        )

        return text
