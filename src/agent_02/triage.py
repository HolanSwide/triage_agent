"""Deterministic evidence sufficiency, triage, and guardrail decisions."""

from typing import List, Optional, Tuple

from .models import Evidence, TestSpec, TriageResult


def _find(evidence: List[Evidence], key: str, source: str) -> Optional[Evidence]:
    for item in reversed(evidence):
        if item.key == key and item.source == source:
            return item
    return None


def evidence_sufficiency(evidence: List[Evidence], spec: TestSpec) -> bool:
    knowledge = _find(evidence, spec.fault, "knowledge_base")
    fault = _find(evidence, spec.fault, "log")
    action = _find(evidence, spec.expected_action, "log")
    return knowledge is not None and fault is not None and (
        not fault.present or (action is not None)
    )


def deterministic_triage(evidence: List[Evidence], spec: TestSpec) -> Tuple[TriageResult, str]:
    knowledge = _find(evidence, spec.fault, "knowledge_base")
    fault = _find(evidence, spec.fault, "log")
    action = _find(evidence, spec.expected_action, "log")
    if knowledge is None or fault is None or (fault.present and action is None):
        raise ValueError("insufficient evidence for deterministic triage")
    if not knowledge.present or knowledge.value != spec.expected_action:
        return "RETEST", "TestSpec 的预期行为与知识库规则不一致或知识库缺少有效规则"
    if not fault.present:
        return "RETEST", f"目标故障 {spec.fault} 未在完整日志窗口中观察到"
    if action.present:
        return "PASS", f"故障 {spec.fault} 已注入，且观察到预期指令 {spec.expected_action}"
    return "FAIL", f"故障 {spec.fault} 已注入，但未观察到预期指令 {spec.expected_action}"


def guardrail_fallback(rounds: int, max_rounds: int) -> Tuple[TriageResult, str]:
    if rounds < max_rounds:
        raise ValueError("investigation has not reached its configured limit")
    return "RETEST", f"系统保底：调查达到最大轮数 {max_rounds}，Evidence 仍不充分"
