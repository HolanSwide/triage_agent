"""Deterministic TASK 02 knowledge-base and log fixture generation."""

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional


KNOWLEDGE_BASE: Dict[str, Dict[str, str]] = {
    "RU_ERROR": {"expected_action": "PULL_OVER"},
    "SENSOR_ERROR": {"expected_action": "SAFE_STOP"},
    "BRAKE_ERROR": {"expected_action": "EMERGENCY_BRAKE"},
    "CAMERA_ERROR": {"expected_action": "EXIT_AUTONOMOUS_MODE"},
    "LIDAR_ERROR": {"expected_action": "REDUCE_SPEED"},
}


@dataclass(frozen=True)
class GeneratedCase:
    name: str
    fault: str
    expected_action: str
    log_text: str
    expected_category: str


def _line(fault: str, action: Optional[str] = None) -> str:
    fault_line = f"09-01 23:02:10 ERROR /ru: new fault: {fault}, simulated fault."
    if action is None:
        return fault_line
    return "\n".join(
        [
            fault_line,
            f"09-01 23:02:11 INFO /planner: publish action {action}.",
        ]
    )


def generate_positive_cases() -> List[GeneratedCase]:
    return [
        GeneratedCase(
            name=f"positive_{fault.lower()}",
            fault=fault,
            expected_action=rule["expected_action"],
            log_text=_line(fault, rule["expected_action"]),
            expected_category="PASS",
        )
        for fault, rule in KNOWLEDGE_BASE.items()
    ]


def generate_negative_cases() -> List[GeneratedCase]:
    fault = "RU_ERROR"
    expected_action = KNOWLEDGE_BASE[fault]["expected_action"]
    return [
        GeneratedCase(
            name="negative_no_fault_injection",
            fault=fault,
            expected_action=expected_action,
            log_text="09-01 23:02:10 INFO /system: test window started.",
            expected_category="RETEST",
        ),
        GeneratedCase(
            name="negative_wrong_fault_injection",
            fault=fault,
            expected_action=expected_action,
            log_text=_line("SENSOR_ERROR", "SAFE_STOP"),
            expected_category="RETEST",
        ),
        GeneratedCase(
            name="negative_wrong_action",
            fault=fault,
            expected_action=expected_action,
            log_text=_line(fault, "SAFE_STOP"),
            expected_category="FAIL",
        ),
        GeneratedCase(
            name="negative_empty_log",
            fault=fault,
            expected_action=expected_action,
            log_text="",
            expected_category="RETEST",
        ),
        GeneratedCase(
            name="negative_unrelated_log",
            fault=fault,
            expected_action=expected_action,
            log_text="09-01 23:02:10 INFO /planning: route updated.",
            expected_category="RETEST",
        ),
    ]


def write_cases(output_dir: Path) -> List[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    paths: List[Path] = []
    for case in generate_positive_cases() + generate_negative_cases():
        path = output_dir / f"{case.name}.txt"
        path.write_text(case.log_text + ("\n" if case.log_text else ""), encoding="utf-8")
        paths.append(path)
    return paths
