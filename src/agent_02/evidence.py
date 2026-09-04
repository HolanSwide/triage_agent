"""Deterministic Tool Result to Evidence conversion and deduplication."""

import hashlib
import json
import re
from typing import Any, Iterable, List

from .models import Evidence, TestSpec


def evidence_id(evidence: Evidence) -> str:
    payload = evidence.model_dump(exclude={"id", "tool_call_id"})
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def with_stable_id(evidence: Evidence) -> Evidence:
    return evidence.model_copy(update={"id": evidence_id(evidence)})


def evidence_reducer(existing: List[Evidence], updates: Iterable[Evidence]) -> List[Evidence]:
    result = list(existing)
    known = {item.id for item in result}
    for item in updates:
        normalized = with_stable_id(item)
        if normalized.id not in known:
            result.append(normalized)
            known.add(normalized.id)
    return result


def expectation_to_evidence(spec: TestSpec) -> List[Evidence]:
    return [with_stable_id(Evidence(id="", type="EXPECTATION", source="test_spec",
                                     key="expected_action", value=spec.expected_action,
                                     present=True))]


def query_logs_to_evidence(result: Any, tool_call_id: str, spec: TestSpec) -> List[Evidence]:
    matches = result["matches"]
    if not matches:
        query = result["query"]
        if query == spec.fault:
            return [Evidence(id="", type="OBSERVATION", source="log", key="fault", value=spec.fault,
                             present=False, tool_call_id=tool_call_id)]
        if query == spec.expected_action:
            return [Evidence(id="", type="OBSERVATION", source="log", key="actual_action", value=spec.expected_action,
                             present=False, tool_call_id=tool_call_id)]
        return []
    evidence: List[Evidence] = []
    for match in matches:
        raw = match["raw"]
        fault_match = re.search(r"new fault:\s*([A-Za-z0-9_]+)", raw)
        action_match = re.search(r"publish action\s+([A-Za-z0-9_]+)", raw)
        if fault_match:
            evidence.append(Evidence(id="", type="OBSERVATION", source="log", key="fault",
                                     value=fault_match.group(1), present=True,
                                     timestamp=match["timestamp"], raw_ref=raw,
                                     tool_call_id=tool_call_id))
        if action_match:
            evidence.append(Evidence(id="", type="OBSERVATION", source="log", key="actual_action",
                                     value=action_match.group(1), present=True,
                                     timestamp=match["timestamp"], raw_ref=raw,
                                     tool_call_id=tool_call_id))
    return evidence


def knowledge_to_evidence(result: Any, tool_call_id: str) -> List[Evidence]:
    expected = result.get("expected_action")
    fault = result["fault"]
    return [Evidence(id="", type="KNOWLEDGE", source="knowledge_base", key=fault,
                     value=expected or "", present=expected is not None,
                     tool_call_id=tool_call_id)]
