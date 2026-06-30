from io import BytesIO

import soundfile as sf
import uvicorn

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from kokoro_onnx import Kokoro

import logging

logger = logging.getLogger(__name__)

MODEL = "kokoro-v1.0.onnx"
VOICES = "voices-v1.0.bin"

tts = None
app = FastAPI()


class SynthesizeRequest(BaseModel):
    text: str
    voice: str = "af_heart"
    speed: float = 1.0


@app.on_event("startup")
def startup():
    global tts
    print(f"Loading voice: {MODEL}")
    tts = Kokoro(MODEL, VOICES)
    print("Voice loaded")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/synthesize")
def synthesize(req: SynthesizeRequest):
    text = req.text.strip()

    if not text:
        raise HTTPException(400, "empty text")

    samples, sample_rate = tts.create(
        text,
        voice=req.voice,
        speed=req.speed,
    )

    wav = BytesIO()

    sf.write(
        wav,
        samples,
        sample_rate,
        format="WAV",
    )

    logger.info(
        "Generated %.2f s of audio", len(samples) / sample_rate,
    )

    return Response(
        content=wav.getvalue(),
        media_type="audio/wav",
    )
