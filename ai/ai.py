from providers import (
    GeminiProvider,
    GroqProvider,
    OpenAIProvider,
    OpenRouterProvider,
    LocalProvider,
)
from logger import logger

class AI:

    def __init__(self):

        self.local = LocalProvider()
        self.gemini = GeminiProvider()
        self.groq = GroqProvider()
        self.openai = OpenAIProvider()
        self.openrouter = OpenRouterProvider()

        self.providers = [
            self.local,
            self.gemini,
            self.groq,
            self.openai,
            self.openrouter,
        ]
        logger.info(f"Enabled providers:")
        for provider in self.providers:
            logger.info(f"  - {provider.name}")

        self.llm = [
            self.gemini,
            self.groq,
            self.openai,
            self.openrouter,
        ]

        self.tts = [
            self.groq,
            self.local,
            self.gemini,
        ]

        self.stt = [
            self.groq,
            self.local,
        ]

    def _run(self, capability, providers, *args, **kwargs):

        method = {
            "llm": "ask",
            "tts": "synthesize",
            "stt": "transcribe",
        }[capability]

        last_error = None

        for provider in providers:

            model = provider.models[capability]

            if not model.available:
                continue

            try:
                return getattr(provider, method)(
                    *args,
                    **kwargs,
                )

            except Exception as e:
                logger.exception(
                    f"{provider.name} {capability} failed",
                )
                last_error = e

        if last_error:
            raise last_error

        raise RuntimeError(
            f"No {capability.upper()} provider available."
        )

    def ask(self, text):
        return self._run(
            "llm",
            self.llm,
            text,
        )

    def synthesize(self, text, speed=1.0, voice=None):
        kwargs = {"speed": speed}
        if voice is not None:
            kwargs["voice"] = voice

        return self._run(
            "tts",
            self.tts,
            text,
            **kwargs,
        )

    def transcribe(self, audio):
        return self._run(
            "stt",
            self.stt,
            audio,
        )

    def stop(self):

        for provider in self.providers:
            provider.stop()
