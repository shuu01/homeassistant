from io import BytesIO

import soundfile as sf
import uvicorn

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from kokoro_onnx import Kokoro


MODEL = "/models/kokoro.onnx"
VOICES = "/models/voices.bin"

voice = None
app = FastAPI()


class SynthesizeRequest(BaseModel):
    text: str
    voice: str = "af_heart"
    speed: float = 1.0


@app.on_event("startup")
def startup():
    global voice
    print(f"Loading voice: {MODEL}")
    voice = Kokoro(MODEL, VOICES)
    print("Voice loaded")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/synthesize")
def synthesize(req: SynthesizeRequest):
    text = req.text.strip()

    if not text:
        raise HTTPException(400, "empty text")

    print("TTS START")
    samples, sample_rate = voice.create(
        text,
        voice=req.voice,
        speed=req.speed,
    )
    print("TTS DONE")
    wav = BytesIO()

    sf.write(
        wav,
        samples,
        sample_rate,
        format="WAV",
    )

    return Response(
        content=wav.getvalue(),
        media_type="audio/wav",
    )
