from __future__ import annotations

import json
import os
import hashlib
import shutil
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable

from app.core.ppt_exporter import count_ppt_slides, export_slides
from app.core.script_parser import parse_script
from app.core.paths import (
    audio_cache_dir,
    audio_dir,
    ensure_user_dirs,
    output_dir,
    reports_dir,
    resource_path,
    settings_path,
    slides_dir,
    tmp_dir,
    video_segments_dir,
)
from app.core.tts.tts_factory import create_tts_engine, xtts_config_from_values
from app.core.tts.xtts_engine import DEFAULT_REFERENCE_WAV, check_xtts_dependencies, resolve_reference_wav
from app.core.validator import ValidationReport, build_validation_report, write_report
from app.core.video_builder import build_slide_segment, concatenate_segments, probe_audio_duration


CONFIG_PATH = settings_path()
TMP_DIR = tmp_dir()
SLIDES_DIR = slides_dir()
AUDIO_DIR = audio_dir()
CACHE_AUDIO_DIR = audio_cache_dir()
SEGMENTS_DIR = video_segments_dir()
REPORTS_DIR = reports_dir()
OUTPUT_DIR = output_dir()


ProgressCallback = Callable[[int, str], None]
LogCallback = Callable[[str, str], None]
CancelCallback = Callable[[], bool]


class FriendlyPipelineError(RuntimeError):
    """An error message safe to show directly to a non-technical user."""


@dataclass(frozen=True)
class AppSettings:
    ffmpeg_path: str = ""
    libreoffice_path: str = ""
    default_output_folder: str = str(OUTPUT_DIR)
    default_voice: str = "Default Reference Voice"
    default_speech_speed: str = "+0%"
    theme: str = "Light"
    xtts_device: str = "Auto"
    xtts_preload_model: bool = False
    xtts_chunk_size: int = 900
    xtts_generation_quality: str = "Balanced"
    xtts_cache_audio: bool = True
    xtts_reference_wav: str = str(DEFAULT_REFERENCE_WAV)
    reuse_existing_narration: bool = True


@dataclass(frozen=True)
class PipelineRequest:
    ppt_path: Path
    script_path: Path
    output_folder: Path
    output_name: str
    voice: str
    speech_speed: str
    padding_seconds: float
    tts_engine: str = "xtts"
    quality_mode: str = "Balanced"
    reuse_existing_narration: bool = True


@dataclass(frozen=True)
class ValidationResult:
    report: ValidationReport
    parsed_slide_numbers: list[int]
    report_path: Path
    can_generate: bool
    warnings: list[str]
    errors: list[str]
    parser_debug: list[str] = field(default_factory=list)


def load_settings() -> AppSettings:
    ensure_user_dirs()
    if not CONFIG_PATH.exists():
        save_settings(AppSettings())
    data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    defaults = asdict(AppSettings())
    clean_data = {key: value for key, value in data.items() if key in defaults}
    return AppSettings(**{**defaults, **clean_data})


def save_settings(settings: AppSettings) -> None:
    ensure_user_dirs()
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(asdict(settings), indent=2), encoding="utf-8")


def _normalize_output_name(name: str) -> str:
    clean = name.strip() or "output.mp4"
    if not clean.lower().endswith(".mp4"):
        clean += ".mp4"
    return clean


def _candidate_from_setting(value: str, binary_names: list[str]) -> str | None:
    if not value.strip():
        return None
    path = Path(value).expanduser()
    if path.is_file():
        return str(path)
    if path.is_dir():
        for binary_name in binary_names:
            candidate = path / binary_name
            if candidate.exists():
                return str(candidate)
    return None


def _candidate_from_common_locations(binary_names: list[str]) -> str | None:
    folders = [
        resource_path("bin"),
        resource_path("app", "assets", "bin"),
        Path("/opt/homebrew/bin"),
        Path("/usr/local/bin"),
    ]
    for folder in folders:
        candidate = _candidate_from_setting(str(folder), binary_names)
        if candidate:
            return candidate
    return None


def _find_ffmpeg(settings: AppSettings) -> str | None:
    configured = _candidate_from_setting(settings.ffmpeg_path, ["ffmpeg.exe", "ffmpeg"])
    common = _candidate_from_common_locations(["ffmpeg.exe", "ffmpeg"])
    found = configured or common or shutil.which("ffmpeg")
    return str(Path(found).expanduser().resolve(strict=False)) if found else None


def _find_ffprobe(settings: AppSettings) -> str | None:
    if settings.ffmpeg_path.strip():
        path = Path(settings.ffmpeg_path).expanduser()
        folder = path.parent if path.is_file() else path
        for name in ["ffprobe.exe", "ffprobe"]:
            candidate = folder / name
            if candidate.exists():
                return str(candidate.expanduser().resolve(strict=False))
    common = _candidate_from_common_locations(["ffprobe.exe", "ffprobe"])
    found = common or shutil.which("ffprobe")
    return str(Path(found).expanduser().resolve(strict=False)) if found else None


def detect_ffmpeg_paths(settings: AppSettings) -> tuple[str | None, str | None]:
    return _find_ffmpeg(settings), _find_ffprobe(settings)


def _find_libreoffice(settings: AppSettings) -> str | None:
    configured = _candidate_from_setting(settings.libreoffice_path, ["soffice.exe", "soffice", "libreoffice"])
    if configured:
        return str(Path(configured).expanduser().resolve(strict=False))
    candidates = [
        _candidate_from_setting(str(resource_path("bin")), ["soffice.exe", "soffice", "libreoffice"]),
        _candidate_from_setting(str(resource_path("app", "assets", "bin")), ["soffice.exe", "soffice", "libreoffice"]),
        "/opt/homebrew/bin/soffice",
        "/usr/local/bin/soffice",
        "/opt/homebrew/bin/libreoffice",
        "/usr/local/bin/libreoffice",
        shutil.which("soffice"),
        shutil.which("libreoffice"),
        "/Applications/LibreOffice.app/Contents/MacOS/soffice",
    ]
    return next((str(Path(candidate).expanduser().resolve(strict=False)) for candidate in candidates if candidate and Path(candidate).exists()), None)


def _apply_binary_paths(settings: AppSettings) -> None:
    folders: list[str] = []
    ffmpeg = _find_ffmpeg(settings)
    ffprobe = _find_ffprobe(settings)
    libreoffice = _find_libreoffice(settings)
    if ffmpeg:
        os.environ["PPT_BOT_FFMPEG"] = ffmpeg
    if ffprobe:
        os.environ["PPT_BOT_FFPROBE"] = ffprobe
    if libreoffice:
        os.environ["PPT_BOT_LIBREOFFICE"] = libreoffice
    for value in [ffmpeg or settings.ffmpeg_path, ffprobe or "", libreoffice or settings.libreoffice_path]:
        if not value.strip():
            continue
        path = Path(value).expanduser()
        folders.append(str(path.parent if path.is_file() else path))
    if folders:
        os.environ["PATH"] = os.pathsep.join(folders + [os.environ.get("PATH", "")])


def check_system_requirements(settings: AppSettings) -> list[str]:
    errors: list[str] = []
    if not _find_ffmpeg(settings) or not _find_ffprobe(settings):
        errors.append("FFmpeg is required to create the video. Please install FFmpeg or set its location in Settings.")
    if not _find_libreoffice(settings):
        errors.append("LibreOffice is required to read PowerPoint slides. Please install LibreOffice or set its location in Settings.")
    return errors


def current_tts_device_label(settings: AppSettings) -> str:
    if settings.xtts_device.lower() == "auto":
        return "XTTS Local Ready"
    if settings.xtts_device.lower() == "mps":
        return "XTTS CPU Ready"
    return f"XTTS {settings.xtts_device.upper()} Ready"


def validate_request(request: PipelineRequest, settings: AppSettings) -> ValidationResult:
    errors: list[str] = []
    warnings: list[str] = []
    parser_debug: list[str] = []
    ppt_path = Path(request.ppt_path).expanduser().resolve(strict=False)
    script_path = Path(request.script_path).expanduser().resolve(strict=False)
    output_folder = Path(request.output_folder).expanduser().resolve(strict=False)
    parser_debug.append(f"Resolved PPTX path: {ppt_path}")
    parser_debug.append(f"Resolved DOCX path: {script_path}")
    parser_debug.append(f"Resolved output folder: {output_folder}")

    if not ppt_path.exists():
        errors.append("The selected PowerPoint file could not be found. Please choose the file again.")
    elif ppt_path.suffix.lower() != ".pptx":
        errors.append("Please choose a PowerPoint file ending in .pptx.")

    if not script_path.exists():
        errors.append("The selected script document could not be found. Please choose the file again.")
    elif script_path.suffix.lower() != ".docx":
        errors.append("Please choose a Word script file ending in .docx.")

    if not output_folder.exists():
        errors.append("The output folder could not be found. Please choose an output folder.")
    if request.tts_engine not in {"xtts", "edge"}:
        errors.append("Please choose XTTS-v2 or Edge-TTS for narration.")
    if request.tts_engine == "xtts" and not request.voice.strip():
        errors.append("Please choose a narration voice.")
    if request.tts_engine == "xtts":
        xtts_config = xtts_config_from_values(
            device=settings.xtts_device,
            preload_model=settings.xtts_preload_model,
            chunk_size=settings.xtts_chunk_size,
            quality=request.quality_mode,
            cache_audio=settings.xtts_cache_audio,
            reference_wav=settings.xtts_reference_wav,
        )
        try:
            resolve_reference_wav(request.voice, xtts_config)
        except Exception:
            errors.append("XTTS-v2 needs a reference voice WAV file. Please add one in Settings.")
        if not errors:
            ok, message = check_xtts_dependencies(xtts_config)
            if not ok:
                errors.append(message)

    errors.extend(check_system_requirements(settings))
    if errors:
        empty_report = build_validation_report(0, {}, [])
        return ValidationResult(empty_report, [], REPORTS_DIR / "validation_report.json", False, warnings, errors, parser_debug)

    try:
        ppt_slide_count = count_ppt_slides(ppt_path)
        script_parse = parse_script(script_path, debug_log=parser_debug.append)
        parsed_slide_numbers = sorted(script_parse.sections)
        report = build_validation_report(
            ppt_slide_count=ppt_slide_count,
            sections=script_parse.sections,
            duplicate_script_sections=script_parse.duplicate_slide_numbers,
            padding_seconds=request.padding_seconds,
        )
        report_path = REPORTS_DIR / "validation_report.json"
        write_report(report, report_path)
    except FileNotFoundError:
        raise FriendlyPipelineError("One of the selected files could not be found. Please choose the files again.") from None
    except Exception as exc:
        diagnostics = "\n".join(parser_debug[-12:])
        detail = f" Details: {exc}"
        if diagnostics:
            detail += f"\n\nParser diagnostics:\n{diagnostics}"
        raise FriendlyPipelineError(f"The files could not be validated. Please check that they are not open in another app.{detail}") from exc

    if report.missing_scripts:
        errors.append("Some slides do not have script text. Please fix the script before generating the video.")
    if report.extra_scripts:
        warnings.append("The script contains slide numbers that are not in the PowerPoint. These will be skipped.")
    if report.duplicate_script_sections:
        warnings.append("Some slide numbers appear more than once in the script. The last matching section will be used.")

    return ValidationResult(
        report=report,
        parsed_slide_numbers=parsed_slide_numbers,
        report_path=report_path,
        can_generate=not errors,
        warnings=warnings,
        errors=errors,
        parser_debug=parser_debug,
    )


def _clean_previous_outputs() -> None:
    for folder, pattern in [(AUDIO_DIR, "slide_*.mp3"), (SEGMENTS_DIR, "slide_*.mp4"), (SLIDES_DIR, "slide_*.png")]:
        folder.mkdir(parents=True, exist_ok=True)
        for path in folder.glob(pattern):
            path.unlink()


def _audio_cache_key(
    slide_number: int,
    text: str,
    voice: str,
    provider: str,
    speed: str,
    quality_mode: str,
    settings: AppSettings,
) -> str:
    payload = json.dumps(
        {
            "slide": slide_number,
            "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "voice": voice,
            "provider": provider,
            "speed": speed,
            "quality": quality_mode,
            "xtts_device": settings.xtts_device if provider == "xtts" else "",
            "xtts_chunk_size": settings.xtts_chunk_size if provider == "xtts" else "",
            "xtts_quality": settings.xtts_generation_quality if provider == "xtts" else "",
            "xtts_reference_wav": settings.xtts_reference_wav if provider == "xtts" else "",
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


def _cached_audio_path(
    slide_number: int,
    text: str,
    voice: str,
    provider: str,
    speed: str,
    quality_mode: str,
    settings: AppSettings,
) -> Path:
    return CACHE_AUDIO_DIR / f"slide_{slide_number:03d}_{_audio_cache_key(slide_number, text, voice, provider, speed, quality_mode, settings)}.mp3"


def _check_cancel(cancel_requested: CancelCallback | None) -> None:
    if cancel_requested and cancel_requested():
        raise FriendlyPipelineError("Video generation was cancelled.")


def run_pipeline(
    request: PipelineRequest,
    settings: AppSettings,
    progress: ProgressCallback | None = None,
    log: LogCallback | None = None,
    cancel_requested: CancelCallback | None = None,
) -> tuple[Path, ValidationResult]:
    def emit_progress(value: int, message: str) -> None:
        if progress:
            progress(value, message)

    def emit_log(message: str, level: str = "info") -> None:
        if log:
            log(message, level)

    _apply_binary_paths(settings)
    validation = validate_request(request, settings)
    for parser_message in validation.parser_debug:
        emit_log(parser_message, "info")
    emit_log(f"Parsed slide numbers from DOCX: {validation.parsed_slide_numbers}", "info")
    if validation.errors:
        raise FriendlyPipelineError("\n".join(validation.errors))

    _check_cancel(cancel_requested)
    emit_progress(5, "Preparing folders...")
    _clean_previous_outputs()

    _check_cancel(cancel_requested)
    emit_progress(10, "Exporting PowerPoint slides...")
    ppt_path = Path(request.ppt_path).expanduser().resolve(strict=False)
    script_path = Path(request.script_path).expanduser().resolve(strict=False)
    output_folder = Path(request.output_folder).expanduser().resolve(strict=False)

    slide_export = export_slides(ppt_path, SLIDES_DIR, TMP_DIR)

    _check_cancel(cancel_requested)
    emit_progress(20, "Parsing script...")
    script_parse = parse_script(script_path, debug_log=lambda message: emit_log(message, "info"))

    matched_slides = validation.report.matched_slides
    xtts_config = xtts_config_from_values(
        device=settings.xtts_device,
        preload_model=settings.xtts_preload_model,
        chunk_size=settings.xtts_chunk_size,
        quality=request.quality_mode,
        cache_audio=settings.xtts_cache_audio,
        reference_wav=settings.xtts_reference_wav,
    )
    tts = create_tts_engine(
        request.tts_engine,
        voice=request.voice,
        rate=request.speech_speed,
        xtts_config=xtts_config,
        log_callback=emit_log,
        cancel_callback=cancel_requested,
    )
    audio_durations: dict[int, float] = {}
    segments = []
    total_steps = max(len(matched_slides), 1)
    generation_started_at = time.monotonic()

    for index, slide_number in enumerate(matched_slides, start=1):
        _check_cancel(cancel_requested)
        audio_progress = 20 + int((index - 1) / total_steps * 35)
        elapsed_total = time.monotonic() - generation_started_at
        avg_per_slide = elapsed_total / max(index - 1, 1)
        remaining_seconds = avg_per_slide * max(total_steps - index + 1, 0) if index > 1 else 0
        eta_text = f" ETA {remaining_seconds / 60:.1f} min" if index > 1 else ""
        emit_progress(audio_progress, f"Generating narration for slide {slide_number} of {total_steps}...{eta_text}")
        emit_log(f"Current slide {slide_number}/{total_steps}. Elapsed {elapsed_total / 60:.1f} min.{eta_text}", "info")
        section = script_parse.sections[slide_number]
        audio_path = AUDIO_DIR / f"slide_{slide_number:03d}.mp3"
        cache_path = _cached_audio_path(
            slide_number=slide_number,
            text=section.text,
            voice=request.voice,
            provider=request.tts_engine,
            speed=request.speech_speed,
            quality_mode=request.quality_mode,
            settings=settings,
        )
        cache_enabled = settings.xtts_cache_audio if request.tts_engine == "xtts" else True
        should_reuse = cache_enabled and request.reuse_existing_narration and settings.reuse_existing_narration
        if should_reuse and cache_path.exists() and cache_path.stat().st_size > 0:
            shutil.copyfile(cache_path, audio_path)
            emit_log(f"Reused cached narration for slide {slide_number}.", "success")
        else:
            slide_started_at = time.monotonic()
            try:
                tts.synthesize(section.text, audio_path)
            except Exception as exc:
                raise exc
            elapsed = time.monotonic() - slide_started_at
            emit_log(f"Narration for slide {slide_number} generated in {elapsed / 60:.1f} minutes.", "info")
            if cache_enabled and audio_path.exists() and audio_path.stat().st_size > 0:
                CACHE_AUDIO_DIR.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(audio_path, cache_path)
                emit_log(f"Cached narration for slide {slide_number}.", "info")
        audio_durations[slide_number] = probe_audio_duration(audio_path)

        _check_cancel(cancel_requested)
        video_progress = 55 + int((index - 1) / total_steps * 35)
        emit_progress(video_progress, f"Building video segment for slide {slide_number}...")
        segment_path = SEGMENTS_DIR / f"slide_{slide_number:03d}.mp4"
        segments.append(
            build_slide_segment(
                slide_number=slide_number,
                image_path=slide_export.image_paths[slide_number - 1],
                audio_path=audio_path,
                output_path=segment_path,
                padding_seconds=request.padding_seconds,
            )
        )

    _check_cancel(cancel_requested)
    output_path = output_folder / _normalize_output_name(request.output_name)
    emit_progress(95, "Combining final video...")
    concatenate_segments(segments, output_path, SEGMENTS_DIR / "concat.txt")

    final_report = build_validation_report(
        ppt_slide_count=slide_export.slide_count,
        sections=script_parse.sections,
        duplicate_script_sections=script_parse.duplicate_slide_numbers,
        audio_durations=audio_durations,
        padding_seconds=request.padding_seconds,
    )
    final_validation = ValidationResult(
        report=final_report,
        parsed_slide_numbers=sorted(script_parse.sections),
        report_path=REPORTS_DIR / "validation_report.json",
        can_generate=True,
        warnings=validation.warnings,
        errors=[],
        parser_debug=script_parse.debug_messages,
    )
    write_report(final_report, final_validation.report_path)
    emit_progress(100, "Video complete.")
    emit_log(f"Final video saved to: {output_path}", "success")
    return output_path, final_validation
