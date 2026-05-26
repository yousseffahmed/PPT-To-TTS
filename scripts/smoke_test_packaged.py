from __future__ import annotations

import argparse
import os
import sys
import traceback
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

MPLCONFIGDIR = PROJECT_ROOT / "tmp" / "matplotlib"
MPLCONFIGDIR.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(MPLCONFIGDIR))


def report(name: str, ok: bool, detail: str = "") -> bool:
    status = "PASS" if ok else "FAIL"
    print(f"[{status}] {name}{': ' + detail if detail else ''}")
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test packaged runtime dependencies.")
    parser.add_argument("--docx", type=Path, help="Optional DOCX file to verify python-docx parsing.")
    args = parser.parse_args()

    ok = True

    try:
        import TTS  # noqa: F401

        tts_file = getattr(TTS, "__file__", "")
        ok &= report("TTS package import", True, tts_file)
    except FileNotFoundError as exc:
        ok &= report("TTS package import", False, f"Missing package data: {exc}")
    except Exception:
        ok &= report("TTS package import", False, traceback.format_exc())

    try:
        from TTS.api import TTS as CoquiTTS  # noqa: F401

        ok &= report("TTS.api import", True)
    except Exception:
        ok &= report("TTS.api import", False, traceback.format_exc())

    try:
        from docx import Document

        ok &= report("python-docx import", True)
        if args.docx:
            docx_path = args.docx.expanduser().resolve(strict=False)
            document = Document(str(docx_path))
            paragraphs = [paragraph.text for paragraph in document.paragraphs]
            ok &= report("DOCX paragraph read", bool(paragraphs), f"{len(paragraphs)} paragraphs from {docx_path}")
    except Exception:
        ok &= report("python-docx/DOCX read", False, traceback.format_exc())

    try:
        from app.core.pipeline_runner import detect_ffmpeg_paths, load_settings

        ffmpeg, ffprobe = detect_ffmpeg_paths(load_settings())
        ok &= report("FFmpeg detection", bool(ffmpeg and ffprobe), f"ffmpeg={ffmpeg}, ffprobe={ffprobe}")
    except Exception:
        ok &= report("FFmpeg detection", False, traceback.format_exc())

    try:
        from app.core.ppt_exporter import _find_libreoffice

        soffice = _find_libreoffice()
        ok &= report("LibreOffice detection", bool(soffice), str(soffice))
    except Exception:
        ok &= report("LibreOffice detection", False, traceback.format_exc())

    try:
        from app.core.paths import ensure_user_dirs, user_data_dir

        ensure_user_dirs()
        test_file = user_data_dir() / ".smoke_test"
        test_file.write_text("ok", encoding="utf-8")
        test_file.unlink(missing_ok=True)
        ok &= report("User data directory writable", True, str(user_data_dir()))
    except Exception:
        ok &= report("User data directory writable", False, traceback.format_exc())

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
