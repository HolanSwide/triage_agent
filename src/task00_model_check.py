"""Minimal model capability checks for Task 00.

The script intentionally does not implement any Triage Agent workflow.  It only
checks basic chat, tool calling, and structured output against the configured
DeepSeek-compatible endpoint.
"""

from __future__ import annotations

import argparse
import json
import os
from typing import Any, Literal

from langchain_core.messages import HumanMessage, ToolMessage
from langchain_core.tools import tool
from langchain_deepseek import ChatDeepSeek
from dotenv import load_dotenv
from pydantic import BaseModel, Field


CheckName = Literal["basic", "tool", "structured", "all"]

load_dotenv()


class StructuredResult(BaseModel):
    """Small schema used to check structured output parsing."""

    result: str = Field(description="The result of the check")
    confidence: float = Field(description="Confidence between 0 and 1")


@tool
def get_temperature(city: str) -> str:
    """Return a deterministic fake temperature for a city.

    This is deliberately not a real weather lookup.  It only exercises the
    model -> tool -> model execution path.
    """

    return f"{city}: 22°C (模拟数据)"


def build_model() -> ChatDeepSeek:
    """Build the model from the existing environment configuration."""

    api_key = os.getenv("DEEPSEEK_API_KEY")
    model_name = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")
    base_url = os.getenv("DEEPSEEK_API_BASE", "https://api.deepseek.com")

    if not api_key:
        raise RuntimeError(
            "DEEPSEEK_API_KEY is not set. Source env.sh or configure a local .env file."
        )

    return ChatDeepSeek(
        model=model_name,
        api_key=api_key,
        base_url=base_url,
        temperature=0,
    )


def _message_text(message: Any) -> str:
    """Normalize LangChain message content for the JSON report."""

    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    return json.dumps(content, ensure_ascii=False)


def run_basic_chat(model: ChatDeepSeek) -> dict[str, Any]:
    """Verify that the model returns a normal assistant message."""

    response = model.invoke([HumanMessage(content="请只回复：基础对话调用成功")])
    text = _message_text(response).strip()
    if not text:
        raise RuntimeError("The model returned an empty response.")

    return {"status": "passed", "response": text}


def run_tool_calling(model: ChatDeepSeek) -> dict[str, Any]:
    """Verify model tool selection, tool execution, and follow-up response."""

    messages = [
        HumanMessage(
            content=(
                "请查询北京的温度。必须调用 get_temperature 工具，"
                "拿到工具结果后用一句中文回答。"
            )
        )
    ]
    tool_model = model.bind_tools([get_temperature])
    tool_response = tool_model.invoke(messages)
    tool_calls = getattr(tool_response, "tool_calls", [])

    if not tool_calls:
        raise RuntimeError("The model did not return a tool call.")

    messages.append(tool_response)
    executed_calls: list[dict[str, Any]] = []
    for call in tool_calls:
        if call.get("name") != get_temperature.name:
            raise RuntimeError(f"Unexpected tool selected: {call.get('name')!r}")

        args = call.get("args", {})
        if not isinstance(args, dict) or not isinstance(args.get("city"), str):
            raise RuntimeError(f"Invalid tool arguments: {args!r}")

        result = get_temperature.invoke(args)
        messages.append(
            ToolMessage(
                content=str(result),
                tool_call_id=call.get("id", "task00-tool-call"),
            )
        )
        executed_calls.append({"name": call["name"], "args": args, "result": result})

    final_response = model.invoke(messages)
    final_text = _message_text(final_response).strip()
    if not final_text:
        raise RuntimeError("The model returned no final response after tool execution.")

    return {
        "status": "passed",
        "tool_calls": executed_calls,
        "final_response": final_text,
    }


def run_structured_output(model: ChatDeepSeek) -> dict[str, Any]:
    """Verify JSON-mode structured output and Pydantic parsing.

    The configured model rejects LangChain's function-calling structured-output
    request while thinking mode is enabled, so JSON mode is tested as the
    compatible alternative for this task.
    """

    structured_model = model.with_structured_output(
        StructuredResult,
        method="json_mode",
        include_raw=True,
    )
    raw_result = structured_model.invoke(
        [
            HumanMessage(
                content=(
                    "请严格返回 JSON 结构化结果：result 填‘结构化输出调用成功’，"
                    "confidence 填 0 到 1 之间的数字。"
                )
            )
        ]
    )

    parsed = raw_result.get("parsed") if isinstance(raw_result, dict) else None
    parsing_error = raw_result.get("parsing_error") if isinstance(raw_result, dict) else None
    if parsing_error is not None:
        raise RuntimeError(f"Structured output parsing failed: {parsing_error}")
    if not isinstance(parsed, StructuredResult):
        raise RuntimeError(f"Unexpected structured output: {raw_result!r}")
    if not 0 <= parsed.confidence <= 1:
        raise RuntimeError(f"confidence is outside [0, 1]: {parsed.confidence}")

    return {"status": "passed", "parsed": parsed.model_dump()}


def run_checks(check: CheckName) -> dict[str, Any]:
    """Run one check or all checks and return a machine-readable report."""

    model = build_model()
    results: dict[str, Any] = {
        "model": os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash"),
        "base_url": os.getenv("DEEPSEEK_API_BASE", "https://api.deepseek.com"),
        "checks": {},
    }
    runners = {
        "basic": run_basic_chat,
        "tool": run_tool_calling,
        "structured": run_structured_output,
    }
    selected = runners.keys() if check == "all" else [check]
    for name in selected:
        try:
            results["checks"][name] = runners[name](model)
        except Exception as exc:  # noqa: BLE001 - report each external check clearly.
            results["checks"][name] = {"status": "failed", "error": str(exc)}

    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "check",
        nargs="?",
        choices=("basic", "tool", "structured", "all"),
        default="all",
        help="Capability check to run (default: all).",
    )
    args = parser.parse_args()

    try:
        report = run_checks(args.check)
    except Exception as exc:  # noqa: BLE001 - CLI should show configuration errors.
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if all(item.get("status") == "passed" for item in report["checks"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
