from io import BytesIO
import logging
import os
import wave

import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response, StreamingResponse
from kokoro_onnx import Kokoro
from pydantic import BaseModel

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger(__name__)

MODEL = "kokoro-v1.0.onnx"
VOICES = "voices-v1.0.bin"

tts = None
app = FastAPI()


class SynthesizeRequest(BaseModel):
    text: str
    voice: str = "af_heart:0.7,af_sarah:0.3"
    speed: float = 1.0


class OpenAISpeechRequest(BaseModel):
    model: str = "kokoro"
    input: str
    voice: str = "af_heart:0.7,af_sarah:0.3"
    speed: float = 1.0
    response_format: str = "wav"
    stream: bool = False


@app.on_event("startup")
def startup():
    global tts

    logger.info("Loading model %s", MODEL)
    tts = Kokoro(MODEL, VOICES)
    logger.info("Model loaded")


@app.get("/health")
def health():
    return {"status": "ok"}


def to_int16(samples):
    if samples.dtype == np.int16:
        return samples

    return (samples * 32767).clip(-32768, 32767).astype(np.int16)


def create_wav(text: str, voice: str, speed: float) -> bytes:
    samples, sample_rate = tts.create(
        text,
        voice=voice,
        speed=speed,
    )

    samples = to_int16(samples)

    logger.info(
        "Generated %.2f s of audio",
        len(samples) / sample_rate,
    )

    wav = BytesIO()

    with wave.open(wav, "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(sample_rate)
        f.writeframes(samples.tobytes())

    return wav.getvalue()


@app.post("/synthesize")
def synthesize(req: SynthesizeRequest):
    text = req.text.strip()

    if not text:
        raise HTTPException(400, "empty text")

    return Response(
        create_wav(
            text=text,
            voice=req.voice,
            speed=req.speed,
        ),
        media_type="audio/wav",
    )


@app.post("/v1/audio/speech")
async def openai_speech(req: OpenAISpeechRequest):
    text = req.input.strip()

    if not text:
        raise HTTPException(400, "empty input")

    if not req.stream:
        if req.response_format != "wav":
            raise HTTPException(
                400,
                "Only 'wav' is currently supported.",
            )

        return Response(
            create_wav(
                text=text,
                voice=req.voice,
                speed=req.speed,
            ),
            media_type="audio/wav",
        )

    if req.response_format != "pcm":
        raise HTTPException(
            400,
            "Streaming currently supports only response_format='pcm'.",
        )

    async def generate():
        total_samples = 0
        sample_rate = None

        stream = tts.create_stream(
            text,
            voice=voice,
            speed=req.speed,
            lang="en-us",
        )

        async for samples, sr in stream:
            samples = to_int16(samples)

            sample_rate = sr
            total_samples += len(samples)

            yield samples.tobytes()

        if sample_rate:
            logger.info(
                "Streamed %.2f s of audio",
                total_samples / sample_rate,
            )

    return StreamingResponse(
        generate(),
        media_type="audio/pcm",
    )
