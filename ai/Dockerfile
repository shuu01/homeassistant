FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends \
        wget \
        ca-certificates \
        libportaudio2 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY ai/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY ai/assistant.py .
CMD ["python", "assistant.py"]
