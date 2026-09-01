"""Final user-facing output with deterministic fallback."""

from typing import Any, List, Optional

from .models import Evidence, TriageResult


def fallback_content(triage_res: Optional[TriageResult], reason: str) -> str:
    return f"{triage_res or 'RETEST'}：{reason}"


def make_friendly_content(triage_res: Optional[TriageResult], reason: str,
                          evidence: List[Evidence], model: Any = None) -> str:
    fallback = fallback_content(triage_res, reason)
    if model is None:
        return fallback
    prompt = (
        "你是自动驾驶测试结果说明助手。只能根据给定的确定性结果生成简洁中文说明。"
        "不得修改 triage_res、reason，不得添加不存在的事实，只返回自然语言文本。\n"
        f"triage_res: {triage_res}\nreason: {reason}\n"
        f"evidence: {[item.model_dump() for item in evidence]}"
    )
    try:
        response = model.invoke(prompt)
        content = response.content if hasattr(response, "content") else response
        return content.strip() if isinstance(content, str) and content.strip() else fallback
    except Exception:
        return fallback
