"""Data contracts for TASK 02.

This module deliberately contains no investigation or triage business logic.
"""

from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Set, TypedDict

from langgraph.graph import MessagesState
from pydantic import BaseModel, Field
from typing_extensions import Annotated


TriageResult = Literal["PASS", "FAIL", "RETEST"]
EvidenceType = Literal["EXPECTATION", "OBSERVATION", "KNOWLEDGE"]
EvidenceSource = Literal["test_spec", "log", "knowledge_base"]


class TestSpec(BaseModel):
    fault: str = Field(min_length=1)
    expected_action: str = Field(min_length=1)


class Evidence(BaseModel):
    id: str
    type: EvidenceType
    source: EvidenceSource
    key: str
    value: str
    present: bool
    timestamp: Optional[str] = None
    raw_ref: Optional[str] = None
    tool_call_id: Optional[str] = None


class RuntimeContext(TypedDict):
    log_path: Path
    knowledge_base: Dict[str, Dict[str, str]]
    max_investigation_rounds: int


def parse_test_spec(raw: Any) -> TestSpec:
    if isinstance(raw, TestSpec):
        data = raw.model_dump()
    elif isinstance(raw, dict):
        data = raw
    else:
        raise ValueError("TestSpec must be an object")
    if not isinstance(data.get("fault"), str) or not data["fault"].strip():
        raise ValueError("fault must be a non-empty string")
    if not isinstance(data.get("expected_action"), str) or not data["expected_action"].strip():
        raise ValueError("expected_action must be a non-empty string")
    return TestSpec(fault=data["fault"].strip(), expected_action=data["expected_action"].strip())


def evidence_state_reducer(existing: List[Evidence], updates: List[Evidence]) -> List[Evidence]:
    """Append Evidence while preserving the first item for each stable ID."""
    result = list(existing)
    known = {item.id for item in result}
    for item in updates:
        if item.id not in known:
            result.append(item)
            known.add(item.id)
    return result


class AgentState(MessagesState):
    raw_input: Any
    test_spec: Optional[TestSpec]
    evidence: Annotated[List[Evidence], evidence_state_reducer]
    processed_tool_call_ids: Set[str]
    investigation_rounds: int
    triage_res: Optional[TriageResult]
    reason: str
    friendly_content: str


class QueryLogsInput(BaseModel):
    keyword: str = Field(min_length=1)


class LogMatch(BaseModel):
    timestamp: str
    raw: str


class QueryLogsOutput(BaseModel):
    query: str
    matches: List[LogMatch]


class LookupKnowledgeInput(BaseModel):
    fault: str = Field(min_length=1)


class LookupKnowledgeOutput(BaseModel):
    fault: str
    expected_action: Optional[str]
