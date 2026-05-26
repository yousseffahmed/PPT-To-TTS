from __future__ import annotations

import argparse
import sys
from pathlib import Path

from modules.ppt_exporter import count_ppt_slides, export_slides
from modules.script_parser import parse_script
from modules.tts_engine import create_tts_engine
from modules.validator import build_validation_report, write_report
from modules.video_builder import build_slide_segment, concatenate_segments, probe_audio_duration


ROOT = Path(__file__).resolve().parent
DEFAULT_SLIDES_DIR = ROOT / "tmp" / "slides"
DEFAULT_AUDIO_DIR = ROOT / "tmp" / "audio"
DEFAULT_SEGMENTS_DIR = ROOT / "tmp" / "video_segments"
DEFAULT_REPORTS_DIR = ROOT / "reports"
DEFAULT_WORK_DIR = ROOT / "tmp"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a narrated MP4 from a PPTX and slide-based DOCX script.")
    parser.add_argument("--ppt", required=True, type=Path, help="Input PowerPoint .pptx path")
    parser.add_argument("--script", required=True, type=Path, help="Input Word .docx script path")
    parser.add_argument("--out", required=True, type=Path, help="Output MP4 path")
    parser.add_argument("--tts", choices=["xtts", "edge"], default="xtts", help="TTS backend")
    parser.add_argument("--voice", default=None, help="Voice preset or voice name for the selected TTS backend")
    parser.add_argument("--padding", type=float, default=0.5, help="Seconds of silence after each slide narration")
    parser.add_argument("--dpi", type=int, default=144, help="Slide image render DPI")
    parser.add_argument("--resolution", default="1920x1080", help="Output video resolution, e.g. 1920x1080")
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORTS_DIR / "validation_report.json")
    return parser.parse_args()


def _clean_outputs() -> None:
    for folder, pattern in [
        (DEFAULT_AUDIO_DIR, "slide_*.mp3"),
        (DEFAULT_SEGMENTS_DIR, "slide_*.mp4"),
    ]:
        folder.mkdir(parents=True, exist_ok=True)
        for path in folder.glob(pattern):
            path.unlink()


def run() -> int:
    args = _parse_args()
    ppt_path = args.ppt.expanduser().resolve()
    script_path = args.script.expanduser().resolve()
    output_path = args.out.expanduser().resolve()
    report_path = args.report.expanduser().resolve()

    ppt_slide_count = count_ppt_slides(ppt_path)
    script_parse = parse_script(script_path)
    parsed_slide_numbers = sorted(script_parse.sections.keys())
    print(f"Parsed slide numbers from DOCX: {parsed_slide_numbers}")

    initial_report = build_validation_report(
        ppt_slide_count=ppt_slide_count,
        sections=script_parse.sections,
        duplicate_script_sections=script_parse.duplicate_slide_numbers,
        padding_seconds=args.padding,
    )
    write_report(initial_report, report_path)
    print(f"Validation report written: {report_path}")
    if initial_report.missing_scripts:
        print(f"Missing scripts for slides: {initial_report.missing_scripts}")
    if initial_report.extra_scripts:
        print(f"Extra scripts without matching slides: {initial_report.extra_scripts}")

    _clean_outputs()
    slide_export = export_slides(ppt_path, DEFAULT_SLIDES_DIR, DEFAULT_WORK_DIR, dpi=args.dpi)

    tts_engine = create_tts_engine(args.tts, voice=args.voice)
    audio_durations: dict[int, float] = {}
    segments = []

    for slide_number in initial_report.matched_slides:
        section = script_parse.sections[slide_number]
        image_path = slide_export.image_paths[slide_number - 1]
        audio_path = DEFAULT_AUDIO_DIR / f"slide_{slide_number:03d}.mp3"
        segment_path = DEFAULT_SEGMENTS_DIR / f"slide_{slide_number:03d}.mp4"

        print(f"Generating narration for slide {slide_number}...")
        tts_engine.synthesize(section.text, audio_path)
        audio_durations[slide_number] = probe_audio_duration(audio_path)

        print(f"Building video segment for slide {slide_number}...")
        segment = build_slide_segment(
            slide_number=slide_number,
            image_path=image_path,
            audio_path=audio_path,
            output_path=segment_path,
            padding_seconds=args.padding,
            resolution=args.resolution,
        )
        segments.append(segment)

    final_report = build_validation_report(
        ppt_slide_count=slide_export.slide_count,
        sections=script_parse.sections,
        duplicate_script_sections=script_parse.duplicate_slide_numbers,
        audio_durations=audio_durations,
        padding_seconds=args.padding,
    )
    write_report(final_report, report_path)

    concatenate_segments(segments, output_path, DEFAULT_SEGMENTS_DIR / "concat.txt")
    print(f"Final MP4 written: {output_path}")
    print(f"Estimated duration: {final_report.estimated_duration_seconds:.1f}s")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(run())
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)
