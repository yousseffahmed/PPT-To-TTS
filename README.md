# PPT Script to Video Bot

Local MVP that turns a PowerPoint deck plus a slide-based Word script into a narrated MP4.

## What it does

1. Converts each `.pptx` slide to `tmp/slides/slide_001.png`, etc.
2. Parses the `.docx` script into slide-numbered voiceover sections.
3. Validates slide/script mismatches and writes `reports/validation_report.json`.
4. Generates one narration file per matched slide.
5. Builds one MP4 segment per matched slide.
6. Concatenates all segments into the requested final MP4.

The script body is passed to TTS without rewriting. Formatting markers such as `Slide 1`, `--- VOICEOVER: Slide 1 ---`, and `--- END VOICEOVER ---` are used only for parsing.

## Supported TTS Providers

- `XTTS-v2 Human Voice (Local)`: free local high-quality narration voice.
- `Edge-TTS Fast Free`: fast lightweight cloud narration.

XTTS-v2 is the default desktop provider. Edge-TTS remains available when you want quick generation or a small dependency footprint.

## Setup

```bash
python3.11 -m venv .venv311
. .venv311/bin/activate
pip install -r requirements.txt
```

XTTS-v2 uses the Coqui `TTS` package and downloads the model `tts_models/multilingual/multi-dataset/xtts_v2` the first time it is used. After the model is cached locally, high-quality generation can run offline.

Coqui `TTS` currently requires Python 3.9-3.11. Use Python 3.11 for this project.

This project pins `TTS==0.22.0`, `transformers==4.38.2`, and `torchcodec` because newer Transformers/PyTorch audio-loading behavior can break XTTS-v2 model loading.

## System Dependencies

### LibreOffice

Required to convert PowerPoint to PDF before rendering PNG slide images.

macOS:

```bash
brew install --cask libreoffice
```

Ubuntu/Debian:

```bash
sudo apt-get update
sudo apt-get install libreoffice
```

### FFmpeg and FFprobe

Required for audio duration probing, narration stitching/normalization, video segment generation, and final MP4 concatenation.

macOS:

```bash
brew install ffmpeg
```

Ubuntu/Debian:

```bash
sudo apt-get update
sudo apt-get install ffmpeg
```

## Run With Sample Files

Place the attached files in `input/`:

```text
input/ProfVision_Module2_Batch1_Slides1-15(1).pptx
input/ProfVision_Module2_Voiceover_Scripts_Renumbered2(1).docx
```

Run:

```bash
python main.py \
  --ppt "input/ProfVision_Module2_Batch1_Slides1-15(1).pptx" \
  --script "input/ProfVision_Module2_Voiceover_Scripts_Renumbered2(1).docx" \
  --out "output/profvision_module2.mp4"
```

The CLI uses XTTS-v2 by default. To use Edge-TTS instead:

```bash
python main.py --ppt input/deck.pptx --script input/script.docx --out output/video.mp4 --tts edge
```

## Script Formats Supported

Heading format:

```text
Slide 1
Exact narration text...

Slide 2:
Exact narration text...
```

Voiceover block format:

```text
--- VOICEOVER: Slide 1 ---
Exact narration text...
--- END VOICEOVER ---
```

## Validation Report

The report includes:

- `ppt_slide_count`
- `script_section_count`
- `matched_slides`
- `missing_scripts`
- `extra_scripts`
- `duplicate_script_sections`
- `estimated_duration_seconds`

If the PPT and DOCX numbering do not match, the video is built from matched slide numbers and the mismatch is reported.

## Desktop App

This project includes a local desktop app. It does not require hosting, deployment, or a browser.

For normal use, build the packaged app and launch it by double-clicking:

- macOS: `dist/PPT Script to Video Bot.app`
- Windows: `dist\PPT Script to Video Bot.exe`

Run it from the project folder:

```bash
. .venv311/bin/activate
python -m app.desktop_app
```

If your terminal shows `(base)`, use the project interpreter directly:

```bash
.venv311/bin/python -m app.desktop_app
```

The desktop app lets a non-technical user:

- choose a PowerPoint `.pptx`
- choose a Word `.docx` script
- choose an output folder and video name
- validate slide/script matching before generation
- select XTTS-v2 or Edge-TTS
- preview the selected narration voice
- generate the MP4 in the background without freezing the app
- open the final video or output folder when done

Settings are saved in:

```text
macOS: ~/Library/Application Support/PPTScriptToVideoBot/config/settings.json
Windows: %APPDATA%\PPTScriptToVideoBot\config\settings.json
```

Runtime cache, logs, previews, XTTS model cache, reports, and default output are also stored under the same user data folder. The app bundle itself is treated as read-only.

The Settings window supports:

- FFmpeg location
- LibreOffice location
- default output folder
- default narration voice
- XTTS reference voice WAV
- default speech speed
- XTTS device: Auto, CUDA, or CPU
- XTTS generation quality
- XTTS chunk size
- preload XTTS-v2 on startup
- cache and reuse narration
- Light / Dark theme

## XTTS-v2 Narration

XTTS-v2 is loaded lazily and reused for the whole session, so the model is not reloaded for every slide. Long slide scripts are split by sentence into larger chunks, generated as WAV, stitched, normalized, and saved for the video pipeline.

XTTS-v2 requires a reference voice WAV file. The app includes:

```text
app/assets/voices/default_narrator.wav
```

You can choose a custom `.wav` reference in Settings.

Narration audio is cached in:

```text
macOS: ~/Library/Application Support/PPTScriptToVideoBot/cache/audio/
Windows: %APPDATA%\PPTScriptToVideoBot\cache\audio\
```

If the slide text, voice, provider, speed, and quality settings have not changed, the app reuses cached narration instead of regenerating it.

## Common Errors and Fixes

`LibreOffice was not found`

Install LibreOffice and ensure `soffice` is on PATH. On macOS the app path is also checked automatically.

`Required binary not found on PATH: ffmpeg` or `ffprobe`

Install FFmpeg. The ffprobe tool is included with FFmpeg distributions.

`XTTS-v2 is not installed`

Activate the project environment and run:

```bash
pip install -r requirements.txt
```

`XTTS-v2 requires a reference voice WAV file`

Open Settings and choose a valid `.wav` file under `XTTS Reference Voice WAV`, or restore:

```text
app/assets/voices/default_narrator.wav
```

`XTTS-v2 failed to load because of a PyTorch/TTS compatibility issue`

Reinstall the pinned dependencies:

```bash
pip install -r requirements.txt
```

To test XTTS outside the app:

```bash
.venv311/bin/python scripts/test_xtts.py
```

`edge-tts network or service errors`

Choose XTTS-v2 for local narration, or retry Edge-TTS when network access is available.

`No video segments were created`

The parser found no matching slide numbers. Open `reports/validation_report.json` and check `missing_scripts` and `extra_scripts`.

## Build Packaged Desktop Apps

Packaging uses PyInstaller and the spec file:

```text
ppt_script_to_video_bot.spec
```

The package includes app assets, config defaults, icons, Qt/PySide dependencies, multimedia modules, and XTTS-related imports. Runtime data is created in the OS user data directory on first launch.

### macOS `.app`

From the project root on macOS:

```bash
scripts/build_mac.sh
```

Output:

```text
dist/PPT Script to Video Bot.app
```

Double-click the `.app` in Finder. No terminal should open.

Optional code signing can be added after building:

```bash
codesign --deep --force --options runtime --sign "Developer ID Application: Your Name" "dist/PPT Script to Video Bot.app"
```

### Windows `.exe`

On Windows, install LibreOffice and FFmpeg first. FFmpeg should include both `ffmpeg.exe` and `ffprobe.exe`.

Then run:

```bat
scripts\build_windows.bat
```

The packaged app will be created at:

```text
dist\PPT Script to Video Bot.exe
```

The root `build_windows.bat` is a convenience wrapper around `scripts\build_windows.bat`.

If FFmpeg or LibreOffice are not on PATH, open Settings inside the app and choose their locations. macOS Finder-launched apps do not inherit your Terminal PATH, so the app also checks common Homebrew locations and bundled binaries before falling back to PATH.

The macOS build script automatically bundles `/opt/homebrew/bin/ffmpeg`, `/opt/homebrew/bin/ffprobe`, `/usr/local/bin/ffmpeg`, or `/usr/local/bin/ffprobe` when they exist.

To run a dependency smoke test in development:

```bash
.venv311/bin/python scripts/smoke_test_packaged.py --docx input/ProfVision_Module2_Voiceover_Scripts_Renumbered2.docx
```

## Packaged App Troubleshooting

`The app opens but video generation says FFmpeg is missing`

Install FFmpeg, set its path in Settings, or rebuild with `scripts/build_mac.sh` so Homebrew FFmpeg is copied into the packaged app resources.

`The app opens but LibreOffice is missing`

Install LibreOffice, or set its `soffice` path in Settings.

`XTTS downloads again after packaging`

XTTS model files are cached in the user data folder, not inside the app bundle. This is expected on first launch for each user account.

`XTTS fails with TTS/VERSION missing`

Rebuild with `ppt_script_to_video_bot.spec`. The spec and `hooks/hook-TTS.py` collect Coqui TTS package data, including the required `TTS/VERSION` file.

`DOCX parsing works in Terminal but finds no slides in the packaged app`

Rebuild with the current spec so `python-docx` and `lxml` are bundled. The Activity Log now shows the resolved DOCX path, file size, paragraph count, first non-empty paragraphs, and detected slide headings.

`macOS says the app is from an unidentified developer`

For local testing, right-click the app and choose Open. For distribution, sign and notarize the `.app`.
# PPT-To-TTS
