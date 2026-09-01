"""LangGraph investigation loop for TASK 02.

The investigator chooses tool calls; all evidence decisions remain deterministic.
"""

import json
from typing import Any, Dict, Literal

from langchain_core.messages import AIMessage, ToolMessage
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

from .evidence import evidence_reducer, knowledge_to_evidence, query_logs_to_evidence
from .models import AgentState, RuntimeContext, TestSpec
from .output import make_friendly_content
from .tools import make_tools
from .triage import deterministic_triage, evidence_sufficiency, guardrail_fallback


def _parse_tool_content(content: Any) -> Dict[str, Any]:
    if isinstance(content, dict):
        return content
    if isinstance(content, str):
        parsed = json.loads(content)
        if isinstance(parsed, dict):
            return parsed
    raise ValueError("Tool result must be a JSON object")


def build_graph(model: Any, runtime: RuntimeContext, output_model: Any = None):
    tools = make_tools(runtime)
    model_with_tools = model.bind_tools(tools)
    tool_node = ToolNode(tools)

    def validate_input(state: AgentState) -> Dict[str, Any]:
        spec = state.get("test_spec")
        if not isinstance(spec, TestSpec):
            return {"triage_res": "RETEST", "reason": "TestSpec 类型非法"}
        if not runtime["log_path"].is_file():
            return {"triage_res": "RETEST", "reason": "日志文件不存在"}
        if runtime["max_investigation_rounds"] <= 0:
            return {"triage_res": "RETEST", "reason": "最大调查轮数必须为正数"}
        return {}

    def investigator(state: AgentState) -> Dict[str, Any]:
        spec = state["test_spec"]
        prompt = (
            f"调查故障 {spec.fault}。预期行为是 {spec.expected_action}。"
            "只能通过工具收集知识规则、故障日志和预期指令日志；不要给出 Triage 结论。"
        )
        response = model_with_tools.invoke(state["messages"] + [("human", prompt)])
        return {
            "messages": [response],
            "investigation_rounds": state.get("investigation_rounds", 0) + 1,
        }

    def collect_evidence(state: AgentState) -> Dict[str, Any]:
        updates = []
        processed = set(state.get("processed_tool_call_ids", set()))
        for message in state["messages"]:
            if not isinstance(message, ToolMessage) or message.tool_call_id in processed:
                continue
            result = _parse_tool_content(message.content)
            if message.name == "query_logs":
                updates.extend(query_logs_to_evidence(result, message.tool_call_id))
            elif message.name == "lookup_knowledge":
                updates.extend(knowledge_to_evidence(result, message.tool_call_id))
            processed.add(message.tool_call_id)
        return {
            "evidence": evidence_reducer(state.get("evidence", []), updates),
            "processed_tool_call_ids": processed,
        }

    def triage_node(state: AgentState) -> Dict[str, Any]:
        result, reason = deterministic_triage(state["evidence"], state["test_spec"])
        return {"triage_res": result, "reason": reason}

    def fallback_node(state: AgentState) -> Dict[str, Any]:
        result, reason = guardrail_fallback(
            state["investigation_rounds"], runtime["max_investigation_rounds"]
        )
        return {"triage_res": result, "reason": reason}

    def output_node(state: AgentState) -> Dict[str, Any]:
        return {"friendly_content": make_friendly_content(
            state.get("triage_res"), state.get("reason", ""),
            state.get("evidence", []), output_model
        )}

    def route_validation(state: AgentState) -> str:
        return "end" if state.get("triage_res") else "investigator"

    def route_investigator(state: AgentState) -> Literal["tools", "triage", "investigator", "fallback"]:
        last = state["messages"][-1]
        if isinstance(last, AIMessage) and last.tool_calls:
            return "tools"
        return route_evidence(state)

    def route_evidence(state: AgentState) -> Literal["triage", "investigator", "fallback"]:
        if evidence_sufficiency(state.get("evidence", []), state["test_spec"]):
            return "triage"
        if state.get("investigation_rounds", 0) >= runtime["max_investigation_rounds"]:
            return "fallback"
        return "investigator"

    builder = StateGraph(AgentState)
    builder.add_node("validate_input", validate_input)
    builder.add_node("investigator", investigator)
    builder.add_node("tools", tool_node)
    builder.add_node("collect_evidence", collect_evidence)
    builder.add_node("triage", triage_node)
    builder.add_node("guardrail_fallback", fallback_node)
    builder.add_node("make_output", output_node)
    builder.add_edge(START, "validate_input")
    builder.add_conditional_edges("validate_input", route_validation, {"investigator": "investigator", "end": "make_output"})
    builder.add_conditional_edges("investigator", route_investigator, {"tools": "tools", "triage": "triage", "investigator": "investigator", "fallback": "guardrail_fallback"})
    builder.add_edge("tools", "collect_evidence")
    builder.add_conditional_edges("collect_evidence", route_evidence, {"triage": "triage", "investigator": "investigator", "fallback": "guardrail_fallback"})
    builder.add_edge("triage", "make_output")
    builder.add_edge("guardrail_fallback", "make_output")
    builder.add_edge("make_output", END)
    return builder.compile()


def initialize_state(test_spec: TestSpec) -> AgentState:
    return {
        "messages": [],
        "test_spec": test_spec,
        "evidence": [],
        "processed_tool_call_ids": set(),
        "investigation_rounds": 0,
        "triage_res": None,
        "reason": "",
        "friendly_content": "",
    }
