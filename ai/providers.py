import os
import json
import requests
import io
import threading
import re
import wave
from dataclasses import dataclass
from datetime import datetime, timedelta

from google import genai
from google.genai import types
from groq import Groq
from openai import OpenAI

from google.api_core.exceptions import (
    ResourceExhausted,
    ServiceUnavailable,
    DeadlineExceeded,
    TooManyRequests,
)

from logger import logger
from prompt import SYSTEM_PROMPT, EXTRA_PROMPT


@dataclass
class Model:
    name: str | None = None
    url: str | None = None

    configured: bool = False
    healthy: bool = True
    health_counter: int = 0

    disabled_until: datetime | None = None
    timeout: int = 10

    @property
    def available(self):

        if not self.configured:
            return False

        if not self.healthy:
            return False

        if (
            self.disabled_until is not None
            and datetime.now() < self.disabled_until
        ):
            return False

        return True

class Provider:

    RATE_LIMIT_DISABLE = 3600
    CONNECTION_DISABLE = 300
    TIMEOUT_DISABLE = 120

    def __init__(self):
        self.name = None
        self.client = None
        self.models = {
            "llm": Model(),
            "tts": Model(),
            "stt": Model(),
        }

    def disable(
        self,
        capability: str,
        seconds: int,
    ):

        model = self.models[capability]

        model.disabled_until = (
            datetime.now() + timedelta(seconds=seconds)
        )

        logger.warning(
            f"{self.name} {capability} disabled until "
            f"{model.disabled_until.isoformat(timespec='seconds')}",
        )

    def ask(self, prompt):
        raise NotImplementedError
    def transcribe(self, audio):
        raise NotImplementedError
    def synthesize(self, text):
        raise NotImplementedError
    def stop(self):
        pass


class LocalProvider(Provider):

    def __init__(self):
        super().__init__()
        self.name = "local"
        self.models["tts"] = Model(
            name="kokoro",
            url=os.getenv("TTS_SERVER"),
            configured=bool(os.getenv("TTS_SERVER")),
            timeout=60,
        )
        self.models["stt"] = Model(
            name="whisper",
            url=os.getenv("STT_SERVER"),
            configured=bool(os.getenv("STT_SERVER")),
            timeout=60,
        )

        self.health_interval = int(
            os.getenv("LOCAL_HEALTH_INTERVAL", "15")
        )

        self.stop_event = threading.Event()
        self.health_thread = threading.Thread(
            target=self._health_worker,
            daemon=True,
            name="local-health",
        ).start()

    def _health_worker(self):

        while not self.stop_event.wait(self.health_interval):

            self._check("tts")
            self._check("stt")


    def _check(self, capability):

        model = self.models[capability]

        if not model.configured:
            return

        try:
            response = requests.get(
                f"{model.url}/health",
                timeout=3,
            )
            ok = response.ok
        except Exception:
            ok = False

        if ok:
            if model.healthy:
                model.health_counter = 0
                return

            model.health_counter += 1

            if model.health_counter >= 3:
                model.healthy = True
                model.health_counter = 0
                logger.info(f"{model.name} is online")

        else:
            model.health_counter = 0
            if model.healthy:
                model.healthy = False
                logger.warning(f"{model.name} is offline")

    def stop(self):

        self.stop_event.set()
        self.health_thread.join()

    def ask(self, prompt):
        raise NotImplementedError(
            "LocalProvider does not implement LLM."
        )

    def transcribe(self, wav_buffer):
        model = self.models["stt"]

        if not model.configured:
            raise RuntimeError("STT_SERVER is not configured.")

        response = requests.post(
            f"{model.url}/inference",
            files={
                "file": (
                    "audio.wav",
                    wav_buffer,
                    "audio/wav",
                )
            },
            timeout=model.timeout,
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

    def synthesize(
        self,
        text,
        voice="af_heart",
        speed=1.0,
    ):
        model = self.models["tts"]
        if not model.configured:
            raise RuntimeError("TTS_SERVER is not configured.")

        response = requests.post(
            f"{model.url}/synthesize",
            json={
                "text": text,
                "voice": voice,
                "speed": speed,
            },
            timeout=model.timeout,
        )

        response.raise_for_status()

        return response.content

class GeminiProvider(Provider):

    ENV = "GEMINI_API_KEY"

    def __init__(self):
        super().__init__()

        self.name = "gemini"
        key = os.getenv(self.ENV)

        if not key:
            logger.info(f"Gemini disabled ({self.ENV} not set)")
            return

        self.client = genai.Client(api_key=key)

        self.models["llm"] = Model(
            name="models/gemini-2.5-flash",
            configured=True,
        )

        self.models["tts"] = Model(
            name="gemini-2.5-flash-preview-tts",
            configured=True,
        )

    @staticmethod
    def _pcm_to_wav(pcm: bytes, sample_rate=24000):
        buf = io.BytesIO()

        with wave.open(buf, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)      # 16-bit PCM
            wav.setframerate(sample_rate)
            wav.writeframes(pcm)

        return buf.getvalue()

    def ask(self, text):

        model = self.models["llm"]

        try:
            response = self.client.models.generate_content(
                model=model.name,
                contents=f"{SYSTEM_PROMPT}\n\n{text}",
                config={
                    "response_mime_type": "application/json",
                    "response_schema": {
                        "type": "object",
                        "properties": {
                            "answer": {
                                "type": "string",
                            },
                            "facts": {
                                "type": "object",
                                "additionalProperties": {
                                    "anyOf": [
                                        {
                                            "type": "string",
                                        },
                                        {
                                            "type": "array",
                                            "items": {
                                                "type": "string",
                                            },
                                        },
                                    ],
                                },
                            },
                        },
                        "required": [
                            "answer",
                            "facts",
                        ],
                    },
                },
            )

            return json.loads(response.text)

        except ResourceExhausted:
            self.disable("llm", RATE_LIMIT_DISABLE)
            raise

        except (TooManyRequests, ServiceUnavailable):
            self.disable("llm", CONNECTION_DISABLE)
            raise

        except DeadlineExceeded:
            self.disable("llm", TIMEOUT_DISABLE)
            raise

        except Exception as e:
            logger.error(
                f"Gemini ({model.name}) failed: {e}"
            )
            raise

    def synthesize(self, text):

        model = self.models["tts"]

        try:
            response = self.client.models.generate_content(
                model=model.name,
                contents=text,
                config=types.GenerateContentConfig(
                    response_modalities=["AUDIO"],
                    speech_config=types.SpeechConfig(
                        voice_config=types.VoiceConfig(
                            prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                voice_name="Kore",
                            )
                        )
                    ),
                ),
            )

            audio = response.candidates[0].content.parts[0].inline_data.data

            return _pcm_to_wav(audio)

        except ResourceExhausted:
            self.disable("llm", RATE_LIMIT_DISABLE)
            raise

        except (TooManyRequests, ServiceUnavailable):
            self.disable("llm", CONNECTION_DISABLE)
            raise

        except DeadlineExceeded:
            self.disable("llm", TIMEOUT_DISABLE)
            raise

        except Exception as e:
            logger.error(
                f"Gemini TTS ({model.name}) failed: {e}"
            )
            raise


class GroqProvider(Provider):

    ENV = "GROQ_API_KEY"

    def __init__(self):
        super().__init__()

        self.name = "groq"
        key= os.getenv(self.ENV)
        if not key:
            logger.info(f"Groq disabled ({self.ENV} not set)")
            return
        else:
            self.client = Groq(api_key=key)

        self.models["llm"] = Model(
            name="llama-3.3-70b-versatile",
            configured=True,
        )

        self.models["tts"] = Model(
            name="canopylabs/orpheus-v1-english",
            configured=True,
            timeout=60,
        )

        self.models["stt"] = Model(
            name="whisper-large-v3-turbo",
            configured=True,
            timeout=60,
        )

    def ask(self, text):

        model = self.models["llm"]

        try:
            response = self.client.chat.completions.create(
                model=model.name,
                messages=[
                    {"role": "system", "content": f"{SYSTEM_PROMPT}\n\n{EXTRA_PROMPT}"},
                    {"role": "user", "content": text}
                ],
                response_format={"type": "json_object"},
            )
            data = response.choices[0].message.content.strip()
            logger.debug(data)
            json_data = json.loads(data)
            return json_data

        except groq.RateLimitError:
            self.disable("llm", RATE_LIMIT_DISABLE)
            raise

        except (
            groq.APIConnectionError,
            groq.APITimeoutError,
            groq.InternalServerError,
        ):
            self.disable("llm", CONNECTION_DISABLE)
            raise

        except Exception as e:
            logger.error(
                f"Groq LLM ({model.name}) failed: {e}"
            )
            raise

    def synthesize(
        self,
        text,
        voice="hannah",
    ):

        model = self.models["tts"]

        try:
            response = self.client.audio.speech.create(
                model=model.name,
                voice=voice,
                input=text,
                response_format="wav",
            )

            return response.read()

        except groq.RateLimitError:
            self.disable("llm", RATE_LIMIT_DISABLE)
            raise

        except (
            groq.APIConnectionError,
            groq.APITimeoutError,
            groq.InternalServerError,
        ):
            self.disable("llm", CONNECTION_DISABLE)
            raise

        except Exception as e:
            logger.error(
                f"Groq TTS ({model.name}) failed: {e}"
            )
            raise

    def transcribe(self, audio):

        model = self.models["stt"]

        try:
            response = self.client.audio.transcriptions.create(
                file=("audio.wav", audio),
                model=model.name,
                response_format="text",
            )

            return response.strip()

        except groq.RateLimitError:
            self.disable("llm", RATE_LIMIT_DISABLE)
            raise

        except (
            groq.APIConnectionError,
            groq.APITimeoutError,
            groq.InternalServerError,
        ):
            self.disable("llm", CONNECTION_DISABLE)
            raise

        except Exception as e:
            logger.error(
                f"Groq STT ({model.name}) failed: {e}"
            )
            raise


class OpenAIProvider(Provider):

    ENV = "OPENAI_API_KEY"

    def __init__(self):
        super().__init__()

        self.name = "openai"
        key = os.getenv(self.ENV)
        if not key:
            logger.info(f"OpenAI disabled ({self.ENV} not set)")
            return
        else:
            self.client = OpenAI(api_key=key)

        self.models["llm"] = Model(
            name="gpt-5-nano",
            configured=True,
            timeout=60,
        )

    def ask(self, text):

        model = self.models["llm"]

        try:
            response = self.client.responses.create(
                model=model.name,
                instructions=SYSTEM_PROMPT,
                input=text,
                timeout=model.timeout,
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "assistant_response",
                        "schema": {
                            "type": "object",
                            "properties": {
                                "answer": {
                                    "type": "string",
                                },
                                "facts": {
                                    "type": "object",
                                    "additionalProperties": {
                                        "anyOf": [
                                            {
                                                "type": "string",
                                            },
                                            {
                                                "type": "array",
                                                "items": {
                                                    "type": "string",
                                                },
                                            },
                                        ],
                                    },
                                },
                            },
                            "required": [
                                "answer",
                                "facts",
                            ],
                            "additionalProperties": False,
                        },
                    }
                },
            )

            data = response.output_text
            logger.debug(data)
            json_data = json.loads(data)
            return json_data

        except openai.RateLimitError:
            self.disable("llm", RATE_LIMIT_DISABLE)
            raise

        except (
            openai.APIConnectionError,
            openai.APITimeoutError,
            openai.InternalServerError,
        ):
            self.disable("llm", CONNECTION_DISABLE)
            raise

        except Exception as e:
            logger.error(
                f"OpenAI LLM ({model.name}) failed: {e}"
            )
            raise


class OpenRouterProvider(Provider):

    ENV = "OPENROUTER_API_KEY"

    def __init__(self):
        super().__init__()

        self.name = "openrouter"
        key= os.getenv(self.ENV)
        if not key:
            logger.info(f"OpenRouter disabled ({self.ENV} not set)")
            return
        else:
            self.client = OpenAI(
                api_key=key,
                base_url="https://openrouter.ai/api/v1",
            )

        self.models["llm"] = Model(
            name="openrouter/free",
            configured=True,
            timeout=60,
        )

    def ask(self, text):

        model = self.models["llm"]

        try:
            response = self.client.chat.completions.create(
                model=model.name,
                messages=[
                    {
                        "role": "system",
                        "content": f"{SYSTEM_PROMPT}\n\n{EXTRA_PROMPT}",
                    },
                    {
                        "role": "user",
                        "content": text,
                    },
                ],
                timeout=model.timeout,
            )

            data = response.choices[0].message.content.strip()
            logger.debug(data)
            json_data = json.loads(data)
            return json_data

        except openai.RateLimitError:
            self.disable("llm", RATE_LIMIT_DISABLE)
            raise

        except (
            openai.APIConnectionError,
            openai.APITimeoutError,
            openai.InternalServerError,
        ):
            self.disable("llm", CONNECTION_DISABLE)
            raise

        except Exception as e:
            logger.error(
                f"OpenRouter LLM ({model.name}) failed: {e}"
            )
            raise

