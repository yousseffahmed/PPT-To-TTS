from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import traceback
from importlib import metadata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.paths import default_reference_wav, matplotlib_dir, xtts_model_dir
from app.core.tts.base_tts_engine import TTSEngine, TTSError, TTSLogCallback


for key in [
    "OPENBLAS_NUM_THREADS",
    "OMP_NUM_THREADS",
    "MKL_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS",
    "NUMEXPR_NUM_THREADS",
]:
    os.environ.setdefault(key, "1")

MODEL_NAME = "tts_models/multilingual/multi-dataset/xtts_v2"
DEFAULT_LANGUAGE = "en"
DEFAULT_CHUNK_SIZE = 900
DEFAULT_REFERENCE_WAV = default_reference_wav()
XTTS_VOICE_OPTIONS = ["Default Reference Voice", "Custom Reference Voice"]


@dataclass(frozen=True)
class XTTSConfig:
    device: str = "Auto"
    preload_model: bool = False
    chunk_size: int = DEFAULT_CHUNK_SIZE
    quality: str = "Balanced"
    cache_audio: bool = True
    reference_wav: str = ""


def _prepare_xtts_environment() -> None:
    mpl_config = matplotlib_dir()
    mpl_config.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("MPLCONFIGDIR", str(mpl_config))
    model_cache = xtts_model_dir()
    model_cache.mkdir(parents=True, exist_ok=True)
    os.environ["TTS_HOME"] = str(model_cache)
    os.environ.setdefault("COQUI_TOS_AGREED", "1")


def _configure_torch_threads() -> None:
    try:
        import torch
    except Exception:
        return
    for setter in [torch.set_num_threads, torch.set_num_interop_threads]:
        try:
            setter(1)
        except Exception:
            pass


def _apply_torch_load_compatibility() -> None:
    try:
        import torch
    except Exception:
        return
    if getattr(torch.load, "_xtts_weights_patch", False):
        return
    original_load = torch.load

    def patched_load(*args, **kwargs):
        kwargs.setdefault("weights_only", False)
        return original_load(*args, **kwargs)

    patched_load._xtts_weights_patch = True
    torch.load = patched_load


def _detect_device(preferred: str = "Auto") -> str:
    preferred = (preferred or "Auto").strip().lower()
    if preferred == "cuda":
        return "cuda"
    if preferred in {"cpu", "mps"}:
        return "cpu"
    try:
        import torch
    except Exception:
        return "cpu"
    return "cuda" if torch.cuda.is_available() else "cpu"


def _package_version(module_name: str) -> str:
    try:
        module = __import__(module_name)
        return str(getattr(module, "__version__", "unknown"))
    except FileNotFoundError as exc:
        if module_name == "TTS":
            try:
                return f"{metadata.version('TTS')} (package VERSION file missing: {exc})"
            except Exception:
                return f"unknown (package VERSION file missing: {exc})"
        return f"not importable: {type(exc).__name__}: {exc}"
    except Exception as exc:
        return f"not importable: {type(exc).__name__}: {exc}"


def _xtts_environment_report(device: str) -> str:
    return "\n".join(
        [
            f"Python version: {sys.version}",
            f"torch version: {_package_version('torch')}",
            f"TTS package version: {_package_version('TTS')}",
            f"Selected device: {device}",
            f"Model name: {MODEL_NAME}",
            f"TTS_HOME: {os.environ.get('TTS_HOME', '')}",
        ]
    )


def _log_exception(log: TTSLogCallback | None, context: str, exc: Exception, device: str) -> None:
    details = "\n".join(
        [
            context,
            f"Exception type: {type(exc).__name__}",
            f"Exception message: {exc}",
            _xtts_environment_report(device),
            "Traceback:",
            traceback.format_exc(),
        ]
    )
    if log:
        log(details, "error")


def _friendly_xtts_error(exc: Exception) -> str:
    message = str(exc).lower()
    if "tts/version" in message or "version" in message and "tts" in message:
        return "The packaged app is missing Coqui TTS package data. Rebuild the app with the updated PyInstaller spec."
    if "speaker_wav" in message or "speaker" in message:
        return "XTTS-v2 requires a reference voice WAV file."
    if "weights_only" in message:
        return "XTTS-v2 failed to load because of a PyTorch model loading compatibility issue."
    if "beamsearchscorer" in message or "transformers" in message:
        return "XTTS-v2 failed to load because of a Transformers/TTS compatibility issue."
    if "torchcodec" in message:
        return "XTTS-v2 could not read the reference WAV because torchcodec is missing."
    if "torch" in message or "load" in message:
        return "XTTS-v2 failed to load because of a PyTorch/TTS compatibility issue."
    if "permission" in message or "application support" in message:
        return "XTTS-v2 could not access its model cache folder."
    return f"XTTS-v2 failed: {type(exc).__name__}: {exc}"


def check_xtts_dependencies(config: XTTSConfig | None = None) -> tuple[bool, str]:
    config = config or XTTSConfig()
    device = _detect_device(config.device)
    try:
        _prepare_xtts_environment()
        from TTS.api import TTS

        import torch
    except FileNotFoundError as exc:
        if "TTS" in str(exc) and "VERSION" in str(exc):
            return False, "\n".join(
                [
                    "The packaged app is missing Coqui TTS package data (TTS/VERSION). Rebuild the app with the updated PyInstaller spec.",
                    f"Exception type: {type(exc).__name__}",
                    f"Exception message: {exc}",
                    _xtts_environment_report(device),
                    "Traceback:",
                    traceback.format_exc(),
                ]
            )
        return False, _friendly_xtts_error(exc)
    try:

        _configure_torch_threads()
        _apply_torch_load_compatibility()
        if device == "cuda" and not torch.cuda.is_available():
            return False, "CUDA was selected, but CUDA is not available. Choose Auto or CPU."
        TTS(MODEL_NAME)
        return True, f"XTTS-v2 can be loaded on {device.upper()}."
    except Exception as exc:
        return False, "\n".join(
            [
                _friendly_xtts_error(exc),
                f"Exception type: {type(exc).__name__}",
                f"Exception message: {exc}",
                _xtts_environment_report(device),
                "Traceback:",
                traceback.format_exc(),
            ]
        )


def resolve_reference_wav(voice: str, config: XTTSConfig) -> Path:
    voice_value = (voice or "").strip()
    if voice_value and Path(voice_value).expanduser().exists():
        path = Path(voice_value).expanduser()
    elif voice_value == "Custom Reference Voice":
        path = Path(config.reference_wav).expanduser() if config.reference_wav.strip() else DEFAULT_REFERENCE_WAV
    else:
        path = DEFAULT_REFERENCE_WAV
    if not path.exists() or path.suffix.lower() != ".wav" or path.stat().st_size < 1024:
        raise TTSError("XTTS-v2 needs a reference voice WAV file. Please add one in Settings.")
    return path


def _parse_speed(value: str | float) -> float:
    if isinstance(value, (int, float)):
        return max(0.5, min(2.0, float(value)))
    match = re.search(r"[-+]?\d+", value or "")
    if not match:
        return 1.0
    percent = int(match.group(0))
    return max(0.5, min(2.0, 1.0 + percent / 100.0))


def _clean_text_for_tts(text: str) -> str:
    clean = text.replace("\u00a0", " ")
    clean = clean.replace("\u2014", ", ").replace("\u2013", ", ")
    clean = clean.replace("\u201c", '"').replace("\u201d", '"')
    clean = clean.replace("\u2018", "'").replace("\u2019", "'")
    clean = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", clean)
    return re.sub(r"\s+", " ", clean).strip()


def _split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"'])", text)
    return [part.strip() for part in parts if part.strip()]


def chunk_text(text: str, max_chars: int = DEFAULT_CHUNK_SIZE) -> list[str]:
    clean = _clean_text_for_tts(text)
    if not clean:
        return []
    max_chars = max(500, min(1200, int(max_chars or DEFAULT_CHUNK_SIZE)))
    chunks: list[str] = []
    current = ""
    for sentence in _split_sentences(clean):
        if len(sentence) > max_chars:
            if current:
                chunks.append(current.strip())
                current = ""
            words = sentence.split()
            part = ""
            for word in words:
                candidate = f"{part} {word}".strip()
                if len(candidate) > max_chars and part:
                    chunks.append(part.strip())
                    part = word
                else:
                    part = candidate
            if part:
                chunks.append(part.strip())
            continue
        candidate = f"{current} {sentence}".strip()
        if len(candidate) > max_chars and current:
            chunks.append(current.strip())
            current = sentence
        else:
            current = candidate
    if current:
        chunks.append(current.strip())
    return chunks


class XTTSModelCache:
    _model: Any | None = None
    _device: str | None = None

    @classmethod
    def get_model(cls, config: XTTSConfig, log: TTSLogCallback | None = None) -> tuple[Any, str]:
        device = _detect_device(config.device)
        if cls._model is not None and cls._device == device:
            return cls._model, device
        if log:
            log("Loading XTTS-v2...", "info")
            log(f"Using {device.upper()} for XTTS-v2.", "info")
        try:
            _prepare_xtts_environment()
            from TTS.api import TTS
        except Exception as exc:
            _log_exception(log, "XTTS-v2 dependency import failed.", exc, device)
            raise TTSError("XTTS-v2 is not installed. Run setup again with: pip install TTS") from exc
        _configure_torch_threads()
        _apply_torch_load_compatibility()
        try:
            model = TTS(MODEL_NAME)
            if hasattr(model, "to"):
                model = model.to(device)
        except Exception as exc:
            _log_exception(log, "XTTS-v2 model load failed.", exc, device)
            raise TTSError(_friendly_xtts_error(exc)) from exc
        cls._model = model
        cls._device = device
        if log:
            log("XTTS ready.", "success")
        return model, device

    @classmethod
    def clear(cls) -> None:
        cls._model = None
        cls._device = None


def _run_ffmpeg(command: list[str], error_message: str) -> None:
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise TTSError(error_message)


def _stitch_and_normalize(chunk_paths: list[Path], output_path: Path) -> None:
    if not shutil.which("ffmpeg"):
        raise TTSError("FFmpeg is required to stitch narration audio.")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        concat_file = tmp_dir / "concat.txt"
        concat_file.write_text(
            "\n".join(f"file '{path.as_posix()}'" for path in chunk_paths),
            encoding="utf-8",
        )
        stitched_wav = tmp_dir / "stitched.wav"
        _run_ffmpeg(
            ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file), "-ar", "44100", "-ac", "2", str(stitched_wav)],
            "XTTS narration chunks could not be stitched.",
        )
        codec_args = ["-codec:a", "libmp3lame", "-b:a", "192k"] if output_path.suffix.lower() == ".mp3" else ["-ar", "44100", "-ac", "2"]
        _run_ffmpeg(
            ["ffmpeg", "-y", "-i", str(stitched_wav), "-af", "loudnorm=I=-16:TP=-1.5:LRA=11", *codec_args, str(output_path)],
            "XTTS narration could not be normalized.",
        )


def generate_speech(
    text: str,
    output_path: str | Path,
    voice: str,
    speed: float | str = 1.0,
    config: XTTSConfig | None = None,
    log_callback: TTSLogCallback | None = None,
    cancel_callback=None,
) -> Path:
    config = config or XTTSConfig()
    output = Path(output_path)
    chunks = chunk_text(text, config.chunk_size)
    if not chunks:
        raise TTSError("No narration text was provided for XTTS-v2.")
    model, device = XTTSModelCache.get_model(config, log_callback)
    speaker_wav = resolve_reference_wav(voice, config)
    speed_value = _parse_speed(speed)
    if log_callback:
        log_callback(f"Generating XTTS-v2 narration with {len(chunks)} chunk(s).", "info")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        chunk_paths: list[Path] = []
        for index, chunk in enumerate(chunks, start=1):
            if cancel_callback and cancel_callback():
                raise TTSError("Video generation was cancelled.")
            chunk_path = tmp_dir / f"chunk_{index:03d}.wav"
            if log_callback:
                log_callback(f"Generating chunk {index}/{len(chunks)}.", "info")
            kwargs: dict[str, Any] = {
                "text": chunk,
                "file_path": str(chunk_path),
                "language": DEFAULT_LANGUAGE,
                "speaker_wav": str(speaker_wav),
            }
            if speed_value != 1.0:
                kwargs["speed"] = speed_value
            try:
                model.tts_to_file(**kwargs)
            except TypeError:
                kwargs.pop("speed", None)
                model.tts_to_file(**kwargs)
            except Exception as exc:
                _log_exception(log_callback, "XTTS-v2 generation failed.", exc, device)
                raise TTSError(_friendly_xtts_error(exc)) from exc
            if not chunk_path.exists() or chunk_path.stat().st_size == 0:
                raise TTSError("XTTS-v2 returned empty narration audio.")
            chunk_paths.append(chunk_path)
        if log_callback:
            log_callback("Stitching narration.", "info")
        _stitch_and_normalize(chunk_paths, output)
    if not output.exists() or output.stat().st_size == 0:
        raise TTSError("XTTS-v2 narration audio could not be created.")
    return output


class XTTSv2Engine(TTSEngine):
    def __init__(
        self,
        voice: str = "Default Reference Voice",
        speed: str = "+0%",
        config: XTTSConfig | None = None,
        log_callback: TTSLogCallback | None = None,
        cancel_callback=None,
    ) -> None:
        self.voice = voice
        self.speed = speed
        self.config = config or XTTSConfig()
        self.log_callback = log_callback
        self.cancel_callback = cancel_callback

    def synthesize(self, text: str, output_path: Path) -> Path:
        return generate_speech(
            text=text,
            output_path=output_path,
            voice=self.voice,
            speed=self.speed,
            config=self.config,
            log_callback=self.log_callback,
            cancel_callback=self.cancel_callback,
        )
