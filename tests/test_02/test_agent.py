"""TASK 02 full-chain tests and JSON report generation."""

import json
import os
import unittest
from pathlib import Path
from typing import Any, Dict, List

from langchain_core.messages import AIMessage
from langchain_core.messages import ToolMessage
from langchain_deepseek import ChatDeepSeek

from src.agent_02.graph import build_graph, initialize_state
from src.agent_02.evidence import evidence_reducer, knowledge_to_evidence, query_logs_to_evidence
from src.agent_02.models import RuntimeContext, TestSpec
from src.agent_02.triage import deterministic_triage, evidence_sufficiency
from tests.test_02.test_data import KNOWLEDGE_BASE, GeneratedCase, generate_negative_cases, generate_positive_cases


TEST_DIR = Path(__file__).parent
LOG_DIR = TEST_DIR / "logs"
REPORT_PATH = TEST_DIR / "test_report.json"


class TimeoutOutputModel:
    def invoke(self, prompt: Any) -> Any:
        raise TimeoutError("simulated LLM timeout")


class StopInvestigator:
    def bind_tools(self, tools: Any) -> Any:
        return self

    def invoke(self, messages: Any) -> AIMessage:
        return AIMessage(content="无法继续调查", tool_calls=[])


def _supplemental_checks() -> List[Dict[str, Any]]:
    spec = TestSpec(fault="RU_ERROR", expected_action="PULL_OVER")
    knowledge_conflict = knowledge_to_evidence(
        {"fault": "RU_ERROR", "expected_action": "SAFE_STOP"}, "k"
    )
    conflict_evidence = knowledge_conflict + [
        query_logs_to_evidence({"query": "RU_ERROR", "matches": [{"timestamp": "t", "raw": "RU_ERROR"}]}, "f")[0],
        query_logs_to_evidence({"query": "PULL_OVER", "matches": [{"timestamp": "t", "raw": "PULL_OVER"}]}, "a")[0],
    ]
    conflict_result = deterministic_triage(conflict_evidence, spec)[0]
    absent = query_logs_to_evidence({"query": "RU_ERROR", "matches": []}, "absent")
    present = query_logs_to_evidence({"query": "RU_ERROR", "matches": [{"timestamp": "t", "raw": "RU_ERROR"}]}, "present")
    duplicate = evidence_reducer([], present + present)
    same_tool = evidence_reducer([], knowledge_to_evidence({"fault": "RU_ERROR", "expected_action": "PULL_OVER"}, "same") * 2)
    unknown_is_insufficient = not evidence_sufficiency([], spec)
    absent_is_distinct = absent[0].present is False and present[0].present is True
    invalid_runtime: RuntimeContext = {
        "log_path": TEST_DIR / "missing.log",
        "knowledge_base": KNOWLEDGE_BASE,
        "max_investigation_rounds": 2,
    }
    invalid_result = build_graph(StopInvestigator(), invalid_runtime).invoke(
        initialize_state(spec)
    )
    early_stop_result = build_graph(
        StopInvestigator(),
        {"log_path": LOG_DIR / "positive_ru_error.txt", "knowledge_base": KNOWLEDGE_BASE, "max_investigation_rounds": 1},
    ).invoke(initialize_state(spec))
    streaming_path = [
        next(iter(update.keys()))
        for update in build_graph(
            StopInvestigator(),
            {"log_path": LOG_DIR / "positive_ru_error.txt", "knowledge_base": KNOWLEDGE_BASE, "max_investigation_rounds": 1},
        ).stream(initialize_state(spec), stream_mode="updates")
    ]
    return [
        {"scenario": "testspec_knowledge_conflict", "passed": conflict_result == "RETEST"},
        {"scenario": "invalid_input_missing_log", "passed": invalid_result["triage_res"] == "RETEST"},
        {"scenario": "evidence_deduplication", "passed": len(duplicate) == 1},
        {"scenario": "unknown_vs_absent", "passed": unknown_is_insufficient and absent_is_distinct},
        {"scenario": "tool_result_single_consumption", "passed": len(same_tool) == 1},
        {"scenario": "investigator_early_stop", "passed": early_stop_result["triage_res"] == "RETEST"},
        {"scenario": "graph_streaming_path", "passed": streaming_path[-1] == "make_output"},
    ]


def _real_model() -> ChatDeepSeek:
    return ChatDeepSeek(model=os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash"))


def _run_case(case: GeneratedCase, output_model: Any = None) -> Dict[str, Any]:
    runtime: RuntimeContext = {
        "log_path": LOG_DIR / f"{case.name}.txt",
        "knowledge_base": KNOWLEDGE_BASE,
        "max_investigation_rounds": 5,
    }
    model = _real_model()
    result = build_graph(model, runtime, output_model=output_model or model).invoke(
        initialize_state(TestSpec(fault=case.fault, expected_action=case.expected_action))
    )
    tool_calls: List[Dict[str, Any]] = []
    for message in result["messages"]:
        for call in getattr(message, "tool_calls", []):
            tool_calls.append({"name": call["name"], "args": call["args"]})
    return {
        "scenario": case.name,
        "expected": case.expected_category,
        "actual": result["triage_res"],
        "passed": result["triage_res"] == case.expected_category,
        "investigation_rounds": result["investigation_rounds"],
        "tool_calls": tool_calls,
        "evidence": [item.model_dump() for item in result["evidence"]],
        "reason": result["reason"],
        "friendly_content": result["friendly_content"],
    }


def run_report() -> Dict[str, Any]:
    cases = generate_positive_cases() + generate_negative_cases()
    results = [_run_case(case) for case in cases]

    timeout_case = generate_positive_cases()[0]
    timeout_result = _run_case(timeout_case, output_model=TimeoutOutputModel())
    timeout_result.update({
        "scenario": "simulated_llm_timeout",
        "expected_fallback": True,
        "fallback_used": timeout_result["friendly_content"] == (
            f"{timeout_result['actual']}：{timeout_result['reason']}"
        ),
    })
    supplemental = _supplemental_checks()
    report = {
        "model": os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash"),
        "call_method": "ChatDeepSeek.invoke",
        "full_chain_cases": results,
        "timeout_case": timeout_result,
        "supplemental_tests": supplemental,
        "summary": {
            "full_chain_passed": all(item["passed"] for item in results),
            "full_chain_count": len(results),
            "timeout_fallback_passed": timeout_result["fallback_used"],
            "supplemental_passed": all(item["passed"] for item in supplemental),
        },
    }
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


class TestTask02FullChain(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = run_report()

    def test_all_existing_logs(self) -> None:
        self.assertTrue(self.report["summary"]["full_chain_passed"])
        self.assertEqual(self.report["summary"]["full_chain_count"], 10)

    def test_timeout_fallback(self) -> None:
        self.assertTrue(self.report["summary"]["timeout_fallback_passed"])

    def test_supplemental_requirements(self) -> None:
        self.assertTrue(self.report["summary"]["supplemental_passed"])


if __name__ == "__main__":
    unittest.main()
