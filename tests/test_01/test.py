import json
import random
import sys
import types
import unittest
from pathlib import Path
from typing import Dict, List

from src.agent_01.agent import graph, initialize_state, run


REPORT_PATH = Path(__file__).with_name("test_report.json")
RANDOM_SEED = 20260830
FAULTS = ["RU_ERROR", "SENSOR_ERROR", "PLANNING_ERROR"]
BEHAVIORS = ["PULL_OVER", "PULL_UP", "EMERGENCY_STOP"]


def _valid_sample(fault: str, expected: str, actual: str) -> dict:
    return {
        "spec": {"fault": fault, "expected": expected},
        "obs": {"complete": True, "fault": fault, "actual": actual},
    }


def build_test_cases() -> List[Dict[str, object]]:
    rng = random.Random(RANDOM_SEED)
    cases = []

    for index in range(10):
        fault = rng.choice(FAULTS)
        behavior = rng.choice(BEHAVIORS)
        cases.append(
            {
                "name": f"pass_case_{index + 1:02d}",
                "input": _valid_sample(fault, behavior, behavior),
                "expected_result": "PASS",
            }
        )

    for index in range(5):
        fault = rng.choice(FAULTS)
        expected = rng.choice(BEHAVIORS)
        actual = rng.choice([behavior for behavior in BEHAVIORS if behavior != expected])
        cases.append(
            {
                "name": f"fail_case_{index + 1:02d}",
                "input": _valid_sample(fault, expected, actual),
                "expected_result": "FAIL",
            }
        )

    for index in range(5):
        fault = rng.choice(FAULTS)
        expected = rng.choice(BEHAVIORS)
        sample = _valid_sample(fault, expected, expected)
        if index == 0:
            sample["obs"]["complete"] = False
        elif index == 1:
            wrong_fault = rng.choice([item for item in FAULTS if item != fault])
            sample["obs"]["fault"] = wrong_fault
        elif index == 2:
            del sample["obs"]["actual"]
        elif index == 3:
            sample["obs"]["actual"] = ""
        else:
            sample["obs"]["complete"] = "True"
        cases.append(
            {
                "name": f"retest_case_{index + 1:02d}",
                "input": sample,
                "expected_result": "RETEST",
            }
        )

    rng.shuffle(cases)
    return cases


def collect_stream(input_data: dict) -> dict:
    events = list(graph.stream(initialize_state(input_data), stream_mode="updates"))
    path = [node_name for event in events for node_name in event]
    return {"events": events, "path": path}


class FakeResponse:
    content = "测试结果描述（测试替代响应）。"


class FakeChatDeepSeek:
    def __init__(self, model: str) -> None:
        if model != "deepseek-v4-flash":
            raise ValueError("unexpected model")

    def invoke(self, messages: list) -> FakeResponse:
        return FakeResponse()


def _use_fake_llm() -> object:
    previous = sys.modules.get("langchain_deepseek")
    fake_module = types.ModuleType("langchain_deepseek")
    fake_module.ChatDeepSeek = FakeChatDeepSeek
    sys.modules["langchain_deepseek"] = fake_module
    return previous


def _restore_llm(previous: object) -> None:
    if previous is None:
        sys.modules.pop("langchain_deepseek", None)
    else:
        sys.modules["langchain_deepseek"] = previous


def _binary_label(result: str) -> str:
    return "positive" if result == "PASS" else "negative"


def _classification(expected: str, actual: str) -> str:
    expected_label = _binary_label(expected)
    actual_label = _binary_label(actual)
    if expected_label == "positive" and actual_label == "positive":
        return "TP"
    if expected_label == "positive" and actual_label == "negative":
        return "FN"
    if expected_label == "negative" and actual_label == "negative":
        return "TN"
    return "FP"


def _ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def summarize_results(case_results: List[Dict[str, object]]) -> dict:
    matrix = {"tp": 0, "fn": 0, "tn": 0, "fp": 0}
    path_statistics = {}

    for case in case_results:
        classification = case["classification"].lower()
        matrix[classification] += 1
        path = "->".join(case["path"])
        path_statistics[path] = path_statistics.get(path, 0) + 1

    tp, fn, tn, fp = matrix["tp"], matrix["fn"], matrix["tn"], matrix["fp"]
    total = tp + fn + tn + fp
    precision = _ratio(tp, tp + fp)
    recall = _ratio(tp, tp + fn)
    metrics = {
        "accuracy": _ratio(tp + tn, total),
        "precision": precision,
        "recall": recall,
        "specificity": _ratio(tn, tn + fp),
        "f1": _ratio(2 * precision * recall, precision + recall),
    }
    return {
        "confusion_matrix": matrix,
        "metrics": metrics,
        "path_statistics": path_statistics,
    }


def generate_report() -> dict:
    case_results = []
    real_llm_results = set()
    for case in build_test_cases():
        input_data = case["input"]
        expected_result = case["expected_result"]
        use_real_llm = expected_result not in real_llm_results
        previous_llm = None
        if not use_real_llm:
            previous_llm = _use_fake_llm()
        try:
            output = run(input_data)
            stream = collect_stream(input_data)
        finally:
            if not use_real_llm:
                _restore_llm(previous_llm)
        real_llm_results.add(expected_result)
        actual_result = output["triage_res"]
        case_results.append(
            {
                "name": case["name"],
                "input": input_data,
                "expected_result": expected_result,
                "actual_result": actual_result,
                "expected_binary_label": _binary_label(expected_result),
                "actual_binary_label": _binary_label(actual_result),
                "classification": _classification(expected_result, actual_result),
                "path": stream["path"],
                "reason": output["reason"],
                "friendly_content": output["friendly_content"],
            }
        )

    report = {
        "summary": {
            "total": len(case_results),
            "expected_pass": sum(case["expected_result"] == "PASS" for case in case_results),
            "expected_fail": sum(case["expected_result"] == "FAIL" for case in case_results),
            "expected_retest": sum(case["expected_result"] == "RETEST" for case in case_results),
        },
        "binary_mapping": {"positive": "PASS", "negative": ["FAIL", "RETEST"]},
        **summarize_results(case_results),
        "cases": case_results,
    }
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


class Task01Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = generate_report()

    def test_end_to_end_results(self) -> None:
        self.assertEqual(self.report["summary"]["total"], 20)
        self.assertEqual(self.report["summary"]["expected_pass"], 10)
        self.assertEqual(self.report["summary"]["expected_fail"], 5)
        self.assertEqual(self.report["summary"]["expected_retest"], 5)
        self.assertEqual(self.report["confusion_matrix"], {"tp": 10, "fn": 0, "tn": 10, "fp": 0})

        for case in self.report["cases"]:
            self.assertEqual(case["expected_result"], case["actual_result"])
            self.assertTrue(case["reason"])
            self.assertTrue(case["friendly_content"])

    def test_execution_paths(self) -> None:
        for case in self.report["cases"]:
            sample = case["input"]
            obs = sample["obs"]
            invalid_input = (
                not isinstance(obs.get("complete"), bool)
                or obs.get("complete") is False
                or not isinstance(obs.get("actual"), str)
                or not obs.get("actual", "").strip()
            )
            if case["expected_result"] == "RETEST" and invalid_input:
                self.assertEqual(case["path"], ["validate_input", "make_output"])
            else:
                self.assertEqual(case["path"], ["validate_input", "triage", "make_output"])

    def test_report_file(self) -> None:
        self.assertTrue(REPORT_PATH.exists())
        saved_report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
        self.assertEqual(saved_report, self.report)


if __name__ == "__main__":
    unittest.main()
