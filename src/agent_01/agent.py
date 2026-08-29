from typing import Dict, Literal, TypedDict

from langgraph.graph import END, START, StateGraph


TriageResult = Literal["PASS", "FAIL", "RETEST"]


class Spec(TypedDict):
    fault: str
    expected: str


class Obs(TypedDict):
    complete: bool
    fault: str
    actual: str


class Sample(TypedDict):
    spec: Spec
    obs: Obs


Input = Sample


class State(TypedDict):
    sample: Sample
    valid: bool
    triage_res: TriageResult
    reason: str
    friendly_content: str


class Output(TypedDict):
    triage_res: TriageResult
    reason: str
    friendly_content: str


def validate_input(state: State) -> Dict[str, object]:
    sample = state.get("sample")
    if not isinstance(sample, dict):
        return {
            "valid": False,
            "triage_res": "RETEST",
            "reason": "缺少字段: sample",
        }

    spec = sample.get("spec")
    if not isinstance(spec, dict):
        return {
            "valid": False,
            "triage_res": "RETEST",
            "reason": "缺少字段: sample.spec",
        }

    obs = sample.get("obs")
    if not isinstance(obs, dict):
        return {
            "valid": False,
            "triage_res": "RETEST",
            "reason": "缺少字段: sample.obs",
        }

    for field in ("fault", "expected"):
        value = spec.get(field)
        if not isinstance(value, str):
            return {
                "valid": False,
                "triage_res": "RETEST",
                "reason": f"字段类型错误: sample.spec.{field} 应为 str",
            }
        if not value.strip():
            return {
                "valid": False,
                "triage_res": "RETEST",
                "reason": f"必要字段为空: sample.spec.{field}",
            }

    complete = obs.get("complete")
    if not isinstance(complete, bool):
        return {
            "valid": False,
            "triage_res": "RETEST",
            "reason": "字段类型错误: sample.obs.complete 应为 bool",
        }

    for field in ("fault", "actual"):
        value = obs.get(field)
        if not isinstance(value, str):
            return {
                "valid": False,
                "triage_res": "RETEST",
                "reason": f"字段类型错误: sample.obs.{field} 应为 str",
            }
        if not value.strip():
            return {
                "valid": False,
                "triage_res": "RETEST",
                "reason": f"必要字段为空: sample.obs.{field}",
            }

    if not complete:
        return {
            "valid": False,
            "triage_res": "RETEST",
            "reason": "测试数据不完整: sample.obs.complete 为 False",
        }

    return {"valid": True}


def triage(state: State) -> Dict[str, object]:
    spec = state["sample"]["spec"]
    obs = state["sample"]["obs"]

    if spec["fault"] != obs["fault"]:
        return {
            "triage_res": "RETEST",
            "reason": (
                f"故障注入不一致：设计故障为 {spec['fault']}，"
                f"实际故障为 {obs['fault']}"
            ),
        }

    if spec["expected"] == obs["actual"]:
        return {
            "triage_res": "PASS",
            "reason": (
                f"故障 {spec['fault']} 注入正确，预期行为 {spec['expected']} "
                f"与实际行为 {obs['actual']} 一致"
            ),
        }

    return {
        "triage_res": "FAIL",
        "reason": (
            f"故障 {spec['fault']} 的预期行为是 {spec['expected']}，"
            f"与实际行为 {obs['actual']} 不一致"
        ),
    }


def make_output(state: State) -> Dict[str, object]:
    triage_res = state["triage_res"]
    reason = state["reason"]
    fallback = f"{triage_res}：{reason}"

    system_prompt = (
        "你是自动驾驶测试结果说明助手。"
        "你的唯一任务是根据输入的 Triage 结果和确定性判定原因，"
        "生成一段简洁、清晰、自然的中文用户可读描述。"
        "只能生成 friendly_content，不得修改、推断或质疑 triage_res 和 reason，"
        "不得执行新的测试判断，不得输出 JSON、Markdown、字段名或解释过程，"
        "只输出最终的中文描述文本。"
    )
    user_prompt = (
        "请根据以下确定性的测试结果生成用户可读的自然语言描述。\n\n"
        f"Triage 结果：{triage_res}\n"
        f"判定原因：{reason}\n\n"
        "请先明确说明测试结果，再清晰描述判定原因，"
        "并只返回 friendly_content 文本。"
    )

    try:
        from langchain_deepseek import ChatDeepSeek

        model = ChatDeepSeek(model="deepseek-v4-flash")
        response = model.invoke(
            [
                ("system", system_prompt),
                ("human", user_prompt),
            ]
        )
        friendly_content = response.content
        if not isinstance(friendly_content, str) or not friendly_content.strip():
            friendly_content = fallback
    except Exception as exc:
        print(f"LLM 调用失败: {exc}")
        friendly_content = fallback

    return {"friendly_content": friendly_content}


def route_after_validation(state: State) -> Literal["triage", "make_output"]:
    if state["valid"]:
        return "triage"
    return "make_output"


def build_graph():
    builder = StateGraph(State)
    builder.add_node("validate_input", validate_input)
    builder.add_node("triage", triage)
    builder.add_node("make_output", make_output)

    builder.add_edge(START, "validate_input")
    builder.add_conditional_edges(
        "validate_input",
        route_after_validation,
        {"triage": "triage", "make_output": "make_output"},
    )
    builder.add_edge("triage", "make_output")
    builder.add_edge("make_output", END)

    return builder.compile()


graph = build_graph()


def initialize_state(input_data: Input) -> State:
    return {
        "sample": input_data,
        "valid": False,
        "triage_res": "RETEST",
        "reason": "",
        "friendly_content": "",
    }


def run(input_data: Input) -> Output:
    state = graph.invoke(initialize_state(input_data))
    return {
        "triage_res": state["triage_res"],
        "reason": state["reason"],
        "friendly_content": state["friendly_content"],
    }
