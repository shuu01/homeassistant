# AGENTS.md

## What this is

A personal Home Assistant setup with a custom voice assistant. All services run as Docker containers via `docker-compose.yml`. There is **no test suite, linter, formatter, or typecheck** — changes are verified by running the stack.

## Services (docker-compose)

| Service | Purpose | Port | Notes |
|---------|---------|------|-------|
| `homeassistant` | HA core | 8123 (internal) | Mounts `./config` |
| `esphome` | IoT device firmware | — | **Mounts entire repo root as `/config`** — any file you add to the repo is visible inside this container |
| `mqtt` | Mosquitto broker | host network | Config at `mqtt/mosquitto.conf` |
| `ai` | Voice assistant (custom) | — | Requires `/dev/snd` (audio). Entry: `ai/main.py` |
| `whisper` | STT server (whisper.cpp) | 8081→8080 | Built from source in Dockerfile |
| `kokoro` | TTS server (FastAPI) | 8080→8080 | Requires `.env` for model download on first build |
| `metube` | YouTube downloader | 8081 | **Port conflict with `whisper`** — both claim host port 8081 |
| `mpd` / `mympd` | Music player + web UI | 6600, 8080 | Plays files from `./youtube` |

## Build & deploy

```sh
# Rebuild and restart everything
docker compose up -d --build

# Rebuild a single service
docker compose up -d --build ai

# View logs
docker compose logs -f ai
```

CI (`.github/workflows/docker.yml`) only builds `whisper` and `kokoro` images on push to `main`. The `ai` image is built locally only.

## AI service (`ai/`)

Python 3.12 app. Entry point: `ai/main.py`. Runs as a single-threaded main loop with background worker threads.

**Flow:** wake word → record audio → STT → LLM → TTS → speaker output.

**Provider fallback chain** (configured in `ai/ai.py`):
- LLM: Gemini → Groq → OpenAI → OpenRouter
- TTS: Groq → Local (kokoro) → Gemini
- STT: Groq → Local (whisper)

Each provider is enabled/disabled by the presence of its API key env var. Providers auto-disable on rate limits/errors with backoff.

**Persistence:** Conversation history and child facts are stored in a GitHub Gist via `ai/storage.py` (requires `GITHUB_TOKEN` + `GIST_ID` env vars).

**Prerequisites for the `ai` container:**
- `./greetings/` and `./fallbacks/` directories must exist with `.wav` files (gitignored)
- Audio hardware (`/dev/snd`) must be available
- `.env` must set the appropriate API keys and audio device IDs

## Environment

`.env` is gitignored. The `ai`, `kokoro`, and `linux-voice-assistant` services load it via `env_file`. Key variables for the AI service:

- `GEMINI_API_KEY`, `GROQ_API_KEY`, `OPENAI_API_KEY`, `OPENROUTER_API_KEY` — each enables its provider
- `TTS_SERVER`, `STT_SERVER` — URLs for local kokoro/whisper services (enables `LocalProvider`)
- `INPUT_DEVICE`, `OUTPUT_DEVICE` — audio device indices (defaults: 0, 4)
- `GITHUB_TOKEN`, `GIST_ID` — for gist-based persistence
- `WAKE_THRESHOLD`, `VOLUME_THRESHOLD` — wake word / speech detection tuning

## Gotchas

- **ESPHome mounts the repo root.** Every file in the repo is visible inside the esphome container at `/config`. Don't put secrets at the repo root.
- **Port 8081 conflict.** Both `metube` and `whisper` map to host port 8081. Only run one at a time or remap.
- **No automated tests.** Validate changes by running the relevant container and checking logs.
- **`greetings/` and `fallbacks/` are required** but gitignored. The AI service crashes on startup without them.
- The `linux-voice-assistant` service references `LVA_USER_ID` / `LVA_USER_GROUP` env vars for user mapping and needs PulseAudio socket volume mounts.
