from __future__ import annotations

import os
import sys
from pathlib import Path

for key in [
    "OPENBLAS_NUM_THREADS",
    "OMP_NUM_THREADS",
    "MKL_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS",
    "NUMEXPR_NUM_THREADS",
]:
    os.environ.setdefault(key, "1")

try:
    from PySide6.QtCore import Qt, QTimer
    from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
    from PySide6.QtWidgets import QApplication, QMessageBox, QSplashScreen
except ModuleNotFoundError as exc:
    if getattr(sys, "frozen", False):
        raise
    if exc.name != "PySide6":
        raise

    project_root = Path(__file__).resolve().parents[1]
    preferred_venvs = [project_root / ".venv311", project_root / ".venv"]
    active_prefix = Path(sys.prefix).resolve()
    already_using_venv = any(active_prefix == venv.resolve() for venv in preferred_venvs)
    venv_python = next((venv / "bin" / "python" for venv in preferred_venvs if (venv / "bin" / "python").exists()), None)

    if venv_python and not already_using_venv:
        print("PySide6 was not found in this Python environment.")
        print(f"Relaunching with the project environment: {venv_python}")
        os.execv(str(venv_python), [str(venv_python), "-m", "app.desktop_app", *sys.argv[1:]])

    print("PySide6 is not installed in the current Python environment.")
    print("Run this from the project folder:")
    print("  .venv311/bin/python -m app.desktop_app")
    print("Or install dependencies:")
    print("  python3.11 -m venv .venv311 && . .venv311/bin/activate && pip install -r requirements.txt")
    raise SystemExit(1) from exc

from app.core.paths import APP_DISPLAY_NAME, ensure_user_dirs, icon_ico
from app.core.pipeline_runner import check_system_requirements, load_settings
from app.core.tts.xtts_engine import DEFAULT_REFERENCE_WAV
from app.ui.main_window import MainWindow


def _make_splash() -> QSplashScreen:
    pixmap = QPixmap(420, 180)
    pixmap.fill(QColor("#140B35"))
    painter = QPainter(pixmap)
    painter.setPen(QColor("#FFFFFF"))
    painter.drawText(0, 44, 420, 46, Qt.AlignmentFlag.AlignCenter, APP_DISPLAY_NAME)
    painter.setPen(QColor("#DDD6FE"))
    painter.drawText(0, 92, 420, 38, Qt.AlignmentFlag.AlignCenter, "Starting desktop app...")
    painter.end()
    splash = QSplashScreen(pixmap)
    splash.showMessage(
        "PPT Script to Video Bot\n\nStarting desktop app...",
        Qt.AlignmentFlag.AlignCenter,
        Qt.GlobalColor.white,
    )
    return splash


def _show_first_launch_setup(window: MainWindow) -> None:
    settings = load_settings()
    issues = check_system_requirements(settings)
    if not DEFAULT_REFERENCE_WAV.exists():
        issues.append("XTTS-v2 needs a bundled reference voice WAV file.")
    if not issues:
        return
    QMessageBox.information(
        window,
        "Setup Check",
        "The app is ready to open, but a few tools may be needed before video generation:\n\n"
        + "\n".join(f"- {issue}" for issue in issues)
        + "\n\nYou can update tool locations in Settings.",
    )


def main() -> int:
    ensure_user_dirs()
    app = QApplication(sys.argv)
    app.setApplicationName(APP_DISPLAY_NAME)
    app.setApplicationDisplayName(APP_DISPLAY_NAME)
    app.setOrganizationName("Presenter")
    if icon_ico().exists():
        app.setWindowIcon(QIcon(str(icon_ico())))
    splash = _make_splash()
    splash.show()
    app.processEvents()
    splash.showMessage(
        "PPT Script to Video Bot\n\nChecking local resources...",
        Qt.AlignmentFlag.AlignCenter,
        Qt.GlobalColor.white,
    )
    window = MainWindow()
    if icon_ico().exists():
        window.setWindowIcon(QIcon(str(icon_ico())))
    window.show()
    splash.finish(window)
    QTimer.singleShot(250, lambda: _show_first_launch_setup(window))
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
