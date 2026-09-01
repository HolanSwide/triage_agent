# TASK 02 实现方案：Evidence-Based Test Triage Agent

## 一、数据定义

### 1. 输入数据

```python
class TestSpec(BaseModel):
    fault: str
    expected_action: str
```

日志输入是一个 TXT 文件：一次运行对应一个完整测试窗口，文件按行保存日志记录，每行一条记录。例如：

```text
09-01 23:02:10 ERROR /ru: new fault: RU_ERROR, Heartbeat timeout for 3000ms.
```

`query_logs` 按行读取该文件，并从每条匹配记录中提取时间戳和原始日志文本。日志路径由 Runtime Context 提供，不能要求 LLM 生成或猜测。

知识库是直接保存在内存中的 JSON 数据，结构按故障名称索引规范行为：

```json
{
  "RU_ERROR": {
    "expected_action": "PULL_OVER"
  },
  "SENSOR_ERROR": {
    "expected_action": "SAFE_STOP"
  }
}
```

实现中可将该 JSON 对象作为 `dict[str, dict[str, str]]` 传入 Runtime Context；不引入文件数据库、RAG 或向量检索。

运行时固定依赖不放入 LLM Tool 参数，而通过 Runtime Context 注入：

```python
class RuntimeContext:
    log_path: Path
    knowledge_base: dict[str, dict[str, str]]
    max_investigation_rounds: int
```

`log_path` 必须指向单次完整测试窗口日志；知识库至少支持 `fault -> expected_action` 映射。

### 2. 结构化 Evidence

```python
class Evidence(BaseModel):
    id: str
    type: Literal["EXPECTATION", "OBSERVATION", "KNOWLEDGE"]
    source: Literal["test_spec", "log", "knowledge_base"]
    key: str
    value: str
    present: bool
    timestamp: str | None = None
    raw_ref: str | None = None
    tool_call_id: str | None = None
```

规则：

- `present=True` 表示明确观察到事实。
- `present=False` 仅表示已经完成可靠查询且没有找到事实。
- 没有对应 Evidence 表示 `UNKNOWN`。
- `id` 由 Evidence 稳定字段生成 SHA256 fingerprint，不使用 UUID、随机值或调用次数。
- Evidence 使用 append-only reducer，并按 `id` 去重；旧事实不被覆盖。

### 3. Graph State

State 建议包含：

```python
from langgraph.graph import MessagesState


class AgentState(MessagesState):
    test_spec: TestSpec
    evidence: Annotated[list[Evidence], evidence_reducer]
    processed_tool_call_ids: set[str]
    investigation_rounds: int
    triage_res: Literal["PASS", "FAIL", "RETEST"] | None
    reason: str
    friendly_content: str
```

Runtime Context 保存 `log_path`、`knowledge_base` 和 `max_investigation_rounds`；这些值不作为业务 State 持续更新。

### 4. Tool 数据契约

`query_logs(keyword: str)` 在 Runtime Context 指定的 TXT 日志文件中逐行查询，返回：

```python
{"query": keyword, "matches": [{"timestamp": str, "raw": str}]}
```

`lookup_knowledge(fault: str)` 在 Runtime Context 指定的内存 JSON 知识库中查询，返回：

```python
{"fault": fault, "expected_action": str | None}
```

Tool 必须校验输入，直接访问 Runtime Context，不包含 Triage 决策逻辑。

## 二、结构定义

### 1. 文件结构

```text
src/agent_02/
├── __init__.py
├── models.py          # Pydantic 数据模型、State 类型、输出模型
├── tools.py           # query_logs、lookup_knowledge 及结果模型
├── evidence.py        # Tool Result 转 Evidence、fingerprint、reducer
├── triage.py          # Evidence sufficiency 和确定性 Triage
├── graph.py            # LangGraph StateGraph、节点和路由
└── prompts.py          # Investigator 与 friendly output 提示词

tests/
└── test_02/
    ├── test_agent.py
    ├── fixtures.py
    └── test_report.json
```

### 2. Graph 流程

```text
START
  ↓
validate_input
  ↓
investigator
  ↓
有 Tool Call ──→ execute_tools ──→ collect_evidence ──┐
  │                                                   │
无 Tool Call ─────────────────────→ evidence_router ──┤
                                                      │
              ┌──────────────充分──────────────┐       │
              ↓                                ↓       │
            triage                         investigator
              ↓                                ↑       │
              └──────────────→ make_output ←──┘       │
                               ↑                       │
                    达到上限 → guardrail_fallback ────┘
```

推荐节点职责：

- `validate_input`：校验 TestSpec、日志路径和运行配置；非法输入直接设置 `RETEST`。
- `investigator`：仅由 LLM 决定下一步 Tool 调查；不能输出或修改 Triage。
- `execute_tools`：执行 Tool Calls，并保留原始 Tool Message 与调用 ID。
- `collect_evidence`：纯代码消费未处理的 Tool Result，生成并追加 Evidence。
- `evidence_router`：纯代码判断 UNKNOWN、充分性和调查轮数，决定下一跳。
- `triage`：纯代码执行 PASS/FAIL/RETEST 规则并生成确定性 reason。
- `guardrail_fallback`：Evidence 不充分且超过最大轮数时输出系统级 RETEST。
- `make_output`：根据固定 triage 结果、reason 和相关 Evidence 生成自然语言；失败时使用 deterministic fallback。

### 3. 确定性判断

Evidence 至少要覆盖：知识规则、目标故障观察、预期行为观察。

- 知识规则与 TestSpec 冲突：`RETEST`。
- 目标故障已确认不存在：`RETEST`。
- 知识一致、故障存在、预期行为存在：`PASS`。
- 知识一致、故障存在、预期行为不存在：`FAIL`。
- 其他情况：继续调查；达到上限则 `guardrail_fallback`。

### 4. LLM 边界

Investigator 的系统提示词应要求其优先补齐缺失证据，并只能使用声明的 Tool。最终 Triage 不从 LLM 输出读取。`make_output` 的 LLM 只生成 `friendly_content`，不得生成新 Evidence 或改变 verdict/reason。

## 三、开发流程

### 阶段 1：接口和固定数据

1. 确认 `TestSpec`、`Evidence`、State、Runtime Context 和 Output 模型。
2. 定义 Tool 输入/输出契约及错误行为。
3. 准备最小日志 fixture 和知识库 fixture。

### 阶段 2：确定性核心

1. 实现输入校验。
2. 实现日志查询和知识查询。
3. 实现 Tool Result 消费、Evidence fingerprint、append-only 去重 reducer。
4. 实现 Evidence sufficiency、triage 和 guardrail。
5. 先用无 LLM 的单元测试验证上述逻辑。

### 阶段 3：LangGraph Investigator

1. 创建 `StateGraph` 和节点。
2. 绑定两个 Tool，实现 Tool Calling 与循环路由。
3. 验证 Investigator 只决定调查动作，确定性节点掌握最终判定。
4. 限制每轮最多推进一次调查，并使用运行配置控制最大轮数。

### 阶段 4：自然语言输出

1. 将最终固定结果传给 `make_output`。
2. 增加 LLM 异常、空响应和不可用时的 deterministic fallback。
3. 验证 friendly output 不能污染结构化结果。

### 阶段 5：自动化测试与报告

1. 使用 Fake Investigator 覆盖确定性路径，避免大多数测试依赖外部 API。
2. 单独保留必要的真实 LLM 集成验证，并从 `DEEPSEEK_API_KEY` 读取凭证。
3. 测试 Graph streaming/path、Tool Calls、最终 Evidence 和 Triage。
4. 将每个场景的预期结果、实际结果、调查路径、Evidence 和结果写入 `tests/test_02/test_report.json`。
5. 在 `helloagent` 环境执行语法检查和自动化测试。

## 四、验收标准

### 功能验收

- PASS、FAIL、Fault Injection RETEST、TestSpec 冲突 RETEST 均得到正确 verdict。
- 非法输入、日志不存在、知识缺失等情况不会产生无证据的正常结论。
- Investigator 能按缺失 Evidence 选择 `query_logs` 或 `lookup_knowledge`。
- Tool 原始结果能被确定性转换为结构化 Evidence。
- 相同事实和相同 Tool Call 不会被重复消费或重复追加。
- 系统明确区分 UNKNOWN 与查询后的 ABSENT。
- Evidence 足够时直接进入确定性 Triage；不足时继续调查。
- Investigator 提前停止时不会绕过 Evidence 检查。
- 达到最大调查轮数后 Graph 能通过 `guardrail_fallback` 正常结束。
- friendly output 失败时仍保留正确的 `triage_res` 和 `reason`。

### 设计验收

- 使用 LangGraph `StateGraph` 实现循环。
- State 与 Runtime Context 清晰分离。
- Evidence reducer 具备 append-only 和稳定 ID 去重语义。
- LLM 不负责最终 Triage，代码不依赖自然语言猜测业务事实。
- 不引入 Persistence、RAG、MCP、Multi-Agent、数据库、Web UI 或复杂重试框架。

### 测试验收

- 自动化测试覆盖需求中列出的全部场景。
- 测试报告包含场景、预期/实际结果、是否通过、Agent 调查路径、Tool Calls、最终 Evidence 和 Triage。
- 语法检查、单元测试和 Graph 级测试在 `helloagent` 环境可重复运行并通过。
- 不以单一准确率指标作为唯一证明，而以调查过程、Evidence 正确性和确定性判定共同验收。
