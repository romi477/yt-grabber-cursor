"""Speech-to-text via OpenAI Whisper (runs in a FastAPI BackgroundTask)."""

import os
from pathlib import Path

import whisper

from jobs import update_job

DEFAULT_MODEL = "base"
VALID_MODELS = frozenset({"tiny", "base", "small", "medium"})

WHISPER_CACHE_DIR = Path(
    os.environ.get("WHISPER_CACHE_DIR", Path(__file__).resolve().parent / "whisper-cache")
)


def transcribe(
    filepath: Path,
    job_id: str,
    model_name: str = DEFAULT_MODEL,
) -> str:
    """Transcribe an audio/video file and store the text on the job."""
    if model_name not in VALID_MODELS:
        msg = (
            f"Invalid model {model_name!r}. "
            f"Choose one of: {', '.join(sorted(VALID_MODELS))}."
        )
        update_job(job_id, status="error", error=msg)
        raise ValueError(msg)

    path = filepath if filepath.is_absolute() else Path.cwd() / filepath
    if not path.is_file():
        msg = f"File not found: {path}"
        update_job(job_id, status="error", error=msg)
        raise FileNotFoundError(msg)

    WHISPER_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    update_job(job_id, status="running", progress=0)
    try:
        model = whisper.load_model(model_name, download_root=str(WHISPER_CACHE_DIR))
        result = model.transcribe(str(path))
        text = (result.get("text") or "").strip()
        update_job(
            job_id,
            status="done",
            progress=100,
            result=text,
            model=model_name,
        )
        return text
    except Exception as exc:
        update_job(job_id, status="error", error=str(exc))
        raise
