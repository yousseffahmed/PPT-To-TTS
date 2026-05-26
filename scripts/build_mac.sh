#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

PYTHON_BIN="${PYTHON_BIN:-.venv311/bin/python}"
if [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN="${PYTHON_BIN:-python3}"
fi

echo "Cleaning old macOS builds..."
rm -rf build dist "PPT Script to Video Bot.spec"
mkdir -p build/pyinstaller_config
export PYINSTALLER_CONFIG_DIR="$PWD/build/pyinstaller_config"
mkdir -p build/matplotlib_config
export MPLCONFIGDIR="$PWD/build/matplotlib_config"

mkdir -p app/assets/bin
for candidate in /opt/homebrew/bin/ffmpeg /usr/local/bin/ffmpeg; do
  if [ -x "$candidate" ]; then
    echo "Bundling FFmpeg from $candidate"
    cp "$candidate" app/assets/bin/ffmpeg
    break
  fi
done
for candidate in /opt/homebrew/bin/ffprobe /usr/local/bin/ffprobe; do
  if [ -x "$candidate" ]; then
    echo "Bundling FFprobe from $candidate"
    cp "$candidate" app/assets/bin/ffprobe
    break
  fi
done

echo "Building PPT Script to Video Bot.app..."
"$PYTHON_BIN" -m PyInstaller --clean --noconfirm ppt_script_to_video_bot.spec

if [ -f "dist/PPT Script to Video Bot.app/Contents/Frameworks/TTS/VERSION" ] || \
   [ -f "dist/PPT Script to Video Bot.app/Contents/Resources/TTS/VERSION" ]; then
  echo "Verified Coqui TTS VERSION file is bundled."
else
  echo "Warning: Coqui TTS VERSION file was not found in the expected bundle locations."
fi

echo
echo "Build complete:"
echo "  dist/PPT Script to Video Bot.app"
echo
echo "Optional code signing example:"
echo "  codesign --deep --force --options runtime --sign \"Developer ID Application: Your Name\" \"dist/PPT Script to Video Bot.app\""
