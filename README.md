# yt-grabber

Web service for downloading YouTube video/audio and transcribing with Whisper.

## Quick start

From this directory (`project/`):

```bash
docker compose up --build
```

- **UI (use this):** http://localhost:8080 — nginx serves the frontend and proxies `/api` to the backend
- **Backend API (direct):** http://localhost:8001 — optional; same API as via the UI proxy

Port **8080** avoids conflicts with other services on host port 80. To use port 80 instead, change `frontend` in `docker-compose.yml` to `"80:80"`.

Downloaded files are stored in `backend/data/`. Transcripts are written to `backend/transcripts/`.

**Try it:** open http://localhost:8080 → paste a YouTube URL → **Get Info** → choose Video/Audio → **Download** → **Save to disk** when finished.

## Runtime dependencies (backend)

| Tool | Why |
|------|-----|
| **Node.js** | YouTube serves player logic as JavaScript. yt-dlp runs that code via `--js-runtimes node` to derive download URLs and unlock **720p / 1080p+** streams. Without Node, only low-quality formats (~360p) are available. |
| **ffmpeg** | Merges separate video/audio streams into one file (mp4/mp3). |
| **yt-dlp** | Downloads from YouTube; uses `--remote-components ejs:github` for up-to-date JS extractors. |

In Docker, Node.js and ffmpeg are installed in `backend/Dockerfile`. For local runs outside Docker, install them yourself (e.g. `brew install node ffmpeg` on macOS).

## Local backend (without Docker)

Dependencies are managed with [uv](https://docs.astral.sh/uv/):

Requires **Node.js** and **ffmpeg** on your PATH (see table above).

```bash
cd backend
uv venv
uv pip install -r requirements.txt
uv run uvicorn main:app --reload --host 0.0.0.0 --port 8001
```

## Project layout

```
project/
├── backend/          # FastAPI + yt-dlp + Whisper
├── frontend/         # Static UI (nginx)
└── docker-compose.yml
```
