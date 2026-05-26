from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODEL_NAME = "tts_models/multilingual/multi-dataset/xtts_v2"
OUTPUT_PATH = ROOT / "output" / "xtts_test.wav"
REFERENCE_WAV = ROOT / "app" / "assets" / "voices" / "default_narrator.wav"


def configure_environment() -> None:
    for key in [
        "OPENBLAS_NUM_THREADS",
        "OMP_NUM_THREADS",
        "MKL_NUM_THREADS",
        "VECLIB_MAXIMUM_THREADS",
        "NUMEXPR_NUM_THREADS",
    ]:
        os.environ.setdefault(key, "1")
    os.environ.setdefault("COQUI_TOS_AGREED", "1")
    model_cache = ROOT / "models" / "xtts_v2"
    model_cache.mkdir(parents=True, exist_ok=True)
    os.environ["TTS_HOME"] = str(model_cache)
    mpl_cache = ROOT / "app" / "tmp" / "matplotlib"
    mpl_cache.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("MPLCONFIGDIR", str(mpl_cache))


def print_environment(torch_module, tts_package) -> None:
    print(f"Python: {sys.version}")
    print(f"torch: {getattr(torch_module, '__version__', 'unknown')}")
    print(f"TTS: {getattr(tts_package, '__version__', 'unknown')}")
    print(f"Model: {MODEL_NAME}")
    print(f"TTS_HOME: {os.environ.get('TTS_HOME', '')}")


def apply_torch_load_compatibility(torch_module) -> None:
    original_load = torch_module.load

    def patched_load(*args, **kwargs):
        kwargs.setdefault("weights_only", False)
        return original_load(*args, **kwargs)

    torch_module.load = patched_load


def main() -> int:
    configure_environment()
    try:
        import torch
        import TTS as tts_package
        from TTS.api import TTS

        torch.set_num_threads(1)
        try:
            torch.set_num_interop_threads(1)
        except Exception:
            pass
        apply_torch_load_compatibility(torch)

        device = "cuda" if torch.cuda.is_available() else "cpu"
        print_environment(torch, tts_package)
        print(f"Device: {device}")

        tts = TTS(MODEL_NAME).to(device)
        OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

        try:
            print("Trying official XTTS call without a reference voice...")
            tts.tts_to_file(
                text="Hello, this is a test narration.",
                speaker_wav=None,
                language="en",
                file_path=str(OUTPUT_PATH),
            )
        except Exception:
            print("The no-reference call failed. Full traceback:")
            traceback.print_exc()
            if not REFERENCE_WAV.exists():
                print(f"Missing reference WAV: {REFERENCE_WAV}", file=sys.stderr)
                return 1
            print(f"Retrying with reference WAV: {REFERENCE_WAV}")
            tts.tts_to_file(
                text="Hello, this is a test narration.",
                speaker_wav=str(REFERENCE_WAV),
                language="en",
                file_path=str(OUTPUT_PATH),
            )

        if not OUTPUT_PATH.exists() or OUTPUT_PATH.stat().st_size == 0:
            print("XTTS test failed: output file was not created.", file=sys.stderr)
            return 1
        print(f"XTTS test succeeded: {OUTPUT_PATH}")
        return 0
    except Exception:
        print("XTTS test failed with full traceback:", file=sys.stderr)
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
