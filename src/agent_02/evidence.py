"""Deterministic Tool Result to Evidence conversion and deduplication."""

import hashlib
import json
from typing import Any, Iterable, List

from .models import Evidence


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


def query_logs_to_evidence(result: Any, tool_call_id: str) -> List[Evidence]:
    query = result["query"]
    matches = result["matches"]
    if not matches:
        return [Evidence(id="", type="OBSERVATION", source="log", key=query, value=query,
                         present=False, tool_call_id=tool_call_id)]
    return [Evidence(id="", type="OBSERVATION", source="log", key=query, value=query,
                     present=True, timestamp=match["timestamp"], raw_ref=match["raw"],
                     tool_call_id=tool_call_id) for match in matches]


def knowledge_to_evidence(result: Any, tool_call_id: str) -> List[Evidence]:
    expected = result.get("expected_action")
    fault = result["fault"]
    return [Evidence(id="", type="KNOWLEDGE", source="knowledge_base", key=fault,
                     value=expected or "", present=expected is not None,
                     tool_call_id=tool_call_id)]
