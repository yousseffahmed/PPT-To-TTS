from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QDateTime, QObject, QThread, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtMultimedia import QSoundEffect
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QCheckBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QDoubleSpinBox,
    QScrollArea,
    QSizePolicy,
    QStyle,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.core.pipeline_runner import (
    AppSettings,
    FriendlyPipelineError,
    PipelineRequest,
    ValidationResult,
    check_system_requirements,
    current_tts_device_label,
    load_settings,
    run_pipeline,
    validate_request,
)
from app.core.paths import icon_ico, previews_dir, resource_path, user_data_dir
from app.core.tts.edge_tts_engine import EdgeTTSEngine
from app.core.tts.xtts_engine import XTTSConfig, XTTSModelCache, generate_speech as generate_xtts_speech
from app.ui.settings_window import SettingsWindow
from app.ui.validation_dialog import ValidationDialog


APP_VERSION = "1.0.0"
PREVIEW_TEXT = "Hello. This is a preview of the selected narration voice."
TTS_THREAD_STACK_SIZE = 64 * 1024 * 1024


def add_shadow(widget: QWidget) -> None:
    shadow = QGraphicsDropShadowEffect(widget)
    shadow.setBlurRadius(28)
    shadow.setOffset(0, 9)
    shadow.setColor(QColor(15, 23, 42, 24))
    widget.setGraphicsEffect(shadow)


class PipelineWorker(QObject):
    progress = Signal(int, str)
    log = Signal(str, str)
    completed = Signal(object, object)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, request: PipelineRequest, settings: AppSettings) -> None:
        super().__init__()
        self.request = request
        self.settings = settings
        self._cancelled = False

    @Slot()
    def run(self) -> None:
        try:
            output_path, validation = run_pipeline(
                self.request,
                self.settings,
                progress=lambda value, message: self.progress.emit(value, message),
                log=lambda message, level="info": self.log.emit(message, level),
                cancel_requested=lambda: self._cancelled,
            )
            if self._cancelled:
                self.cancelled.emit()
                return
            self.completed.emit(output_path, validation)
        except FriendlyPipelineError as exc:
            if "cancelled" in str(exc).lower():
                self.cancelled.emit()
            else:
                self.failed.emit(str(exc))
        except FileNotFoundError:
            self.failed.emit("The selected file could not be found. Please choose the file again.")
        except Exception as exc:
            self.failed.emit(f"Something went wrong while creating the video. Details: {exc}")

    def cancel(self) -> None:
        self._cancelled = True


class PreviewWorker(QObject):
    completed = Signal(object)
    failed = Signal(str)
    log = Signal(str, str)

    def __init__(self, voice: str, speed: str, quality_mode: str, provider: str, settings: AppSettings) -> None:
        super().__init__()
        self.voice = voice
        self.speed = speed
        self.quality_mode = quality_mode
        self.provider = provider
        self.settings = settings

    @Slot()
    def run(self) -> None:
        try:
            safe_name = f"preview_{self.provider}_{self.voice}_{self.speed}_{self.quality_mode}".replace("/", "_").replace("\\", "_")
            output = previews_dir() / f"{safe_name}.mp3"
            output.parent.mkdir(parents=True, exist_ok=True)
            if not output.exists():
                if self.provider == "edge":
                    EdgeTTSEngine(rate=self.speed).synthesize(PREVIEW_TEXT, output)
                else:
                    config = XTTSConfig(
                        device=self.settings.xtts_device,
                        preload_model=self.settings.xtts_preload_model,
                        chunk_size=self.settings.xtts_chunk_size,
                        quality=self.settings.xtts_generation_quality,
                        cache_audio=self.settings.xtts_cache_audio,
                        reference_wav=self.settings.xtts_reference_wav,
                    )
                    generate_xtts_speech(
                        text=PREVIEW_TEXT,
                        output_path=str(output),
                        voice=self.voice,
                        speed=self.speed,
                        config=config,
                        log_callback=lambda message, level="info": self.log.emit(message, level),
                    )
            self.completed.emit(output)
        except Exception as exc:
            self.failed.emit(str(exc))


class ModelPreloadWorker(QObject):
    completed = Signal()
    failed = Signal(str)
    log = Signal(str, str)

    def __init__(self, settings: AppSettings) -> None:
        super().__init__()
        self.settings = settings

    @Slot()
    def run(self) -> None:
        try:
            config = XTTSConfig(
                device=self.settings.xtts_device,
                preload_model=True,
                chunk_size=self.settings.xtts_chunk_size,
                quality=self.settings.xtts_generation_quality,
                cache_audio=self.settings.xtts_cache_audio,
                reference_wav=self.settings.xtts_reference_wav,
            )
            XTTSModelCache.get_model(config, lambda message, level="info": self.log.emit(message, level))
            self.completed.emit()
        except Exception as exc:
            self.failed.emit(str(exc))


class SidebarButton(QPushButton):
    def __init__(self, text: str, active: bool = False) -> None:
        super().__init__(text)
        self.setCheckable(True)
        self.setChecked(active)
        self.setObjectName("SidebarButton")
        self.setMinimumHeight(40)


class FilePickerCard(QFrame):
    def __init__(self, icon_text: str, title: str, helper: str, button_text: str, callback) -> None:
        super().__init__()
        self.setObjectName("FileRow")
        self.setMinimumHeight(56)
        self.path = ""
        self.helper = helper

        self.icon = QLabel(icon_text)
        self.icon.setObjectName("FileIcon")
        self.title = QLabel(title)
        self.title.setObjectName("FileTitle")
        self.name = QLabel("No file selected yet")
        self.name.setObjectName("FileName")
        self.name.setWordWrap(False)
        self.path_label = QLabel(helper)
        self.path_label.setObjectName("MutedText")
        self.path_label.setWordWrap(False)
        self.check = QLabel("Not selected")
        self.check.setObjectName("CheckOff")
        self.button = QPushButton(button_text)
        self.button.setObjectName("SmallOutlineButton")
        self.button.clicked.connect(callback)

        text = QVBoxLayout()
        text.setSpacing(1)
        text.addWidget(self.title)
        text.addWidget(self.name)
        text.addWidget(self.path_label)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 7, 14, 7)
        layout.setSpacing(12)
        layout.addWidget(self.icon)
        layout.addLayout(text, 1)
        layout.addWidget(self.check)
        layout.addWidget(self.button)

    def set_path(self, path: str) -> None:
        self.path = path
        if path:
            selected = Path(path)
            self.name.setText(self._middle_ellipsis(selected.name, 34))
            self.path_label.setText(self._middle_ellipsis(str(selected), 56))
            self.name.setToolTip(selected.name)
            self.path_label.setToolTip(str(selected))
            self.button.setToolTip(str(selected))
            self.check.setText("✓ Selected")
            self.check.setObjectName("CheckOn")
        else:
            self.name.setText("No file selected yet")
            self.path_label.setText(self.helper)
            self.name.setToolTip("")
            self.path_label.setToolTip("")
            self.button.setToolTip("")
            self.check.setText("Not selected")
            self.check.setObjectName("CheckOff")
        self.check.style().unpolish(self.check)
        self.check.style().polish(self.check)

    @staticmethod
    def _middle_ellipsis(text: str, limit: int) -> str:
        if len(text) <= limit:
            return text
        if limit <= 8:
            return f"{text[: max(0, limit - 3)]}..."
        keep = limit - 3
        front = max(4, keep // 2)
        back = max(4, keep - front)
        return f"{text[:front]}...{text[-back:]}"


class StepStatusRow(QFrame):
    def __init__(self, title: str) -> None:
        super().__init__()
        self.setObjectName("StepStatusRow")
        self.dot = QLabel("")
        self.dot.setObjectName("StepDotPending")
        self.title = QLabel(title)
        self.title.setObjectName("StepTitle")
        self.state = QLabel("Pending")
        self.state.setObjectName("StepStatePending")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(10)
        layout.addWidget(self.dot)
        layout.addWidget(self.title, 1)
        layout.addWidget(self.state)
        self.setMinimumHeight(24)
        self.state.setMinimumWidth(78)
        self.state.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

    def set_state(self, state: str) -> None:
        state = state.lower()
        suffix = {"pending": "Pending", "active": "Active", "done": "Done", "failed": "Failed"}[state]
        text = {"pending": "Pending", "active": "In progress", "done": "Done", "failed": "Failed"}[state]
        if state == "done":
            text = "✓ Done"
        self.dot.setObjectName(f"StepDot{suffix}")
        self.state.setObjectName(f"StepState{suffix}")
        self.state.setText(text)
        for widget in (self.dot, self.state):
            widget.style().unpolish(widget)
            widget.style().polish(widget)


class SummaryCard(QFrame):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("Card")
        add_shadow(self)
        self.setMinimumHeight(278)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        self.status_badge = QLabel("Not validated")
        self.status_badge.setObjectName("BadgeNeutral")
        self.status_badge.setMinimumHeight(32)
        self.values: dict[str, QLabel] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 20)
        layout.setSpacing(11)
        layout.addLayout(card_header("Validation Summary"))
        layout.addWidget(self.status_badge)

        for index, (key, title) in enumerate(
            [
                ("ppt", "PPT slides"),
                ("scripts", "Script sections"),
                ("matched", "Matched"),
                ("missing", "Missing"),
                ("extra", "Extra"),
            ]
        ):
            row = QFrame()
            row.setObjectName("MetricRow")
            row.setMinimumHeight(29)
            value = QLabel("-")
            value.setObjectName("MetricValue")
            value.setMinimumWidth(72)
            value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            label = QLabel(title)
            label.setObjectName("MetricLabel")
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(12, 5, 12, 5)
            row_layout.setSpacing(8)
            row_layout.addWidget(label, 1)
            row_layout.addWidget(value)
            self.values[key] = value
            layout.addWidget(row)
        self.message = QLabel("Validate your files to check slide matching.")
        self.message.setObjectName("MutedText")
        self.message.setWordWrap(True)
        self.message.setMinimumHeight(42)
        self.message.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        layout.addWidget(self.message)

    def reset(self) -> None:
        self.set_status("Not validated", "neutral")
        for value in self.values.values():
            value.setText("-")
        self.message.setText("Validate your files to check slide matching.")

    def set_status(self, text: str, level: str) -> None:
        object_name = {
            "ready": "BadgeReady",
            "warning": "BadgeWarning",
            "error": "BadgeError",
            "neutral": "BadgeNeutral",
        }[level]
        prefix = {"ready": "✓ ", "warning": "⚠ ", "error": "! ", "neutral": ""}[level]
        self.status_badge.setText(f"{prefix}{text}")
        self.status_badge.setObjectName(object_name)
        self.status_badge.style().unpolish(self.status_badge)
        self.status_badge.style().polish(self.status_badge)


class ProgressCard(QFrame):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("Card")
        add_shadow(self)
        self.setMinimumHeight(320)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        self.percent = QLabel("0%")
        self.percent.setObjectName("PercentBubble")
        self.current_step = QLabel("Ready to begin")
        self.current_step.setObjectName("CurrentStep")
        self.current_step.setWordWrap(False)
        self.current_step.setFixedHeight(18)
        self.elapsed = QLabel("Elapsed 00:00")
        self.elapsed.setObjectName("MutedText")
        self.elapsed.setFixedHeight(16)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)

        self.steps = {
            "export": StepStatusRow("Export slides"),
            "parse": StepStatusRow("Parse script"),
            "audio": StepStatusRow("Generate narration"),
            "segments": StepStatusRow("Build video segments"),
            "combine": StepStatusRow("Combine final video"),
        }

        top_widget = QWidget()
        top_widget.setMinimumHeight(54)
        top = QHBoxLayout(top_widget)
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(14)
        top.addWidget(self.percent)
        step_text_container = QWidget()
        step_text_container.setMinimumHeight(40)
        step_text = QVBoxLayout(step_text_container)
        step_text.setContentsMargins(0, 2, 0, 2)
        step_text.setSpacing(2)
        step_text.addWidget(self.current_step)
        step_text.addWidget(self.elapsed)
        top.addWidget(step_text_container, 1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 20)
        layout.setSpacing(8)
        layout.addLayout(card_header("Progress"))
        layout.addWidget(top_widget)
        layout.addWidget(self.progress)
        for row in self.steps.values():
            layout.addWidget(row)

    def reset(self) -> None:
        self.percent.setText("0%")
        self.progress.setValue(0)
        self.current_step.setText("Ready to begin")
        self.elapsed.setText("Elapsed 00:00")
        for row in self.steps.values():
            row.set_state("pending")

    def set_progress(self, value: int, message: str, elapsed_seconds: int) -> None:
        self.progress.setValue(value)
        self.percent.setText(f"{value}%")
        self.current_step.setText(message)
        self.elapsed.setText(f"Elapsed {elapsed_seconds // 60:02d}:{elapsed_seconds % 60:02d}")

    def set_failed(self) -> None:
        for row in self.steps.values():
            if row.state.text() == "In progress":
                row.set_state("failed")

    def set_done(self) -> None:
        self.set_progress(100, "Video complete", int(self.elapsed.text()[-5:-3]) * 60 if self.elapsed.text().startswith("Elapsed") else 0)
        for row in self.steps.values():
            row.set_state("done")


class OutputCard(QFrame):
    def __init__(self, open_video, open_folder) -> None:
        super().__init__()
        self.setObjectName("Card")
        add_shadow(self)
        self.setMinimumHeight(172)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        self.filename = QLabel("No videos generated yet.")
        self.filename.setObjectName("OutputName")
        self.created = QLabel("Created time will appear here")
        self.created.setObjectName("MutedText")
        self.path = QLabel("")
        self.path.setObjectName("MutedText")
        self.path.setWordWrap(True)
        self.open_video_button = QPushButton("Open Video")
        self.open_video_button.setObjectName("PrimaryButton")
        self.open_video_button.clicked.connect(open_video)
        self.open_folder_button = QPushButton("Open Folder")
        self.open_folder_button.setObjectName("SecondaryButton")
        self.open_folder_button.clicked.connect(open_folder)

        buttons = QHBoxLayout()
        buttons.setSpacing(10)
        buttons.addWidget(self.open_folder_button)
        buttons.addWidget(self.open_video_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(9)
        layout.addLayout(card_header("Recent Output"))
        layout.addWidget(self.filename)
        layout.addWidget(self.created)
        layout.addWidget(self.path)
        layout.addStretch(1)
        layout.addLayout(buttons)

    def set_output(self, path: Path | None) -> None:
        if path:
            self.filename.setText(path.name)
            self.created.setText(QDateTime.currentDateTime().toString("'Created' MMM d, yyyy h:mm AP"))
            self.path.setText(str(path))
            self.open_video_button.setEnabled(True)
        else:
            self.filename.setText("No videos generated yet.")
            self.created.setText("Created time will appear here")
            self.path.setText("")
            self.open_video_button.setEnabled(False)


def card_header(title: str) -> QHBoxLayout:
    number, sep, rest = title.partition(" ")
    label = QLabel(title if not number.isdigit() else rest)
    label.setObjectName("CardTitle")
    layout = QHBoxLayout()
    layout.setContentsMargins(0, 0, 0, 0)
    if sep and number.isdigit():
        badge = QLabel(number)
        badge.setObjectName("NumberBadge")
        layout.addWidget(badge)
    layout.addWidget(label)
    layout.addStretch(1)
    return layout


class MainWindow(QMainWindow):
    VOICES = SettingsWindow.VOICES
    SPEEDS = SettingsWindow.SPEEDS

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("PPT Script to Video Bot")
        self.setMinimumSize(1440, 900)
        self.resize(1440, 900)
        self.settings = load_settings()
        self.validation_result: ValidationResult | None = None
        self.final_video_path: Path | None = None
        self.worker: PipelineWorker | None = None
        self.thread: QThread | None = None
        self.preview_worker: PreviewWorker | None = None
        self.preview_thread: QThread | None = None
        self.preload_worker: ModelPreloadWorker | None = None
        self.preload_thread: QThread | None = None
        self.preview_player = QSoundEffect(self)
        self.started_at: QDateTime | None = None
        self.elapsed_timer = QTimer(self)
        self.elapsed_timer.timeout.connect(self._refresh_elapsed)

        self.ppt_path = QLineEdit()
        self.script_path = QLineEdit()
        self.output_folder = QLineEdit(self.settings.default_output_folder)
        self.output_name = QLineEdit("output.mp4")
        self.output_name.setPlaceholderText("module_2_video.mp4")
        self.output_name.setToolTip("The final MP4 file name. .mp4 is added automatically if needed.")

        self.voice = QComboBox()
        self.voice.addItems(self.VOICES)
        self.voice.setCurrentText(self.settings.default_voice)
        self.voice.setToolTip("Choose the narration voice.")

        self.tts_provider = QComboBox()
        self.tts_provider.addItems(["XTTS-v2 Human Voice (Local)", "Edge-TTS Fast Free"])
        self.tts_provider.setCurrentText("XTTS-v2 Human Voice (Local)")
        self.tts_provider.setToolTip("XTTS-v2 is local and high quality. Edge-TTS is fast and lightweight.")

        self.speed = QComboBox()
        self.speed.addItems(self.SPEEDS)
        self.speed.setCurrentText(self.settings.default_speech_speed)
        self.speed.setToolTip("Adjust narration speed.")
        self.quality = QComboBox()
        self.quality.addItems(SettingsWindow.QUALITY_MODES)
        self.quality.setCurrentText(self.settings.xtts_generation_quality)
        self.quality.setToolTip("Choose the XTTS-v2 generation quality.")
        self.reuse_narration = QCheckBox("Reuse cached narration")
        self.reuse_narration.setChecked(self.settings.reuse_existing_narration)
        self.reuse_narration.setToolTip("Reuses cached slide audio when the script text and TTS settings match.")
        self.provider_warning = QLabel("")
        self.provider_warning.setObjectName("WarningText")
        self.provider_warning.setWordWrap(True)
        self.provider_warning.setVisible(False)
        self.provider_description = QLabel()
        self.provider_description.setObjectName("MutedText")
        self.provider_description.setWordWrap(True)

        self.padding = QDoubleSpinBox()
        self.padding.setRange(0.0, 5.0)
        self.padding.setSingleStep(0.25)
        self.padding.setValue(0.5)
        self.padding.setSuffix(" sec")
        self.padding.setToolTip("Adds a pause after each slide narration.")
        self.padding.setStatusTip("Adds a pause after each slide narration.")

        self.validate_button = QPushButton("Validate Files")
        self.validate_button.setObjectName("OutlinePurpleButton")
        self.generate_button = QPushButton("Generate Video")
        self.generate_button.setObjectName("PrimaryButton")
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setObjectName("NeutralButton")
        self.settings_button = QPushButton("Settings")
        self.settings_button.setObjectName("TopButton")
        self.help_button = QPushButton("Help")
        self.help_button.setObjectName("TopButton")
        self.device_indicator = QLabel(current_tts_device_label(self.settings))
        self.device_indicator.setObjectName("DeviceIndicator")

        self.summary_card = SummaryCard()
        self.progress_card = ProgressCard()
        self.output_card = OutputCard(self.open_final_video, self.open_output_folder)

        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        self.log_area.setMinimumHeight(118)
        self.log_area.setObjectName("ActivityLog")
        self.log_toggle = QToolButton()
        self.log_toggle.setText("Show Activity Log")
        self.log_toggle.setCheckable(True)
        self.log_toggle.setChecked(False)
        self.log_toggle.setObjectName("LogToggle")
        self.log_area.setVisible(False)
        self.log_card: QFrame | None = None
        self.left_scroll: QScrollArea | None = None

        self.bottom_status = QLabel()
        self.bottom_status.setObjectName("BottomStatus")

        self._build_ui()
        self._connect_signals()
        self._apply_theme()
        self._set_button_icons()
        self._set_running(False)
        self._on_provider_changed(self.tts_provider.currentText())
        self._refresh_file_cards()
        self._refresh_dependency_status("Ready")
        self.output_card.set_output(None)
        self.progress_card.reset()
        self._maybe_preload_xtts()

    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("Root")
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        root_layout.addWidget(self._build_sidebar())
        root_layout.addWidget(self._build_main_area(), 1)
        self.setCentralWidget(root)

    def _build_sidebar(self) -> QFrame:
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(260)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(22, 24, 22, 20)
        layout.setSpacing(12)

        logo = QLabel("P")
        logo.setObjectName("SidebarLogo")
        app_name = QLabel("PPT Script to Video Bot")
        app_name.setObjectName("SidebarTitle")
        app_name.setWordWrap(True)
        subtitle = QLabel("Create narrated videos from PowerPoint and script files")
        subtitle.setObjectName("SidebarSubtitle")
        subtitle.setWordWrap(True)
        layout.addWidget(logo)
        layout.addWidget(app_name)
        layout.addWidget(subtitle)
        layout.addSpacing(22)

        self.nav_create = SidebarButton("Create Video", active=True)
        self.nav_history = SidebarButton("History")
        self.nav_settings = SidebarButton("Settings")
        self.nav_about = SidebarButton("About")
        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        for button in [self.nav_create, self.nav_history, self.nav_settings, self.nav_about]:
            self.nav_group.addButton(button)
            layout.addWidget(button)
            layout.addSpacing(2)
        layout.addStretch(1)

        tip = QFrame()
        tip.setObjectName("TipCard")
        tip_layout = QVBoxLayout(tip)
        tip_layout.setContentsMargins(14, 14, 14, 14)
        tip_title = QLabel("Quick Tip")
        tip_title.setObjectName("TipTitle")
        tip_body = QLabel("Validate your files first to check for missing or extra script slides.")
        tip_body.setObjectName("TipBody")
        tip_body.setWordWrap(True)
        tip_layout.addWidget(tip_title)
        tip_layout.addWidget(tip_body)
        layout.addWidget(tip)
        return sidebar

    def _build_main_area(self) -> QWidget:
        area = QWidget()
        area.setObjectName("MainArea")
        layout = QVBoxLayout(area)
        layout.setContentsMargins(26, 20, 26, 0)
        layout.setSpacing(14)
        layout.addLayout(self._build_topbar())

        content = QHBoxLayout()
        content.setSpacing(18)
        content.addWidget(self._build_left_column(), 7)
        content.addLayout(self._build_right_column(), 3)
        layout.addLayout(content, 1)
        layout.addWidget(self.bottom_status)
        return area

    def _build_topbar(self) -> QHBoxLayout:
        top = QHBoxLayout()
        small_title = QLabel("PPT Script to Video Bot")
        small_title.setObjectName("TopTitle")
        top.addWidget(small_title)
        top.addStretch(1)
        top.addWidget(self.device_indicator)
        top.addWidget(self.log_toggle)
        top.addWidget(self.help_button)
        top.addWidget(self.settings_button)
        top.setSpacing(8)
        return top

    def _build_left_column(self) -> QScrollArea:
        page_title = QLabel("Create New Video")
        page_title.setObjectName("PageTitle")
        page_subtitle = QLabel("Select your files and customize your video settings.")
        page_subtitle.setObjectName("PageSubtitle")

        files_card = QFrame()
        files_card.setObjectName("Card")
        add_shadow(files_card)
        files_card.setMinimumHeight(188)
        files_layout = QVBoxLayout(files_card)
        files_layout.setContentsMargins(16, 12, 16, 14)
        files_layout.setSpacing(7)
        files_layout.addLayout(card_header("1 Select Files"))
        self.ppt_card = FilePickerCard("PPT", "PowerPoint file", "Choose a .pptx slide deck.", "Change", self._choose_ppt)
        self.script_card = FilePickerCard("DOC", "Script DOCX file", "Choose the voiceover script.", "Change", self._choose_script)
        self.output_folder_card = FilePickerCard("OUT", "Output folder", "Choose where the MP4 will be saved.", "Change", self._choose_output_folder)
        files_layout.addWidget(self.ppt_card)
        files_layout.addWidget(self.script_card)
        files_layout.addWidget(self.output_folder_card)

        settings_card = QFrame()
        settings_card.setObjectName("Card")
        add_shadow(settings_card)
        settings_layout = QVBoxLayout(settings_card)
        settings_layout.setContentsMargins(16, 14, 16, 18)
        settings_layout.setSpacing(13)
        settings_layout.addLayout(card_header("2 Video Settings"))

        settings_content = QHBoxLayout()
        settings_content.setSpacing(20)
        fields = QGridLayout()
        fields.setContentsMargins(0, 0, 0, 0)
        fields.setHorizontalSpacing(16)
        fields.setVerticalSpacing(14)
        fields.addWidget(self._field("Output video name", self.output_name), 0, 0, 1, 2)
        fields.addWidget(self._field("TTS Provider", self.tts_provider), 1, 0)
        fields.addWidget(self._field("Quality mode", self.quality), 1, 1)
        fields.addWidget(self._field("Narration Voice", self.voice), 2, 0)
        fields.addWidget(self._field("Speech speed", self.speed), 2, 1)
        fields.addWidget(self._field("Pause after each slide", self.padding), 3, 0)
        fields.addWidget(self._checkbox_field("Narration cache", self.reuse_narration), 3, 1)
        fields.setColumnStretch(0, 1)
        fields.setColumnStretch(1, 1)
        fields.setColumnMinimumWidth(0, 230)
        fields.setColumnMinimumWidth(1, 230)
        settings_content.addLayout(fields, 65)
        preview_card = self._voice_preview_card()
        settings_content.addWidget(preview_card, 35, Qt.AlignTop)
        settings_layout.addLayout(settings_content)

        actions = QHBoxLayout()
        actions.setSpacing(10)
        actions.setContentsMargins(0, 4, 0, 0)
        actions.addWidget(self.validate_button)
        actions.addWidget(self.generate_button)
        actions.addWidget(self.cancel_button)
        actions.addStretch(1)
        action_wrapper = QWidget()
        action_wrapper.setObjectName("ActionRow")
        action_wrapper.setMinimumHeight(46)
        action_wrapper.setLayout(actions)
        settings_layout.addWidget(action_wrapper)

        log_card = QFrame()
        log_card.setObjectName("LogCard")
        log_card.setVisible(False)
        log_card.setMinimumHeight(150)
        self.log_card = log_card
        log_layout = QVBoxLayout(log_card)
        log_layout.setContentsMargins(16, 12, 16, 12)
        log_layout.setSpacing(8)
        log_title = QLabel("Activity Log")
        log_title.setObjectName("CardTitle")
        log_layout.addWidget(log_title)
        log_layout.addWidget(self.log_area)

        inner = QWidget()
        inner.setObjectName("LeftColumnContent")
        column = QVBoxLayout()
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(9)
        column.addWidget(page_title)
        column.addWidget(page_subtitle)
        column.addWidget(files_card)
        column.addWidget(settings_card)
        column.addWidget(log_card)
        column.addStretch(1)
        inner.setLayout(column)

        scroll = QScrollArea()
        scroll.setObjectName("MainScroll")
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setWidget(inner)
        self.left_scroll = scroll
        return scroll

    def _build_right_column(self) -> QVBoxLayout:
        column = QVBoxLayout()
        column.setSpacing(12)
        column.addWidget(self.summary_card)
        column.addWidget(self.progress_card)
        column.addWidget(self.output_card)
        column.addStretch(1)
        return column

    def _field(self, label: str, widget: QWidget) -> QWidget:
        wrapper = QWidget()
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(7)
        label_widget = QLabel(label)
        label_widget.setObjectName("FieldLabel")
        layout.addWidget(label_widget)
        layout.addWidget(widget)
        return wrapper

    def _checkbox_field(self, label: str, widget: QWidget) -> QWidget:
        wrapper = QWidget()
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(7)
        label_widget = QLabel(label)
        label_widget.setObjectName("FieldLabel")
        layout.addWidget(label_widget)
        layout.addWidget(widget)
        return wrapper

    def _voice_preview_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("PreviewCard")
        card.setMinimumWidth(260)
        card.setMaximumWidth(292)
        card.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Minimum)
        add_shadow(card)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(15, 14, 15, 14)
        layout.setSpacing(7)
        icon = QLabel("AUDIO")
        icon.setObjectName("PreviewIcon")
        icon.setFixedWidth(58)
        icon.setAlignment(Qt.AlignCenter)
        title = QLabel("Voice Preview")
        title.setObjectName("PreviewTitle")
        body = QLabel("Play the selected voice and speed.")
        body.setObjectName("MutedText")
        body.setWordWrap(True)
        self.preview_button = QPushButton("Play Preview")
        self.preview_button.setObjectName("SecondaryButton")
        self.preview_button.setToolTip("Generate and play a short voice sample.")
        layout.addWidget(icon)
        layout.addWidget(title)
        layout.addWidget(body)
        layout.addWidget(self.provider_description)
        layout.addWidget(self.provider_warning)
        layout.addSpacing(4)
        layout.addWidget(self.preview_button)
        return card

    def _connect_signals(self) -> None:
        self.validate_button.clicked.connect(lambda: self.validate_inputs(show_dialog=True))
        self.generate_button.clicked.connect(self.generate_video)
        self.cancel_button.clicked.connect(self.cancel_generation)
        self.settings_button.clicked.connect(self.open_settings)
        self.nav_settings.clicked.connect(self.open_settings)
        self.nav_history.clicked.connect(lambda: QMessageBox.information(self, "History", "History will appear here after more videos are created."))
        self.tts_provider.currentTextChanged.connect(self._on_provider_changed)
        self.nav_about.clicked.connect(self.show_about)
        self.help_button.clicked.connect(lambda: QMessageBox.information(self, "Help", "Choose your files, validate them, then generate your video."))
        self.log_toggle.toggled.connect(self._toggle_activity_log)
        self.preview_button.clicked.connect(self.play_voice_preview)
        self.nav_group.buttonClicked.connect(self._activate_sidebar_button)

    def _clear_preload_refs(self) -> None:
        self.preload_thread = None
        self.preload_worker = None

    def _set_button_icons(self) -> None:
        self.settings_button.setIcon(self.style().standardIcon(QStyle.SP_FileDialogDetailedView))
        self.help_button.setIcon(self.style().standardIcon(QStyle.SP_MessageBoxQuestion))
        self.log_toggle.setIcon(self.style().standardIcon(QStyle.SP_FileDialogContentsView))
        self.validate_button.setIcon(self.style().standardIcon(QStyle.SP_DialogApplyButton))
        self.generate_button.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))
        self.cancel_button.setIcon(self.style().standardIcon(QStyle.SP_DialogCancelButton))
        self.output_card.open_video_button.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))
        self.output_card.open_folder_button.setIcon(self.style().standardIcon(QStyle.SP_DirOpenIcon))

    def _apply_theme(self) -> None:
        chevron_icon = resource_path("app", "assets", "icons", "chevron-down.svg").as_posix()
        check_icon = resource_path("app", "assets", "icons", "check-white.svg").as_posix()
        stylesheet = """
            QWidget#Root, QWidget#MainArea {
                background: #F6F8FC;
                color: #111827;
                font-family: "Segoe UI", "Inter", Arial, sans-serif;
                font-size: 14px;
            }
            QLabel { background: transparent; }
            QToolTip {
                background: #111827;
                color: #FFFFFF;
                border: 1px solid #374151;
                border-radius: 8px;
                padding: 7px 9px;
                font-size: 12px;
            }
            QFrame#Sidebar {
                background: #140B35;
                border: 0;
            }
            #SidebarLogo {
                background: #6D28D9;
                color: white;
                min-width: 52px;
                max-width: 52px;
                min-height: 52px;
                max-height: 52px;
                border-radius: 16px;
                font-size: 26px;
                font-weight: 900;
                qproperty-alignment: AlignCenter;
            }
            #SidebarTitle { color: white; font-size: 17px; font-weight: 750; }
            #SidebarSubtitle { color: #C4B5FD; font-size: 12px; line-height: 1.35; }
            QPushButton#SidebarButton {
                background: transparent;
                color: #DDD6FE;
                border: 0;
                border-radius: 12px;
                padding: 8px 13px;
                text-align: left;
                font-weight: 650;
                min-height: 24px;
            }
            QPushButton#SidebarButton:checked {
                background: #2E1A73;
                color: white;
                border-left: 3px solid #A78BFA;
                padding-left: 10px;
            }
            QPushButton#SidebarButton:!checked:hover {
                background: rgba(255, 255, 255, 0.08);
                color: #F5F3FF;
                border-left: 3px solid transparent;
                padding-left: 10px;
            }
            QFrame#TipCard {
                background: #24145E;
                border: 1px solid #3B2A88;
                border-radius: 16px;
            }
            #TipTitle { color: white; font-weight: 700; }
            #TipBody { color: #DDD6FE; font-size: 12px; }
            #TopTitle { color: #475467; font-weight: 700; }
            #DeviceIndicator {
                background: #F3E8FF;
                color: #7C3AED;
                border: 1px solid #E9D5FF;
                border-radius: 11px;
                padding: 6px 10px;
                font-weight: 650;
                min-height: 22px;
            }
            #PageTitle { color: #111827; font-size: 28px; font-weight: 800; }
            #PageSubtitle, #MutedText, #MetricLabel { color: #667085; }
            #WarningText {
                background: #FFF7ED;
                color: #C2410C;
                border: 1px solid #FED7AA;
                border-radius: 10px;
                padding: 8px 10px;
                font-size: 12px;
            }
            QFrame#Card, QFrame#LogCard {
                background: #FFFFFF;
                border: 1px solid #DDE5F0;
                border-radius: 18px;
            }
            QScrollArea#MainScroll,
            QWidget#LeftColumnContent {
                background: transparent;
                border: 0;
            }
            #CardTitle { color: #111827; font-size: 16px; font-weight: 650; }
            #NumberBadge {
                background: #F3E8FF;
                color: #6D28D9;
                border-radius: 10px;
                min-width: 24px;
                min-height: 24px;
                qproperty-alignment: AlignCenter;
                font-weight: 750;
            }
            QFrame#FileRow {
                background: #FBFCFE;
                border: 1px solid #DDE5F0;
                border-radius: 14px;
            }
            QFrame#FileRow:hover {
                background: #FFFFFF;
                border: 1px solid #D8B4FE;
            }
            QLabel#FileIcon {
                background: #F3E8FF;
                color: #6D28D9;
                border-radius: 12px;
                min-width: 42px;
                max-width: 42px;
                min-height: 42px;
                max-height: 42px;
                qproperty-alignment: AlignCenter;
                font-weight: 700;
            }
            #FileTitle, #FieldLabel { color: #344054; font-size: 13px; font-weight: 600; }
            #FileName { color: #111827; font-size: 14px; font-weight: 650; }
            #CheckOn {
                background: transparent;
                color: #16A34A;
                border-radius: 10px;
                padding: 3px 6px;
                font-size: 12px;
                font-weight: 650;
            }
            #CheckOff {
                background: transparent;
                color: #98A2B3;
                border-radius: 10px;
                padding: 3px 6px;
                font-size: 12px;
                font-weight: 500;
            }
            QLineEdit, QComboBox, QDoubleSpinBox {
                background: #FFFFFF;
                border: 1px solid #D8E0EC;
                border-radius: 10px;
                padding: 6px 10px;
                min-height: 24px;
                color: #111827;
            }
            QLineEdit:hover, QComboBox:hover, QDoubleSpinBox:hover {
                border: 1px solid #C4B5FD;
                background: #FDFDFF;
            }
            QLineEdit:focus, QComboBox:focus, QDoubleSpinBox:focus {
                border: 1px solid #7C3AED;
                background: #FFFFFF;
            }
            QComboBox::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 28px;
                border-left: 0;
                background: transparent;
            }
            QComboBox::down-arrow {
                image: url(__CHEVRON_ICON__);
                width: 12px;
                height: 12px;
                margin-right: 8px;
            }
            QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {
                width: 18px;
                border: 0;
                background: transparent;
            }
            QCheckBox {
                color: #344054;
                spacing: 9px;
                padding: 6px 0;
                background: transparent;
                border: 0;
                min-height: 24px;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
                border-radius: 5px;
                border: 1px solid #C8D2E1;
                background: #FFFFFF;
            }
            QCheckBox::indicator:hover {
                border: 1px solid #A78BFA;
                background: #FAF5FF;
            }
            QCheckBox::indicator:checked {
                background: #7C3AED;
                border: 1px solid #7C3AED;
                image: url(__CHECK_ICON__);
            }
            QCheckBox::indicator:checked:hover {
                background: #6D28D9;
                border: 1px solid #6D28D9;
            }
            QPushButton {
                border-radius: 10px;
                padding: 7px 13px;
                font-size: 14px;
                font-weight: 650;
                min-height: 18px;
            }
            QPushButton#PrimaryButton {
                background: #7C3AED;
                color: white;
                border: 1px solid #7C3AED;
            }
            QPushButton#PrimaryButton:hover { background: #6D28D9; border-color: #6D28D9; }
            QPushButton#OutlinePurpleButton {
                background: #FFFFFF;
                color: #7C3AED;
                border: 1px solid #C4B5FD;
            }
            QPushButton#OutlinePurpleButton:hover { background: #F5F3FF; }
            QPushButton#SecondaryButton, QPushButton#SmallOutlineButton, QPushButton#TopButton {
                background: #F8FAFC;
                color: #344054;
                border: 1px solid #E2E8F0;
            }
            QPushButton#SecondaryButton:hover, QPushButton#SmallOutlineButton:hover, QPushButton#TopButton:hover {
                background: #FFFFFF;
                border-color: #CBD5E1;
            }
            QPushButton#SmallOutlineButton { padding: 7px 12px; min-height: 18px; }
            QPushButton#TopButton { padding: 6px 10px; min-height: 22px; }
            QPushButton#NeutralButton {
                background: #EEF2F7;
                color: #475467;
                border: 1px solid #E2E8F0;
            }
            QPushButton:disabled {
                background: #F1F5F9;
                color: #64748B;
                border: 1px solid #E2E8F0;
            }
            QPushButton#PrimaryButton:disabled,
            QPushButton#OutlinePurpleButton:disabled,
            QPushButton#SecondaryButton:disabled,
            QPushButton#SmallOutlineButton:disabled,
            QPushButton#NeutralButton:disabled,
            QPushButton#TopButton:disabled {
                background: #F1F5F9;
                color: #64748B;
                border: 1px solid #E2E8F0;
            }
            QFrame#PreviewCard {
                background: #F8F5FF;
                border: 1px solid #E9D5FF;
                border-radius: 16px;
            }
            #PreviewIcon {
                background: #7C3AED;
                color: white;
                border-radius: 10px;
                padding: 4px 8px;
                font-size: 11px;
                font-weight: 700;
            }
            #PreviewTitle, #OutputName, #CurrentStep { color: #111827; font-weight: 700; }
            #BadgeNeutral, #BadgeReady, #BadgeWarning, #BadgeError {
                border-radius: 12px;
                padding: 7px 10px;
                font-weight: 700;
                qproperty-alignment: AlignCenter;
            }
            #BadgeNeutral { background: #EEF2F7; color: #475467; }
            #BadgeReady { background: #ECFDF3; color: #16A34A; }
            #BadgeWarning { background: #FFF7ED; color: #F97316; }
            #BadgeError { background: #FFF1F2; color: #B42318; }
            QFrame#MetricRow {
                background: #F8FAFC;
                border: 1px solid #EEF2F7;
                border-radius: 12px;
            }
            #MetricValue { color: #111827; font-size: 15px; font-weight: 700; }
            #PercentBubble {
                background: #F3E8FF;
                color: #7C3AED;
                border-radius: 32px;
                min-width: 52px;
                max-width: 52px;
                min-height: 52px;
                max-height: 52px;
                qproperty-alignment: AlignCenter;
                font-size: 20px;
                font-weight: 750;
            }
            QProgressBar {
                background: #EEF2F7;
                border: 0;
                border-radius: 8px;
                min-height: 14px;
                max-height: 14px;
                color: transparent;
            }
            QProgressBar::chunk { background: #7C3AED; border-radius: 8px; }
            #StepDotPending, #StepDotActive, #StepDotDone, #StepDotFailed {
                min-width: 9px;
                max-width: 9px;
                min-height: 9px;
                max-height: 9px;
                border-radius: 4px;
            }
            #StepDotPending { background: #CBD5E1; }
            #StepDotActive { background: #7C3AED; }
            #StepDotDone { background: #16A34A; }
            #StepDotFailed { background: #FCA5A5; }
            #StepTitle { color: #344054; font-weight: 600; }
            #StepStatePending { color: #98A2B3; }
            #StepStateActive { color: #7C3AED; font-weight: 650; }
            #StepStateDone { color: #16A34A; font-weight: 650; }
            #StepStateFailed { color: #B42318; font-weight: 650; }
            QTextEdit#ActivityLog {
                background: #FBFCFE;
                border: 1px solid #E2E8F0;
                border-radius: 12px;
                padding: 10px;
                min-height: 118px;
            }
            QToolButton#LogToggle {
                background: #F8FAFC;
                border: 1px solid #E2E8F0;
                border-radius: 10px;
                padding: 6px 10px;
                color: #475467;
                text-align: left;
                font-weight: 650;
                min-height: 22px;
            }
            QToolButton#LogToggle:checked {
                background: #F5F3FF;
                color: #6D28D9;
                border-color: #C4B5FD;
            }
            QToolButton#LogToggle:hover {
                background: #FFFFFF;
                border-color: #CBD5E1;
            }
            #BottomStatus {
                background: #FFFFFF;
                border-top: 1px solid #E2E8F0;
                color: #667085;
                padding: 8px 12px;
                font-size: 12px;
            }
            QScrollBar:vertical, QScrollBar:horizontal {
                background: transparent;
                border: 0;
                width: 10px;
                height: 10px;
                margin: 2px;
            }
            QScrollBar::handle:vertical, QScrollBar::handle:horizontal {
                background: #CBD5E1;
                border-radius: 5px;
                min-height: 28px;
                min-width: 28px;
            }
            QScrollBar::handle:hover {
                background: #94A3B8;
            }
            QScrollBar::add-line, QScrollBar::sub-line,
            QScrollBar::add-page, QScrollBar::sub-page {
                background: transparent;
                border: 0;
            }
            """
        self.setStyleSheet(stylesheet.replace("__CHEVRON_ICON__", chevron_icon).replace("__CHECK_ICON__", check_icon))

    def _choose_ppt(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Choose PowerPoint", str(Path.home()), "PowerPoint (*.pptx)")
        if path:
            self.ppt_path.setText(path)
            self.validation_result = None
            self._refresh_file_cards()
            self.summary_card.reset()

    def _choose_script(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Choose Script", str(Path.home()), "Word Documents (*.docx)")
        if path:
            self.script_path.setText(path)
            self.validation_result = None
            self._refresh_file_cards()
            self.summary_card.reset()

    def _choose_output_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Choose Output Folder", self.output_folder.text() or str(Path.home()))
        if path:
            self.output_folder.setText(path)
            self.validation_result = None
            self._refresh_file_cards()
            self.summary_card.reset()

    def _refresh_file_cards(self) -> None:
        self.ppt_card.set_path(self.ppt_path.text())
        self.script_card.set_path(self.script_path.text())
        self.output_folder_card.set_path(self.output_folder.text())

    def _request_from_form(self) -> PipelineRequest:
        provider = "xtts" if self.tts_provider.currentText().startswith("XTTS") else "edge"
        return PipelineRequest(
            ppt_path=Path(self.ppt_path.text()).expanduser(),
            script_path=Path(self.script_path.text()).expanduser(),
            output_folder=Path(self.output_folder.text()).expanduser(),
            output_name=self.output_name.text().strip(),
            voice=self.voice.currentText().strip(),
            speech_speed=self.speed.currentText().strip(),
            padding_seconds=float(self.padding.value()),
            tts_engine=provider,
            quality_mode=self.quality.currentText(),
            reuse_existing_narration=self.reuse_narration.isChecked(),
        )

    def _on_provider_changed(self, value: str) -> None:
        is_xtts = value.startswith("XTTS")
        self.provider_warning.setVisible(False)
        self.generate_button.setEnabled(True)
        self.quality.setEnabled(is_xtts)
        self.voice.clear()
        if is_xtts:
            self.voice.addItems(SettingsWindow.VOICES)
            self.voice.setCurrentText(self.settings.default_voice)
            self.provider_description.setText("Free local high-quality narration voice.")
        else:
            self.voice.addItems(["en-US-AriaNeural", "en-US-GuyNeural", "en-US-JennyNeural"])
            self.voice.setCurrentText("en-US-AriaNeural")
            self.provider_description.setText("Fast lightweight cloud narration.")
        self.preview_button.setToolTip(
            "Generate and play a short XTTS-v2 voice sample." if is_xtts else "Generate and play a short Edge-TTS voice sample."
        )

    def play_voice_preview(self) -> None:
        if self.preview_thread and self.preview_thread.isRunning():
            return
        self.settings = load_settings()
        self.preview_button.setEnabled(False)
        self.preview_button.setText("Preparing...")
        provider = "xtts" if self.tts_provider.currentText().startswith("XTTS") else "edge"
        self._append_log("Loading voice preview...", "info")
        self.preview_worker = PreviewWorker(
            voice=self.voice.currentText().strip(),
            speed=self.speed.currentText().strip(),
            quality_mode=self.quality.currentText(),
            provider=provider,
            settings=self.settings,
        )
        self.preview_thread = QThread(self)
        self.preview_thread.setStackSize(TTS_THREAD_STACK_SIZE)
        self.preview_worker.moveToThread(self.preview_thread)
        self.preview_thread.started.connect(self.preview_worker.run)
        self.preview_worker.log.connect(self._append_log)
        self.preview_worker.completed.connect(self._on_preview_ready)
        self.preview_worker.failed.connect(self._on_preview_failed)
        self.preview_worker.completed.connect(self.preview_thread.quit)
        self.preview_worker.failed.connect(self.preview_thread.quit)
        self.preview_thread.finished.connect(self.preview_worker.deleteLater)
        self.preview_thread.finished.connect(self.preview_thread.deleteLater)
        self.preview_thread.finished.connect(self._clear_preview_refs)
        self.preview_thread.start()

    @Slot(object)
    def _on_preview_ready(self, path: Path) -> None:
        self.preview_player.setSource(QUrl.fromLocalFile(str(path)))
        self.preview_player.setVolume(0.9)
        self.preview_player.play()
        self.preview_button.setText("Play Preview")
        self.preview_button.setEnabled(True)
        self._append_log("Voice preview ready.", "success")

    @Slot(str)
    def _on_preview_failed(self, message: str) -> None:
        self.preview_button.setText("Play Preview")
        self.preview_button.setEnabled(True)
        self._show_error(message)

    def _clear_preview_refs(self) -> None:
        self.preview_thread = None
        self.preview_worker = None

    def _maybe_preload_xtts(self) -> None:
        if not self.settings.xtts_preload_model or (self.preload_thread and self.preload_thread.isRunning()):
            return
        self._append_log("Preloading XTTS-v2...", "info")
        self.preload_worker = ModelPreloadWorker(self.settings)
        self.preload_thread = QThread(self)
        self.preload_thread.setStackSize(TTS_THREAD_STACK_SIZE)
        self.preload_worker.moveToThread(self.preload_thread)
        self.preload_thread.started.connect(self.preload_worker.run)
        self.preload_worker.log.connect(self._append_log)
        self.preload_worker.completed.connect(lambda: self._append_log("XTTS-v2 preload complete.", "success"))
        self.preload_worker.failed.connect(lambda message: self._append_log(message, "warning"))
        self.preload_worker.completed.connect(self.preload_thread.quit)
        self.preload_worker.failed.connect(self.preload_thread.quit)
        self.preload_thread.finished.connect(self.preload_worker.deleteLater)
        self.preload_thread.finished.connect(self.preload_thread.deleteLater)
        self.preload_thread.finished.connect(self._clear_preload_refs)
        self.preload_thread.start()

    def _clear_preload_refs(self) -> None:
        self.preload_thread = None
        self.preload_worker = None

    def validate_inputs(self, show_dialog: bool = True) -> bool:
        try:
            self.settings = load_settings()
            result = validate_request(self._request_from_form(), self.settings)
            self.validation_result = result
            self._update_summary(result)
            for parser_message in result.parser_debug:
                self._append_log(parser_message, "info")
            self._append_log(f"Found script sections for slides: {result.parsed_slide_numbers}", "info")

            if result.errors:
                for error in result.errors:
                    self._append_log(error, "error")
            elif result.warnings:
                for warning in result.warnings:
                    self._append_log(warning, "warning")
            else:
                self._append_log("Validation passed. Ready to generate the video.", "success")

            if show_dialog:
                ValidationDialog(result, self).exec()
            return result.can_generate
        except FriendlyPipelineError as exc:
            self._show_error(str(exc))
            return False
        except Exception as exc:
            self._show_error(f"The files could not be validated. Details: {exc}")
            return False

    def _update_summary(self, result: ValidationResult) -> None:
        report = result.report
        if result.errors:
            self.summary_card.set_status("Blocking issue", "error")
            self.summary_card.message.setText("Please fix missing files, dependencies, or missing slide scripts before generating.")
        elif result.warnings:
            self.summary_card.set_status("Ready with warning", "warning")
            self.summary_card.message.setText("You can generate the video. Extra script sections will be skipped.")
        else:
            self.summary_card.set_status("Ready", "ready")
            self.summary_card.message.setText("Files are matched and ready for video generation.")
        self.summary_card.values["ppt"].setText(str(report.ppt_slide_count))
        self.summary_card.values["scripts"].setText(str(report.script_section_count))
        self.summary_card.values["matched"].setText(self._compact_numbers(report.matched_slides))
        self.summary_card.values["missing"].setText("None" if not report.missing_scripts else self._compact_numbers(report.missing_scripts))
        self.summary_card.values["extra"].setText("None" if not report.extra_scripts else self._compact_numbers(report.extra_scripts))

    def _compact_numbers(self, values: list[int]) -> str:
        if not values:
            return "None"
        if len(values) <= 8:
            return ", ".join(str(value) for value in values)
        return f"{values[0]}-{values[-1]} ({len(values)})"

    def generate_video(self) -> None:
        if self.thread and self.thread.isRunning():
            return
        if not self.validate_inputs(show_dialog=False):
            return
        request = self._request_from_form()

        self.started_at = QDateTime.currentDateTime()
        self.elapsed_timer.start(1000)
        self.progress_card.reset()
        self.output_card.set_output(None)
        self.final_video_path = None
        self._set_running(True)
        self._refresh_dependency_status("Processing")
        self._append_log("Starting video generation...", "info")

        self.worker = PipelineWorker(request, self.settings)
        self.thread = QThread(self)
        self.thread.setStackSize(TTS_THREAD_STACK_SIZE)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.progress.connect(self._on_progress)
        self.worker.log.connect(self._append_log)
        self.worker.completed.connect(self._on_completed)
        self.worker.failed.connect(self._on_failed)
        self.worker.cancelled.connect(self._on_cancelled)
        self.worker.completed.connect(self.thread.quit)
        self.worker.failed.connect(self.thread.quit)
        self.worker.cancelled.connect(self.thread.quit)
        self.thread.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.finished.connect(lambda: self._set_thread_refs_none())
        self.thread.start()

    def cancel_generation(self) -> None:
        if self.worker:
            self.worker.cancel()
            self.progress_card.current_step.setText("Cancelling after the current step...")
            self._append_log("Cancelling after the current step finishes...", "warning")

    @Slot(int, str)
    def _on_progress(self, value: int, message: str) -> None:
        elapsed = self._elapsed_seconds()
        self.progress_card.set_progress(value, self._step_title(message), elapsed)
        self._update_steps(value, message)
        self._append_log(message, "info")

    def _step_title(self, message: str) -> str:
        if "Exporting" in message:
            return "Exporting slides"
        if "Parsing" in message:
            return "Parsing script"
        if "Generating narration" in message:
            return "Generating narration"
        if "Building video segment" in message:
            return "Building video segments"
        if "Combining" in message:
            return "Combining final video"
        return message

    def _update_steps(self, value: int, message: str) -> None:
        steps = self.progress_card.steps
        if "Exporting" in message:
            steps["export"].set_state("active")
        elif "Parsing" in message:
            steps["export"].set_state("done")
            steps["parse"].set_state("active")
        elif "Generating narration" in message:
            steps["export"].set_state("done")
            steps["parse"].set_state("done")
            steps["audio"].set_state("active")
        elif "Building video segment" in message:
            steps["export"].set_state("done")
            steps["parse"].set_state("done")
            steps["audio"].set_state("done")
            steps["segments"].set_state("active")
        elif "Combining" in message:
            steps["export"].set_state("done")
            steps["parse"].set_state("done")
            steps["audio"].set_state("done")
            steps["segments"].set_state("done")
            steps["combine"].set_state("active")
        elif value >= 100:
            for row in steps.values():
                row.set_state("done")

    @Slot(object, object)
    def _on_completed(self, output_path: Path, validation: ValidationResult) -> None:
        self.elapsed_timer.stop()
        self.validation_result = validation
        self.final_video_path = Path(output_path)
        self.progress_card.set_progress(100, "Video complete", self._elapsed_seconds())
        for row in self.progress_card.steps.values():
            row.set_state("done")
        self.output_card.set_output(self.final_video_path)
        self._append_log(f"Video saved to: {self.final_video_path}", "success")
        self._set_running(False)
        self._refresh_dependency_status("Complete")
        QMessageBox.information(self, "Video Complete", f"Your video is ready:\n{self.final_video_path}")

    @Slot(str)
    def _on_failed(self, message: str) -> None:
        self.elapsed_timer.stop()
        self.progress_card.set_failed()
        self._show_error(message)
        self._set_running(False)
        self._refresh_dependency_status("Ready")

    @Slot()
    def _on_cancelled(self) -> None:
        self.elapsed_timer.stop()
        self.progress_card.current_step.setText("Video generation cancelled")
        self._append_log("Video generation cancelled.", "warning")
        self._set_running(False)
        self._refresh_dependency_status("Ready")

    def _refresh_elapsed(self) -> None:
        if self.started_at:
            elapsed = self._elapsed_seconds()
            self.progress_card.elapsed.setText(f"Elapsed {elapsed // 60:02d}:{elapsed % 60:02d}")

    def _elapsed_seconds(self) -> int:
        if not self.started_at:
            return 0
        return self.started_at.secsTo(QDateTime.currentDateTime())

    def _set_running(self, running: bool) -> None:
        self.generate_button.setEnabled(not running)
        self.validate_button.setEnabled(not running)
        self.cancel_button.setEnabled(running)
        self.settings_button.setEnabled(not running)
        self.nav_settings.setEnabled(not running)
        self.tts_provider.setEnabled(not running)
        self.reuse_narration.setEnabled(not running)
        if not running:
            self.generate_button.setEnabled(True)

    def _set_thread_refs_none(self) -> None:
        self.thread = None
        self.worker = None

    def open_settings(self) -> None:
        dialog = SettingsWindow(self)
        if dialog.exec():
            self.settings = load_settings()
            self.output_folder.setText(self.settings.default_output_folder)
            self.speed.setCurrentText(self.settings.default_speech_speed)
            self.quality.setCurrentText(self.settings.xtts_generation_quality)
            self.reuse_narration.setChecked(self.settings.reuse_existing_narration)
            self._on_provider_changed(self.tts_provider.currentText())
            self.device_indicator.setText(current_tts_device_label(self.settings))
            self._refresh_file_cards()
            self._refresh_dependency_status("Ready")
            self._append_log("Settings saved.", "success")
            self._maybe_preload_xtts()

    def open_output_folder(self) -> None:
        folder = Path(self.output_folder.text()).expanduser()
        if folder.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))
        else:
            self._show_error("The output folder could not be found. Please choose it again.")

    def show_about(self) -> None:
        try:
            import sys
            import TTS as tts_package
        except Exception:
            tts_version = "not available"
        else:
            tts_version = getattr(tts_package, "__version__", "unknown")
        errors = check_system_requirements(self.settings)
        ffmpeg = "Detected" if not any("FFmpeg" in error for error in errors) else "Missing"
        libreoffice = "Detected" if not any("LibreOffice" in error for error in errors) else "Missing"
        QMessageBox.information(
            self,
            "About",
            "\n".join(
                [
                    "PPT Script to Video Bot",
                    f"Version {APP_VERSION}",
                    f"Python {sys.version.split()[0]}",
                    f"XTTS / Coqui TTS {tts_version}",
                    f"FFmpeg: {ffmpeg}",
                    f"LibreOffice: {libreoffice}",
                    f"User data: {user_data_dir()}",
                    "",
                    "TTS providers: XTTS-v2 local and Edge-TTS.",
                ]
            ),
        )

    def open_final_video(self) -> None:
        if self.final_video_path and self.final_video_path.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.final_video_path)))
        else:
            self._show_error("The final video could not be found yet.")

    def _refresh_dependency_status(self, app_state: str) -> None:
        errors = check_system_requirements(self.settings)
        ffmpeg = "Found" if not any("FFmpeg" in error for error in errors) else "Missing"
        libreoffice = "Found" if not any("LibreOffice" in error for error in errors) else "Missing"
        self.bottom_status.setText(f"{app_state}    FFmpeg: {ffmpeg}    LibreOffice: {libreoffice}    Version {APP_VERSION}")

    def _show_error(self, message: str) -> None:
        self._append_log(message, "error")
        QMessageBox.critical(self, "Needs Attention", message)

    def _activate_sidebar_button(self, button: QPushButton) -> None:
        for nav_button in [self.nav_create, self.nav_history, self.nav_settings, self.nav_about]:
            nav_button.setChecked(nav_button is button)

    def _toggle_activity_log(self, visible: bool) -> None:
        self.log_toggle.setText("Hide Activity Log" if visible else "Show Activity Log")
        self.log_area.setVisible(visible)
        if self.log_card:
            self.log_card.setVisible(visible)
            if visible and self.left_scroll:
                self.left_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
                QTimer.singleShot(0, lambda: self.left_scroll.ensureWidgetVisible(self.log_card, 0, 16))
            elif self.left_scroll:
                self.left_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

    @Slot(str, str)
    def _append_log(self, message: str, level: str = "info") -> None:
        color = {
            "success": "#16A34A",
            "error": "#DC2626",
            "warning": "#F97316",
            "info": "#667085",
        }.get(level, "#667085")
        timestamp = QDateTime.currentDateTime().toString("hh:mm")
        self.log_area.append(f'<span style="color:#98A2B3;">{timestamp}</span> <span style="color:{color};">{message}</span>')
