"""Export transcript text to txt, pdf, or json in transcripts/."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fpdf import FPDF

TRANSCRIPTS_DIR = Path("transcripts")
ExportFormat = Literal["txt", "pdf", "json"]

DEJAVU_REGULAR = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
DEJAVU_BOLD = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")


def _safe_stem(name: str | None) -> str:
    if not name:
        return "transcript"
    stem = re.sub(r"[^\w\s-]", "", name, flags=re.UNICODE).strip()
    stem = re.sub(r"\s+", "_", stem)
    return stem[:80] or "transcript"


def _output_path(stem: str, ext: str) -> Path:
    TRANSCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return TRANSCRIPTS_DIR / f"{stem}_{timestamp}.{ext}"


def _build_pdf(text: str, heading: str) -> FPDF:
    """Build a PDF with Unicode support when DejaVu fonts are available."""
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    if DEJAVU_REGULAR.is_file() and DEJAVU_BOLD.is_file():
        pdf.add_font("DejaVu", style="", fname=str(DEJAVU_REGULAR))
        pdf.add_font("DejaVu", style="B", fname=str(DEJAVU_BOLD))
        family = "DejaVu"
    else:
        family = "Helvetica"

    pdf.set_font(family, style="B", size=16)
    pdf.multi_cell(0, 10, heading)
    pdf.ln(4)
    pdf.set_font(family, size=11)
    pdf.multi_cell(0, 6, text)
    return pdf


def export_txt(text: str, *, title: str | None = None) -> Path:
    path = _output_path(_safe_stem(title), "txt")
    path.write_text(text, encoding="utf-8")
    return path


def export_pdf(text: str, *, title: str | None = None) -> Path:
    path = _output_path(_safe_stem(title), "pdf")
    heading = title or "Transcript"
    pdf = _build_pdf(text, heading)
    pdf.output(str(path))
    return path


def export_json(
    text: str,
    *,
    title: str | None = None,
    url: str | None = None,
    model: str | None = None,
) -> Path:
    path = _output_path(_safe_stem(title), "json")
    payload = {
        "title": title,
        "url": url,
        "transcript": text,
        "model": model,
        "exported_at": datetime.now(timezone.utc).isoformat(),
    }
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def export_transcript(
    text: str,
    fmt: ExportFormat,
    *,
    title: str | None = None,
    url: str | None = None,
    model: str | None = None,
) -> Path:
    """Export transcript to transcripts/ and return the saved file path."""
    if fmt == "txt":
        return export_txt(text, title=title)
    if fmt == "pdf":
        return export_pdf(text, title=title)
    if fmt == "json":
        return export_json(text, title=title, url=url, model=model)
    raise ValueError(f"Unsupported format: {fmt!r}")
