from __future__ import annotations

from app.core.tts.base_tts_engine import TTSEngine, TTSLogCallback
from app.core.tts.edge_tts_engine import EdgeTTSEngine
from app.core.tts.xtts_engine import XTTSConfig, XTTSv2Engine


def create_tts_engine(
    name: str,
    voice: str | None = None,
    rate: str = "+0%",
    xtts_config: XTTSConfig | None = None,
    log_callback: TTSLogCallback | None = None,
    cancel_callback=None,
) -> TTSEngine:
    if name == "xtts":
        return XTTSv2Engine(
            voice=voice or "Default Reference Voice",
            speed=rate,
            config=xtts_config,
            log_callback=log_callback,
            cancel_callback=cancel_callback,
        )
    if name == "edge":
        edge_voice = voice if voice and "Neural" in voice else "en-US-AriaNeural"
        return EdgeTTSEngine(voice=edge_voice, rate=rate)
    raise ValueError(f"Unknown TTS engine: {name}")


def xtts_config_from_values(
    device: str,
    preload_model: bool,
    chunk_size: int,
    quality: str,
    cache_audio: bool,
    reference_wav: str = "",
) -> XTTSConfig:
    return XTTSConfig(
        device=device,
        preload_model=preload_model,
        chunk_size=chunk_size,
        quality=quality,
        cache_audio=cache_audio,
        reference_wav=reference_wav,
    )
