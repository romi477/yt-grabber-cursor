import json
import re
import subprocess
import threading
from pathlib import Path
from typing import TextIO
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from jobs import update_job

DATA_DIR = Path("data")

BASE_CMD = [
    "yt-dlp",
    "--no-playlist",
    "--js-runtimes",
    "node",
    "--remote-components",
    "ejs:github",
    "--newline",
]

FORMAT_MAP = {
    "best": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
    "1080": "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080]",
    "720": "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720]",
    "480": "bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/best[height<=480]",
    "360": "bestvideo[height<=360][ext=mp4]+bestaudio[ext=m4a]/best[height<=360]",
}

TIMEOUT = 600  # seconds
INFO_TIMEOUT = 60


def clean_url(url: str) -> str:
    """Strip playlist/index params so any copy-pasted YouTube URL works as a single video."""
    parsed = urlparse(url)
    params = parse_qs(parsed.query, keep_blank_values=True)
    for key in ("list", "index", "pp"):
        params.pop(key, None)
    clean = parsed._replace(query=urlencode(params, doseq=True))
    return urlunparse(clean)


def _parse_progress(line: str) -> float | None:
    """Extract download percentage from a yt-dlp output line."""
    match = re.search(r"\[download\]\s+([\d.]+)%", line)
    if match:
        return float(match.group(1))
    return None


def _resolve_output_path(line: str) -> Path | None:
    """Parse a --print after_move:filepath line into an existing file path."""
    text = line.strip()
    if not text or text.startswith("["):
        return None
    path = Path(text)
    if not path.is_absolute():
        path = Path.cwd() / path
    return path if path.is_file() else None


def _newest_file(directory: Path) -> Path:
    """Return the most recently modified file in directory."""
    files = [p for p in directory.iterdir() if p.is_file()]
    if not files:
        raise RuntimeError("Download finished but no output file was found")
    return max(files, key=lambda p: p.stat().st_mtime)


def _run(cmd: list[str], job_id: str) -> Path:
    """Run yt-dlp, stream progress into the job store, enforce timeout."""
    state: dict[str, Path | None] = {"filepath": None}

    def _read_stdout(pipe: TextIO | None) -> None:
        if pipe is None:
            return
        for line in iter(pipe.readline, ""):
            pct = _parse_progress(line)
            if pct is not None:
                update_job(job_id, progress=pct)
                continue
            resolved = _resolve_output_path(line)
            if resolved is not None:
                state["filepath"] = resolved
        pipe.close()

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    reader = threading.Thread(
        target=_read_stdout,
        args=(proc.stdout,),
        daemon=True,
    )
    reader.start()

    try:
        proc.wait(timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
        msg = "Download timed out after 600 seconds"
        update_job(job_id, status="error", error=msg)
        reader.join()
        raise RuntimeError(msg) from None

    reader.join()

    if proc.returncode != 0:
        msg = f"yt-dlp exited with code {proc.returncode}"
        update_job(job_id, status="error", error=msg)
        raise RuntimeError(msg)

    filepath = state["filepath"]
    if filepath is None:
        filepath = _newest_file(DATA_DIR)
    return filepath


def get_info(url: str) -> dict:
    """Return video metadata (title, thumbnail, formats) without downloading."""
    url = clean_url(url)
    cmd = [*BASE_CMD, "--dump-json", url]
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=INFO_TIMEOUT,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or "").strip()
        raise RuntimeError(detail or "Failed to fetch video info")

    data = json.loads(result.stdout)
    heights = sorted(
        {f["height"] for f in data.get("formats", []) if f.get("height")},
        reverse=True,
    )
    return {
        "title": data.get("title"),
        "thumbnail": data.get("thumbnail"),
        "duration": data.get("duration"),
        "uploader": data.get("uploader"),
        "available_qualities": [str(h) for h in heights if h >= 360],
    }


def download_video(url: str, quality: str, job_id: str) -> Path:
    """Download a YouTube video as mp4 and return the file path."""
    url = clean_url(url)
    DATA_DIR.mkdir(exist_ok=True)
    fmt = FORMAT_MAP.get(quality, FORMAT_MAP["best"])

    cmd = [
        *BASE_CMD,
        "--format",
        fmt,
        "--merge-output-format",
        "mp4",
        "--output",
        str(DATA_DIR / "%(title)s.%(ext)s"),
        "--print",
        "after_move:filepath",
        url,
    ]
    update_job(job_id, status="running", progress=0)
    path = _run(cmd, job_id)
    update_job(job_id, status="done", progress=100, result=path.name)
    return path


def download_audio(url: str, job_id: str) -> Path:
    """Download best audio and convert to mp3 320kbps."""
    url = clean_url(url)
    DATA_DIR.mkdir(exist_ok=True)

    cmd = [
        *BASE_CMD,
        "--format",
        "bestaudio/best",
        "--extract-audio",
        "--audio-format",
        "mp3",
        "--audio-quality",
        "320K",
        "--output",
        str(DATA_DIR / "%(title)s.%(ext)s"),
        "--print",
        "after_move:filepath",
        url,
    ]
    update_job(job_id, status="running", progress=0)
    path = _run(cmd, job_id)
    update_job(job_id, status="done", progress=100, result=path.name)
    return path
