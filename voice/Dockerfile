FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        wget \
        ca-certificates && \
    rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
    fastapi \
    uvicorn \
    kokoro-onnx \
    soundfile

WORKDIR /models
RUN wget -O kokoro-v1.0.onnx \
    https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files/kokoro-v1.0.onnx

RUN wget -O voices-v1.0.bin \
    https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files/voices-v1.0.bin


WORKDIR /app
COPY voice/server.py .

EXPOSE 8080

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8080"]
