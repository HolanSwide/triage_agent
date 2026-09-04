"""Concrete log and in-memory knowledge-base tools for TASK 02."""

from pathlib import Path
from typing import Any, Dict, List

from langchain_core.tools import BaseTool, StructuredTool
from langgraph.prebuilt import ToolRuntime

from .models import (
    LookupKnowledgeInput,
    LookupKnowledgeOutput,
    QueryLogsInput,
    QueryLogsOutput,
    RuntimeContext,
)


def _timestamp(raw: str) -> str:
    return raw[:14].strip() if len(raw) >= 14 else ""


def query_logs_impl(keyword: str, runtime: ToolRuntime[RuntimeContext, Any]) -> Dict[str, Any]:
    if not isinstance(keyword, str) or not keyword.strip():
        raise ValueError("keyword must be a non-empty string")
    path = Path(runtime.context["log_path"])
    if not path.is_file():
        raise FileNotFoundError(f"log file does not exist: {path}")
    matches: List[Dict[str, str]] = []
    with path.open("r", encoding="utf-8") as log_file:
        for raw_line in log_file:
            raw = raw_line.rstrip("\r\n")
            if keyword in raw:
                matches.append({"timestamp": _timestamp(raw), "raw": raw})
    return QueryLogsOutput(query=keyword, matches=matches).model_dump()

def lookup_knowledge_impl(fault: str, runtime: ToolRuntime[RuntimeContext, Any]) -> Dict[str, Any]:
    if not isinstance(fault, str) or not fault.strip():
        raise ValueError("fault must be a non-empty string")
    rule = runtime.context["knowledge_base"].get(fault)
    expected_action = rule.get("expected_action") if rule else None
    return LookupKnowledgeOutput(fault=fault, expected_action=expected_action).model_dump()


query_logs = StructuredTool.from_function(
    func=query_logs_impl, name="query_logs",
    description="Query the current TXT test log by keyword and return raw matching records.",
    args_schema=QueryLogsInput,
)
lookup_knowledge = StructuredTool.from_function(
    func=lookup_knowledge_impl, name="lookup_knowledge",
    description="Look up the expected action in the in-memory JSON knowledge base.",
    args_schema=LookupKnowledgeInput,
)


def make_tools() -> List[BaseTool]:
    return [query_logs, lookup_knowledge]
