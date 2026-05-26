from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import fitz
from pptx import Presentation


class PPTExportError(RuntimeError):
    """Raised when a presentation cannot be exported to slide images."""


@dataclass(frozen=True)
class SlideExportResult:
    slide_count: int
    image_paths: list[Path]
    pdf_path: Path


def count_ppt_slides(ppt_path: Path) -> int:
    return len(Presentation(str(ppt_path)).slides)


def _find_libreoffice() -> str | None:
    candidates = [
        shutil.which("soffice"),
        shutil.which("libreoffice"),
        "/Applications/LibreOffice.app/Contents/MacOS/soffice",
    ]
    return next((str(candidate) for candidate in candidates if candidate and Path(candidate).exists()), None)


def _convert_pptx_to_pdf(ppt_path: Path, work_dir: Path) -> Path:
    soffice = _find_libreoffice()
    if not soffice:
        raise PPTExportError(
            "LibreOffice was not found. Install LibreOffice and make sure 'soffice' is on PATH."
        )

    work_dir.mkdir(parents=True, exist_ok=True)
    command = [
        soffice,
        "--headless",
        "--convert-to",
        "pdf",
        "--outdir",
        str(work_dir),
        str(ppt_path),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise PPTExportError(
            "LibreOffice failed to convert PPTX to PDF.\n"
            f"stdout: {completed.stdout.strip()}\n"
            f"stderr: {completed.stderr.strip()}"
        )

    pdf_path = work_dir / f"{ppt_path.stem}.pdf"
    if not pdf_path.exists():
        pdf_candidates = sorted(work_dir.glob("*.pdf"))
        if not pdf_candidates:
            raise PPTExportError("LibreOffice finished but no PDF was produced.")
        pdf_path = pdf_candidates[0]
    return pdf_path


def _render_pdf_to_pngs(pdf_path: Path, slides_dir: Path, dpi: int) -> list[Path]:
    slides_dir.mkdir(parents=True, exist_ok=True)
    for existing in slides_dir.glob("slide_*.png"):
        existing.unlink()

    document = fitz.open(pdf_path)
    zoom = dpi / 72
    matrix = fitz.Matrix(zoom, zoom)
    image_paths: list[Path] = []
    for index, page in enumerate(document, start=1):
        pixmap = page.get_pixmap(matrix=matrix, alpha=False)
        output_path = slides_dir / f"slide_{index:03d}.png"
        pixmap.save(output_path)
        image_paths.append(output_path)
    document.close()
    return image_paths


def export_slides(ppt_path: Path, slides_dir: Path, work_dir: Path, dpi: int = 144) -> SlideExportResult:
    if not ppt_path.exists():
        raise FileNotFoundError(f"PPTX not found: {ppt_path}")
    if ppt_path.suffix.lower() != ".pptx":
        raise ValueError(f"Expected a .pptx file, got: {ppt_path}")

    slide_count = count_ppt_slides(ppt_path)
    pdf_path = _convert_pptx_to_pdf(ppt_path, work_dir)
    image_paths = _render_pdf_to_pngs(pdf_path, slides_dir, dpi)
    if len(image_paths) != slide_count:
        raise PPTExportError(
            f"Exported {len(image_paths)} slide images, but python-pptx found {slide_count} slides."
        )
    return SlideExportResult(slide_count=slide_count, image_paths=image_paths, pdf_path=pdf_path)
