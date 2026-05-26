from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from app.core.pipeline_runner import AppSettings, detect_ffmpeg_paths, load_settings, save_settings
from app.core.tts.xtts_engine import XTTS_VOICE_OPTIONS


class SettingsWindow(QDialog):
    SPEEDS = ["-20%", "-10%", "+0%", "+10%", "+20%"]
    QUALITY_MODES = ["Fast", "Balanced", "High Quality"]
    DEVICES = ["Auto", "CUDA", "CPU"]
    VOICES = XTTS_VOICE_OPTIONS

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(680)
        self.settings = load_settings()

        self.ffmpeg_path = QLineEdit(self.settings.ffmpeg_path)
        self.libreoffice_path = QLineEdit(self.settings.libreoffice_path)
        self.output_folder = QLineEdit(self.settings.default_output_folder)
        self.reference_wav = QLineEdit(self.settings.xtts_reference_wav)
        self.detected_ffmpeg = QLabel()
        self.detected_ffmpeg.setWordWrap(True)

        self.voice = QComboBox()
        self.voice.addItems(self.VOICES)
        self.voice.setCurrentText(self.settings.default_voice)

        self.speed = QComboBox()
        self.speed.addItems(self.SPEEDS)
        self.speed.setCurrentText(self.settings.default_speech_speed)

        self.theme = QComboBox()
        self.theme.addItems(["Light", "Dark"])
        self.theme.setCurrentText(self.settings.theme)

        self.xtts_device = QComboBox()
        self.xtts_device.addItems(self.DEVICES)
        self.xtts_device.setCurrentText(self.settings.xtts_device)

        self.xtts_quality = QComboBox()
        self.xtts_quality.addItems(self.QUALITY_MODES)
        self.xtts_quality.setCurrentText(self.settings.xtts_generation_quality)

        self.xtts_chunk_size = QSpinBox()
        self.xtts_chunk_size.setRange(500, 1200)
        self.xtts_chunk_size.setSingleStep(50)
        self.xtts_chunk_size.setValue(int(self.settings.xtts_chunk_size))

        self.preload_xtts = QCheckBox("Preload XTTS-v2 on startup")
        self.preload_xtts.setChecked(self.settings.xtts_preload_model)

        self.cache_audio = QCheckBox("Cache XTTS narration audio")
        self.cache_audio.setChecked(self.settings.xtts_cache_audio)

        self.reuse_narration = QCheckBox("Reuse existing narration if available")
        self.reuse_narration.setChecked(self.settings.reuse_existing_narration)

        form = QFormLayout()
        form.addRow("FFmpeg location", self._path_row(self.ffmpeg_path, self._choose_ffmpeg))
        form.addRow("Detected FFmpeg", self._detected_ffmpeg_row())
        form.addRow("LibreOffice location", self._path_row(self.libreoffice_path, self._choose_libreoffice))
        form.addRow("Default output folder", self._path_row(self.output_folder, self._choose_output_folder))
        form.addRow("Default narration voice", self.voice)
        form.addRow("XTTS reference voice WAV", self._path_row(self.reference_wav, self._choose_reference_wav))
        form.addRow("Default speech speed", self.speed)
        form.addRow("XTTS device", self.xtts_device)
        form.addRow("XTTS generation quality", self.xtts_quality)
        form.addRow("XTTS chunk size", self.xtts_chunk_size)
        form.addRow("", self.preload_xtts)
        form.addRow("", self.cache_audio)
        form.addRow("", self.reuse_narration)
        form.addRow("Theme", self.theme)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)
        self._refresh_ffmpeg_detection()

    def _path_row(self, line_edit: QLineEdit, callback) -> QHBoxLayout:
        button = QPushButton("Browse")
        button.clicked.connect(callback)
        row = QHBoxLayout()
        row.addWidget(line_edit, 1)
        row.addWidget(button)
        return row

    def _detected_ffmpeg_row(self) -> QHBoxLayout:
        button = QPushButton("Re-test")
        button.clicked.connect(self._refresh_ffmpeg_detection)
        row = QHBoxLayout()
        row.addWidget(self.detected_ffmpeg, 1)
        row.addWidget(button)
        return row

    def _settings_from_fields(self) -> AppSettings:
        return AppSettings(
            ffmpeg_path=self.ffmpeg_path.text().strip(),
            libreoffice_path=self.libreoffice_path.text().strip(),
            default_output_folder=self.output_folder.text().strip(),
            default_voice=self.voice.currentText().strip(),
            default_speech_speed=self.speed.currentText().strip(),
            theme=self.theme.currentText(),
            xtts_device=self.xtts_device.currentText(),
            xtts_preload_model=self.preload_xtts.isChecked(),
            xtts_chunk_size=int(self.xtts_chunk_size.value()),
            xtts_generation_quality=self.xtts_quality.currentText(),
            xtts_cache_audio=self.cache_audio.isChecked(),
            xtts_reference_wav=self.reference_wav.text().strip(),
            reuse_existing_narration=self.reuse_narration.isChecked(),
        )

    def _refresh_ffmpeg_detection(self) -> None:
        ffmpeg, ffprobe = detect_ffmpeg_paths(self._settings_from_fields())
        if ffmpeg and ffprobe:
            self.detected_ffmpeg.setText(f"Found FFmpeg: {ffmpeg}\nFound FFprobe: {ffprobe}")
        elif ffmpeg:
            self.detected_ffmpeg.setText(f"Found FFmpeg: {ffmpeg}\nFFprobe was not found.")
        else:
            self.detected_ffmpeg.setText("FFmpeg was not found. Choose the ffmpeg binary or install FFmpeg.")

    def _choose_ffmpeg(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Choose FFmpeg", str(Path.home()))
        if path:
            self.ffmpeg_path.setText(path)
            self._refresh_ffmpeg_detection()

    def _choose_libreoffice(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Choose LibreOffice / soffice", str(Path.home()))
        if path:
            self.libreoffice_path.setText(path)

    def _choose_output_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Choose Default Output Folder", self.output_folder.text())
        if path:
            self.output_folder.setText(path)

    def _choose_reference_wav(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Choose XTTS Reference Voice WAV", str(Path.home()), "WAV files (*.wav)")
        if path:
            self.reference_wav.setText(path)

    def _save(self) -> None:
        save_settings(self._settings_from_fields())
        self.accept()
