from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from downloader import DATA_DIR, download_audio, download_video, get_info
from exporter import ExportFormat, export_transcript
from jobs import create_job, get_job, update_job
from transcriber import DEFAULT_MODEL, VALID_MODELS, transcribe

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

MEDIA_EXTENSIONS = frozenset({
    ".mp3",
    ".mp4",
    ".m4a",
    ".webm",
    ".mkv",
    ".wav",
    ".ogg",
    ".opus",
    ".flac",
    ".aac",
    ".avi",
    ".mov",
    ".wma",
})

app = FastAPI(title="yt-grabber")


def _is_media_file(path: Path) -> bool:
    return path.suffix.lower() in MEDIA_EXTENSIONS


class InfoRequest(BaseModel):
    url: str


class DownloadRequest(BaseModel):
    url: str
    type: Literal["video", "audio"]
    quality: str | None = None


class TranscribeRequest(BaseModel):
    filename: str
    model: str = DEFAULT_MODEL


class ExportRequest(BaseModel):
    job_id: str
    format: ExportFormat
    title: str | None = None
    url: str | None = None


def _safe_data_path(filename: str) -> Path:
    """Resolve a filename under DATA_DIR, rejecting path traversal."""
    if not filename or filename in (".", ".."):
        raise HTTPException(status_code=404, detail="File not found")
    if "/" in filename or "\\" in filename:
        raise HTTPException(status_code=404, detail="File not found")
    root = DATA_DIR.resolve()
    path = (root / filename).resolve()
    if not path.is_file() or not path.is_relative_to(root):
        raise HTTPException(status_code=404, detail="File not found")
    return path


def _run_download(job_id: str, url: str, media_type: str, quality: str) -> None:
    try:
        if media_type == "video":
            download_video(url, quality, job_id)
        else:
            download_audio(url, job_id)
    except Exception as exc:
        job = get_job(job_id)
        if job is None or job.get("status") != "error":
            update_job(job_id, status="error", error=str(exc))


def _run_transcribe(job_id: str, filepath: Path, model_name: str) -> None:
    try:
        transcribe(filepath, job_id, model_name)
    except Exception as exc:
        job = get_job(job_id)
        if job is None or job.get("status") != "error":
            update_job(job_id, status="error", error=str(exc))


@app.post("/api/info")
def api_info(body: InfoRequest) -> dict:
    try:
        return get_info(body.url)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/download")
def api_download(body: DownloadRequest, background_tasks: BackgroundTasks) -> dict:
    if body.type == "video" and not body.quality:
        raise HTTPException(status_code=400, detail="quality is required for video downloads")

    job_id = create_job()
    quality = body.quality or "best"
    background_tasks.add_task(_run_download, job_id, body.url, body.type, quality)
    return {"job_id": job_id}


@app.get("/api/jobs/{job_id}")
def api_job(job_id: str) -> dict:
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.post("/api/transcribe")
def api_transcribe(body: TranscribeRequest, background_tasks: BackgroundTasks) -> dict:
    if body.model not in VALID_MODELS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid model. Choose one of: {', '.join(sorted(VALID_MODELS))}.",
        )
    filepath = _safe_data_path(body.filename)
    if not _is_media_file(filepath):
        raise HTTPException(
            status_code=400,
            detail="Only media files can be transcribed (audio/video).",
        )

    job_id = create_job()
    background_tasks.add_task(_run_transcribe, job_id, filepath, body.model)
    return {"job_id": job_id}


@app.get("/api/transcribe/{job_id}")
def api_transcribe_job(job_id: str) -> dict:
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.post("/api/export")
def api_export(body: ExportRequest) -> FileResponse:
    job = get_job(body.job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.get("status") != "done":
        raise HTTPException(status_code=400, detail="Transcription is not finished yet")

    text = job.get("result")
    if not text:
        raise HTTPException(status_code=400, detail="Transcript is empty")

    try:
        path = export_transcript(
            text,
            body.format,
            title=body.title,
            url=body.url,
            model=job.get("model"),
        )
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    media_types = {
        "txt": "text/plain; charset=utf-8",
        "pdf": "application/pdf",
        "json": "application/json",
    }
    return FileResponse(
        path,
        filename=path.name,
        media_type=media_types.get(body.format, "application/octet-stream"),
    )


@app.get("/api/files")
def api_list_files() -> list[dict]:
    DATA_DIR.mkdir(exist_ok=True)
    files: list[dict] = []
    for path in sorted(DATA_DIR.iterdir(), key=lambda p: p.name.lower()):
        if not path.is_file() or not _is_media_file(path):
            continue
        stat = path.stat()
        files.append(
            {
                "name": path.name,
                "size": stat.st_size,
                "modified": datetime.fromtimestamp(
                    stat.st_mtime, tz=timezone.utc
                ).isoformat(),
            }
        )
    return files


@app.get("/api/files/{filename}")
def api_get_file(filename: str) -> FileResponse:
    path = _safe_data_path(filename)
    return FileResponse(
        path,
        filename=filename,
        media_type="application/octet-stream",
    )


if FRONTEND_DIR.is_dir():
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
