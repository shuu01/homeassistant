from google import genai
from groq import Groq
from openai import OpenAI

import os
import logging

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """
You are Alexa, a friendly companion for a 5-year-old child.

Be warm and friendly.
Be accurate.
Use simple language.
Do not make up magical explanations.
Do not use baby talk.
Do not personify scientific concepts.

When answering educational questions:
- explain the real reason
- use examples a child understands
- keep answers short

Tell stories only when asked.

Keep responses under 3 sentences unless it is a story or a longer answer is requested.
Never be scary.
No emojis in responses.

Return ONLY valid JSON.
Do not use markdown.
Do not use code fences.

At the end of your response, attach memory updates.
Only store information that will likely remain true
for weeks or months.
Do not store temporary events.
The "facts" field is ONLY for facts that the child explicitly states about themselves.
Never infer, assume, or guess.
Bad:
- ate pizza today
- is tired
Good:
- likes unicorns
- favorite color is purple
- has a pet rabbit named Snowball

facts must be an array of strings.
Never use objects.
Never use booleans.
Never use nested JSON.

Response format:
{
  "answer": "...",
  "facts": ["...", "..."]
}
"""

class LLM:
    def __init__(self):
        self.providers = []
        self.client = None
        self.current = 0
        self._load_providers()
        self.system_prompt = os.getenv("SYSTEM_PROMPT", SYSTEM_PROMPT)

    def _load_providers(self):
        if key := os.getenv("GEMINI_API_KEY"):
            self.providers.append({
                "name": "gemini",
                "client": genai.Client(api_key=key),
                "model": "models/gemini-2.5-flash",
                "fn": self._ask_gemini,
            })
        if key := os.getenv("GROQ_API_KEY"):
            self.providers.append({
                "name": "groq",
                "client": Groq(api_key=key),
                "model": "llama-3.3-70b-versatile",
                "fn": self._ask_groq,
            })
        if key := os.getenv("OPENROUTER_API_KEY"):
            self.providers.append({
                "name": "openrouter",
                "client": OpenAI(
                    api_key=key,
                    base_url="https://openrouter.ai/api/v1",
                ),
                "model": "openrouter/free",
                "fn": self._ask_openrouter,
            })
        if key := os.getenv("OPENAI_API_KEY"):
            self.providers.append({
                "name": "openai",
                "client": OpenAI(api_key=key),
                "model": "gpt-5-nano",
                "fn": self._ask_openai,
            })

        logger.info("Enabled providers:")

        for provider in self.providers:
            logger.info(
                f"  - {provider['name']}"
            )

    def _ask_gemini(self, text):

        try:
            return self.client.models.generate_content(
                model=self.model,
                contents=text
            ).text.strip()

        except Exception as e:
            logger.error(f"Gemini failed ({self.model}): {e}")

        raise RuntimeError("Gemini unavailable")


    def _ask_groq(self, text):

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": text}
                ]
            )

            return response.choices[0].message.content.strip()

        except Exception as e:
            logger.error(f"Groq failed ({self.model}): {e}")

        raise RuntimeError("Groq unavailable")


    def _ask_openai(self, text):

        try:
            response = self.client.responses.create(
                model=self.model,
                instructions=self.system_prompt,
                input=text,
            )

            return response.output_text.strip()

        except Exception as e:
            logger.error(f"OpenAI failed ({self.model}): {e}")

        raise RuntimeError("OpenAI unavailable")


    def _ask_openrouter(self, text):

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": text}
                ]
            )

            return response.choices[0].message.content.strip()

        except Exception as e:
            logger.error(f"OpenRouter failed ({self.model}): {e}")

        raise RuntimeError("OpenRouter unavailable")


    def ask(self, text, facts=[], messages={}):

        if not self.providers:
            return "No AI providers configured."

        prompt = f"Child: {text}"

        for offset in range(len(self.providers)):

            idx = (self.current + offset) % len(self.providers)

            provider = self.providers[idx]
            try:
                if provider.get("name") == "gemini":
                    prompt = f"{self.system_prompt}\n\n{prompt}"
                self.client = provider.get("client")
                self.model = provider.get("model")
                result = provider.get("fn")(prompt)
                self.current = idx
                return result

            except Exception as e:
                logger.error(f"{provider.get("name")} failed: {e}")

        return "Sorry, I'm not available right now."
