"""LangGraph investigation loop for TASK 02.

The investigator chooses tool calls; all evidence decisions remain deterministic.
"""

import json
from typing import Any, Dict, Literal

from langchain_core.messages import AIMessage, ToolMessage
from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime
from langgraph.prebuilt import ToolNode

from .evidence import evidence_reducer, expectation_to_evidence, knowledge_to_evidence, query_logs_to_evidence
from .models import AgentState, RuntimeContext, TestSpec, parse_test_spec
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


def build_graph(model: Any, output_model: Any = None):
    tools = make_tools()
    model_with_tools = model.bind_tools(tools)
    tool_node = ToolNode(tools)

    def validate_input(state: AgentState, runtime: Runtime[RuntimeContext]) -> Dict[str, Any]:
        try:
            spec = parse_test_spec(state.get("raw_input"))
        except (TypeError, ValueError, KeyError) as exc:
            return {"triage_res": "RETEST", "reason": f"TestSpec 非法：{exc}"}
        context = runtime.context
        if not context["log_path"].is_file():
            return {"triage_res": "RETEST", "reason": "日志文件不存在"}
        if context["max_investigation_rounds"] <= 0:
            return {"triage_res": "RETEST", "reason": "最大调查轮数必须为正数"}
        return {"test_spec": spec, "evidence": expectation_to_evidence(spec)}

    def investigator(state: AgentState) -> Dict[str, Any]:
        spec = state["test_spec"]
        evidence_text = [item.model_dump() for item in state.get("evidence", [])]
        actions = [
            {"name": message.name, "tool_call_id": message.tool_call_id}
            for message in state["messages"] if isinstance(message, ToolMessage)
        ]
        prompt = (f"调查故障 {spec.fault}。当前 Structured Evidence: {evidence_text}。"
                  f"已执行调查动作摘要: {actions}。不要重复完全相同且已成功的查询。"
                  "只能通过工具补充知识规则、故障日志和实际指令日志；不要给出 Triage 结论。")
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
                updates.extend(query_logs_to_evidence(result, message.tool_call_id, state["test_spec"]))
            elif message.name == "lookup_knowledge":
                updates.extend(knowledge_to_evidence(result, message.tool_call_id))
            processed.add(message.tool_call_id)
        return {
            "evidence": evidence_reducer([], updates),
            "processed_tool_call_ids": processed,
        }

    def triage_node(state: AgentState) -> Dict[str, Any]:
        result, reason = deterministic_triage(state["evidence"], state["test_spec"])
        return {"triage_res": result, "reason": reason}

    def fallback_node(state: AgentState, runtime: Runtime[RuntimeContext]) -> Dict[str, Any]:
        result, reason = guardrail_fallback(
            state["investigation_rounds"], runtime.context["max_investigation_rounds"]
        )
        return {"triage_res": result, "reason": reason}

    def output_node(state: AgentState) -> Dict[str, Any]:
        return {"friendly_content": make_friendly_content(
            state.get("triage_res"), state.get("reason", ""),
            state.get("evidence", []), output_model
        )}

    def route_validation(state: AgentState) -> str:
        return "end" if state.get("triage_res") else "investigator"

    def route_investigator(state: AgentState, runtime: Runtime[RuntimeContext]) -> Literal["tools", "triage", "investigator", "fallback"]:
        last = state["messages"][-1]
        if isinstance(last, AIMessage) and last.tool_calls:
            return "tools"
        return route_evidence(state, runtime)

    def route_evidence(state: AgentState, runtime: Runtime[RuntimeContext]) -> Literal["triage", "investigator", "fallback"]:
        if evidence_sufficiency(state.get("evidence", []), state["test_spec"]):
            return "triage"
        if state.get("investigation_rounds", 0) >= runtime.context["max_investigation_rounds"]:
            return "fallback"
        return "investigator"

    builder = StateGraph(AgentState, context_schema=RuntimeContext)
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


def initialize_state(raw_input: Any) -> AgentState:
    return {
        "messages": [],
        "raw_input": raw_input,
        "test_spec": None,
        "evidence": [],
        "processed_tool_call_ids": set(),
        "investigation_rounds": 0,
        "triage_res": None,
        "reason": "",
        "friendly_content": "",
    }
