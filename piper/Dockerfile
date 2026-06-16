FROM python:3.12-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        wget \
        xz-utils \
        libsndfile1 && \
    rm -rf /var/lib/apt/lists/*

RUN wget -O /tmp/piper.tar.gz \
    https://github.com/rhasspy/piper/releases/download/v1.2.0/piper_linux_x86_64.tar.gz && \
    mkdir /opt/piper && \
    tar -xzf /tmp/piper.tar.gz -C /opt/piper --strip-components=1 && \
    rm /tmp/piper.tar.gz

ENV PATH="/opt/piper:${PATH}"

WORKDIR /app

RUN pip install --no-cache-dir fastapi uvicorn

COPY server.py .

EXPOSE 8080

CMD ["python", "server.py"]
