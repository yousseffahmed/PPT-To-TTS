from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Callable


TTSLogCallback = Callable[[str, str], None]


class TTSError(RuntimeError):
    """Raised when text-to-speech generation fails with a user-facing message."""


class TTSEngine(ABC):
    @abstractmethod
    def synthesize(self, text: str, output_path: Path) -> Path:
        """Generate narration audio and return the output path."""

