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


def audio_to_wav_bytes(audio: np.ndarray) -> bytes:
    buf = BytesIO()
    sf.write(buf, audio, 22050, format="WAV", subtype="PCM_16")
    return buf.getvalue()


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

    chunks = []
    for chunk in voice.synthesize(text):
        chunks.append(chunk.audio)

    audio = np.concatenate(chunks)

    wav_bytes = audio_to_wav_bytes(audio, 22050)

    return Response(content=wav_bytes, media_type="audio/wav")
