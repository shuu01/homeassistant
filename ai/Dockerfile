FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends \
        libportaudio2 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN wget -O kokoro-v1.0.onnx https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx
RUN wget -O voices-v1.0.bin https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin

COPY ai/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY ai/assistant.py .
CMD ["python", "assistant.py"]
