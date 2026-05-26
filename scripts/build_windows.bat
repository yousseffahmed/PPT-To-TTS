@echo off
setlocal

cd /d "%~dp0\.."

if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
mkdir build\pyinstaller_config
set PYINSTALLER_CONFIG_DIR=%CD%\build\pyinstaller_config

set PYTHON_BIN=.venv311\Scripts\python.exe
if not exist "%PYTHON_BIN%" set PYTHON_BIN=python

echo Building PPT Script to Video Bot.exe...
"%PYTHON_BIN%" -m PyInstaller --clean --noconfirm ppt_script_to_video_bot.spec

echo.
echo Build complete:
echo   dist\PPT Script to Video Bot.exe
echo.
pause
