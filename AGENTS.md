# AGENTS.md

## What this is

A personal Home Assistant + voice assistant (lva) + music stack. All services run as Docker containers via `docker-compose.yml`. **No test suite, linter, formatter, or typecheck** — verify changes by rebuilding the touched container and reading its logs.

## Deployment layout (read first)

`docker-compose.yml` resolves most volumes from `${HOME}`, not the repo: `${HOME}/config`, `${HOME}/media`, `${HOME}/esphome`, `${HOME}/mqtt`, `${HOME}/mpd`, `${HOME}/mympd`; `mass` mounts its data dir from `${USERDIR:-$HOME}/docker/music-assistant-server`. The repo's top-level `esphome/`, `mqtt/` dirs mirror that layout — i.e. the repo is meant to be checked out at `$HOME` on the host that runs compose. On a dev Mac (`$HOME` points elsewhere) `docker compose up` mounts non-existent paths; set `export HOME=<repo>` first or run on the actual host. `.env` is also read by compose for `$VAR` substitution (see Environment).

## Services

| Service | Purpose | Ports | Notes |
|---------|---------|-------|-------|
| `homeassistant` | HA core | 8123 | `network_mode: host`, privileged. Mounts `${HOME}/config`, `${HOME}/media`. |
| `esphome` | IoT device firmware | — | `network_mode: host`. Mounts **only** `${HOME}/esphome` as `/config` — not the repo root. |
| `mqtt` | Mosquitto broker | 1883 | `network_mode: host`. Config: `${HOME}/mqtt/mosquitto.conf` (repo: `mqtt/mosquitto.conf`). |
| `metube` | YouTube downloader | 8081→8081 | Downloads into `${HOME}/media`. |
| `mass` | Music Assistant server | — | `network_mode: host`. Volumes use `${USERDIR:-$HOME}` and a placeholder music path (see Gotchas). |
| `mpd` / `mympd` | Music player + web UI | 6600, 8080 | Play files from `${HOME}/media`. mpd passes `/dev/snd`. |
| `whisper` | STT (whisper.cpp) | 8081→8080 | Built from source (git clone + cmake) in `whisper/Dockerfile`; model downloaded via `ADD` at build. |
| `wyoming-whisper-api-client` | Bridges whisper → Wyoming for HA | 10300→10300 | `depends_on` whisper; targets `http://whisper:8080`. |
| `kokoro` | TTS (FastAPI) | 8080→8080 | `env_file: .env`. Downloads ONNX model from GitHub at build. |
| `lva` | Voice assistant | — | `network_mode: host`, `env_file: .env`. Needs PulseAudio socket; `lva-init` chowns its named volumes first. Host audio setup lives in `README.md`. |

## Build & deploy

```sh
# Rebuild and restart everything
docker compose up -d --build

# Rebuild a single service
docker compose up -d --build kokoro

# View logs
docker compose logs -f lva
```

- Rebuilding `whisper` compiles whisper.cpp from source — slow. Avoid full-stack `--build` unless needed.
- `whisper` and `kokoro` downloads happen inside `docker build` (`ADD` from GitHub/HuggingFace) — builds need outbound network.
- CI (`.github/workflows/docker.yml`) builds only `whisper`/`kokoro` (push to `main`, paths-filtered).

## Environment

`.env` is gitignored, read both by compose for `$VAR` substitution and injected via `env_file` into `kokoro`, `lva`, and `lva-init`. Key vars:

- `LVA_USER_ID`/`LVA_USER_GROUP` — host uid/gid mapping for the lva containers (also used by compose's `user:`)
- `PULSE_SERVER` — PulseAudio socket path; defaults to `/run/user/$LVA_USER_ID/pulse/native`
- `WAKEUP_SOUND` — path to a static wake sound on the host (e.g. `${HOME}/media/wakeup_sounds/sound.wav`); must exist
- `WAKE_MODEL`, `CLIENT_NAME`, `LVA_NAME`, `HOST`, `LISTEN_DURING_WAKE_SOUND` — lva tuning

## Gotchas

- **Two port conflicts:** `whisper` vs `metube` both bind host 8081; `kokoro` vs `mympd` both bind host 8080. Run conflicting pairs one at a time or remap.
- **`mass` has placeholder paths:** `- /path/to/your/music:/media:ro` must be pointed at real music, and its data dir resolves to `${USERDIR:-$HOME}/docker/music-assistant-server` — set `USERDIR` or it lands under `$HOME`.
- **`esphome` mounts only `${HOME}/esphone`** — repo-root files are not visible inside it.
- **`lva`** needs a PulseAudio socket at `/run/user/$LVA_USER_ID/pulse/native` with `PULSE_SERVER` set, and `WAKEUP_SOUND` must exist on the host. Host-side setup (PipeWire, systemd linger, udev) is documented in `README.md`.
- **No automated tests.** Validate by rebuilding the touched container and checking `docker compose logs`.