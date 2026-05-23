from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from downloader import DATA_DIR, download_audio, download_video, get_info
from jobs import create_job, get_job, update_job

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

app = FastAPI(title="yt-grabber")


class InfoRequest(BaseModel):
    url: str


class DownloadRequest(BaseModel):
    url: str
    type: Literal["video", "audio"]
    quality: str | None = None


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


@app.get("/api/files")
def api_list_files() -> list[dict]:
    DATA_DIR.mkdir(exist_ok=True)
    files: list[dict] = []
    for path in sorted(DATA_DIR.iterdir(), key=lambda p: p.name.lower()):
        if not path.is_file():
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
