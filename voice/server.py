from io import BytesIO

import soundfile as sf
import os

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from piper import PiperVoice
import numpy as np

MODEL = f"/models/{os.getenv('MODEL', 'en_US-lessac-medium.onnx')}"
CONFIG = f"/models/{os.getenv('CONFIG', 'en_US-lessac-medium.onnx.json')}"

voice = None
app = FastAPI()

class SynthesizeRequest(BaseModel):
    text: str
    voice: str = "default"
    speed: float = 1.0


@app.on_event("startup")
def startup():
    global voice
    print("Loading Piper model...")
    voice = PiperVoice.load(MODEL, CONFIG)
    print("Piper loaded")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/synthesize")
def synthesize(req: SynthesizeRequest):
    text = req.text.strip()

    if not text:
        raise HTTPException(400, "empty text")

    audio = voice.synthesize(text)

    wav_bytes = audio_to_wav_bytes(audio, 22050)

    buf = BytesIO()
    sf.write(buf, audio, 22050, format="WAV", subtype="PCM_16")

    return Response(content=buf.getvalue(), media_type="audio/wav")
