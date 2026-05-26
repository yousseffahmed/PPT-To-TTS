from __future__ import annotations

import asyncio
from pathlib import Path

from app.core.tts.base_tts_engine import TTSEngine, TTSError


class EdgeTTSEngine(TTSEngine):
    def __init__(self, voice: str = "en-US-AriaNeural", rate: str = "+0%") -> None:
        self.voice = voice
        self.rate = rate

    def synthesize(self, text: str, output_path: Path) -> Path:
        try:
            import edge_tts
        except ImportError as exc:
            raise TTSError("Edge TTS is not installed. Run the app setup again, then retry.") from exc

        async def _run() -> None:
            communicate = edge_tts.Communicate(text=text, voice=self.voice, rate=self.rate)
            await communicate.save(str(output_path))

        output_path.parent.mkdir(parents=True, exist_ok=True)
        asyncio.run(_run())
        if not output_path.exists() or output_path.stat().st_size == 0:
            raise TTSError("Narration audio could not be created. Please try again.")
        return output_path
