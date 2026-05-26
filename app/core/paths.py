from __future__ import annotations

import os
import platform
import sys
from pathlib import Path


APP_NAME = "PPTScriptToVideoBot"
APP_DISPLAY_NAME = "PPT Script to Video Bot"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def bundle_root() -> Path:
    if is_frozen():
        executable = Path(sys.executable).resolve()
        if sys.platform == "darwin":
            resources = executable.parents[1] / "Resources"
            if resources.exists():
                return resources
        return Path(getattr(sys, "_MEIPASS", executable.parent))
    return Path(__file__).resolve().parents[2]


def resource_path(*parts: str) -> Path:
    return bundle_root().joinpath(*parts)


def user_data_dir() -> Path:
    override = os.environ.get("PPT_SCRIPT_TO_VIDEO_BOT_DATA_DIR")
    if override:
        return Path(override).expanduser()
    system = platform.system()
    if system == "Darwin":
        base = Path.home() / "Library" / "Application Support"
    elif system == "Windows":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / APP_NAME


def ensure_user_dirs() -> None:
    for folder in [
        user_data_dir(),
        config_dir(),
        cache_dir(),
        audio_cache_dir(),
        logs_dir(),
        models_dir(),
        output_dir(),
        reports_dir(),
        tmp_dir(),
        previews_dir(),
        slides_dir(),
        audio_dir(),
        video_segments_dir(),
        matplotlib_dir(),
    ]:
        folder.mkdir(parents=True, exist_ok=True)


def config_dir() -> Path:
    return user_data_dir() / "config"


def settings_path() -> Path:
    return config_dir() / "settings.json"


def cache_dir() -> Path:
    return user_data_dir() / "cache"


def audio_cache_dir() -> Path:
    return cache_dir() / "audio"


def logs_dir() -> Path:
    return user_data_dir() / "logs"


def models_dir() -> Path:
    return user_data_dir() / "models"


def xtts_model_dir() -> Path:
    return models_dir() / "xtts_v2"


def output_dir() -> Path:
    return user_data_dir() / "output"


def reports_dir() -> Path:
    return user_data_dir() / "reports"


def tmp_dir() -> Path:
    return user_data_dir() / "tmp"


def previews_dir() -> Path:
    return tmp_dir() / "previews"


def slides_dir() -> Path:
    return tmp_dir() / "slides"


def audio_dir() -> Path:
    return tmp_dir() / "audio"


def video_segments_dir() -> Path:
    return tmp_dir() / "video_segments"


def matplotlib_dir() -> Path:
    return tmp_dir() / "matplotlib"


def default_reference_wav() -> Path:
    return resource_path("app", "assets", "voices", "default_narrator.wav")


def icon_ico() -> Path:
    return resource_path("app", "assets", "icon.ico")


def icon_icns() -> Path:
    return resource_path("app", "assets", "icon.icns")
