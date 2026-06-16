from io import BytesIO
import wave

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from piper.voice import PiperVoice


MODEL_PATH = "/models/en_US-lessac-medium.onnx"

app = FastAPI()

voice = None


class SynthesizeRequest(BaseModel):
    text: str


@app.on_event("startup")
def startup():
    global voice

    print(f"Loading voice: {MODEL_PATH}")

    voice = PiperVoice.load(MODEL_PATH)

    print("Voice loaded")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/synthesize")
def synthesize(req: SynthesizeRequest):
    if not req.text.strip():
        raise HTTPException(
            status_code=400,
            detail="text is required",
        )

    wav_buffer = BytesIO()

    with wave.open(wav_buffer, "wb") as wav_file:
        voice.synthesize(
            req.text,
            wav_file,
        )

    return Response(
        content=wav_buffer.getvalue(),
        media_type="audio/wav",
    )
