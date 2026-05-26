from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


class VideoBuildError(RuntimeError):
    """Raised when ffmpeg/ffprobe video operations fail."""


@dataclass(frozen=True)
class Segment:
    slide_number: int
    path: Path
    duration_seconds: float


def _require_binary(name: str) -> None:
    if not shutil.which(name):
        raise VideoBuildError(f"Required binary not found on PATH: {name}")


def probe_audio_duration(audio_path: Path) -> float:
    _require_binary("ffprobe")
    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(audio_path),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise VideoBuildError(f"ffprobe failed for {audio_path}: {completed.stderr.strip()}")
    return float(completed.stdout.strip())


def build_slide_segment(
    slide_number: int,
    image_path: Path,
    audio_path: Path,
    output_path: Path,
    padding_seconds: float,
    resolution: str = "1920x1080",
) -> Segment:
    _require_binary("ffmpeg")
    duration = probe_audio_duration(audio_path)
    total_duration = duration + padding_seconds
    width, height = resolution.split("x", maxsplit=1)
    vf = (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=white,"
        "setsar=1"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "ffmpeg",
        "-y",
        "-loop",
        "1",
        "-i",
        str(image_path),
        "-i",
        str(audio_path),
        "-t",
        f"{total_duration:.3f}",
        "-vf",
        vf,
        "-af",
        f"apad=pad_dur={padding_seconds}",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-movflags",
        "+faststart",
        str(output_path),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise VideoBuildError(f"ffmpeg failed for slide {slide_number}: {completed.stderr.strip()}")
    return Segment(slide_number=slide_number, path=output_path, duration_seconds=total_duration)


def concatenate_segments(segments: list[Segment], output_path: Path, concat_list_path: Path) -> Path:
    _require_binary("ffmpeg")
    if not segments:
        raise VideoBuildError("No video segments were created; nothing to concatenate.")

    concat_list_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"file '{segment.path.resolve().as_posix()}'" for segment in segments]
    concat_list_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "ffmpeg",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(concat_list_path),
        "-c",
        "copy",
        str(output_path),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise VideoBuildError(f"ffmpeg concat failed: {completed.stderr.strip()}")
    return output_path
