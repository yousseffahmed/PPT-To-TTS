from __future__ import annotations

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QTextEdit, QVBoxLayout

from app.core.pipeline_runner import ValidationResult


class ValidationDialog(QDialog):
    def __init__(self, result: ValidationResult, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Validation Result")
        self.setMinimumSize(520, 420)

        title = QLabel("Validation complete")
        title.setObjectName("DialogTitle")

        details = QTextEdit()
        details.setReadOnly(True)
        details.setPlainText(self._format_result(result))

        buttons = QDialogButtonBox(QDialogButtonBox.Ok)
        buttons.accepted.connect(self.accept)

        layout = QVBoxLayout(self)
        layout.addWidget(title)
        layout.addWidget(details)
        layout.addWidget(buttons)

    @staticmethod
    def _format_result(result: ValidationResult) -> str:
        report = result.report
        lines = [
            f"PPT slides found: {report.ppt_slide_count}",
            f"Script sections found: {report.script_section_count}",
            f"Parsed slide numbers: {result.parsed_slide_numbers}",
            f"Matched slides: {report.matched_slides}",
            f"Missing scripts: {report.missing_scripts or 'None'}",
            f"Extra scripts: {report.extra_scripts or 'None'}",
            f"Duplicate script sections: {report.duplicate_script_sections or 'None'}",
        ]
        if result.warnings:
            lines.extend(["", "Warnings:"])
            lines.extend(f"- {warning}" for warning in result.warnings)
        if result.errors:
            lines.extend(["", "Needs attention:"])
            lines.extend(f"- {error}" for error in result.errors)
        return "\n".join(lines)
