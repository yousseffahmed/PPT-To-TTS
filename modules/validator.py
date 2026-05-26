from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from modules.script_parser import ScriptSection


@dataclass(frozen=True)
class ValidationReport:
    ppt_slide_count: int
    script_section_count: int
    matched_slides: list[int]
    missing_scripts: list[int]
    extra_scripts: list[int]
    duplicate_script_sections: list[int]
    estimated_duration_seconds: float


def build_validation_report(
    ppt_slide_count: int,
    sections: dict[int, ScriptSection],
    duplicate_script_sections: list[int],
    audio_durations: dict[int, float] | None = None,
    padding_seconds: float = 0.5,
) -> ValidationReport:
    slide_numbers = set(range(1, ppt_slide_count + 1))
    script_numbers = set(sections.keys())
    matched_slides = sorted(slide_numbers & script_numbers)
    missing_scripts = sorted(slide_numbers - script_numbers)
    extra_scripts = sorted(script_numbers - slide_numbers)
    durations = audio_durations or {}
    estimated_duration = sum(durations.get(number, 0.0) + padding_seconds for number in matched_slides)
    return ValidationReport(
        ppt_slide_count=ppt_slide_count,
        script_section_count=len(sections),
        matched_slides=matched_slides,
        missing_scripts=missing_scripts,
        extra_scripts=extra_scripts,
        duplicate_script_sections=duplicate_script_sections,
        estimated_duration_seconds=round(estimated_duration, 3),
    )


def write_report(report: ValidationReport, report_path: Path) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(asdict(report), indent=2), encoding="utf-8")
