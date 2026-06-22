FROM debian:stable-slim AS builder

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        git \
        build-essential \
        ca-certificates \
        cmake && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /src

RUN git clone --depth=1 https://github.com/ggml-org/whisper.cpp.git .

RUN cmake -B build \
    -DCMAKE_BUILD_TYPE=Release \
    -DGGML_NATIVE=ON \
    -DBUILD_SHARED_LIBS=OFF

RUN cmake --build build \
    --target whisper-server \
    -j$(nproc)

FROM debian:stable-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        wget \
        ca-certificates \
        libgomp1 && \
    rm -rf /var/lib/apt/lists/*

COPY --from=builder /src/build/bin/whisper-server /usr/local/bin/whisper-server

WORKDIR /models
RUN wget -O /models/ggml-base.en.bin \
    https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.en.bin

EXPOSE 8080

CMD ["/usr/local/bin/whisper-server", "-m", "/models/ggml-base.en.bin", \
  "--host", "0.0.0.0", "--port", "8080"]
