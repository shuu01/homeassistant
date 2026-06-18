from io import BytesIO

import wave
import os

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from piper import PiperVoice

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

    wav_buffer = io.BytesIO()

    # Write the synthesized audio directly to the buffer as a WAV file
    with wave.open(wav_buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)  # 16-bit PCM
        wav_file.setframerate(22050)
        voice.synthesize_wav(text, wav_file)

    # Reset the buffer pointer to the beginning
    wav_buffer.seek(0)

    # Stream the WAV byte stream back to the client
    return StreamingResponse(wav_buffer, media_type="audio/wav")
