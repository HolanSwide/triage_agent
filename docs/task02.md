# TASK 02 — Evidence-Based Agentic Triage

## 1. 背景

在 TASK 01 中，系统已经实现了一个完全确定性的 Test Triage Workflow：

* 输入测试用例设计与结构化观测结果；
* 校验输入；
* 根据固定规则输出：

  * `PASS`
  * `FAIL`
  * `RETEST`
* 最终由 LLM 将确定性结果转换为自然语言输出。

TASK 02 在此基础上增加 **Agentic Investigation Loop**。

与 TASK 01 不同，系统不再直接获得完整的结构化观测结果，而是获得：

1. 测试用例说明；
2. 一份完整测试窗口内的日志文件；
3. 一个简单的知识库。

Agent 需要主动决定如何调用工具，从日志和知识库中逐步收集证据，再由确定性代码根据证据完成最终 Triage。

---

# 2. 目标

实现一个 **Evidence-Based Test Triage Agent**：

```text
TestSpec + Log File + Knowledge Base
                ↓
        Agent investigates
                ↓
          Structured Evidence
                ↓
       Deterministic Triage
                ↓
       PASS / FAIL / RETEST
                ↓
        Friendly Output
```

核心原则：

> LLM 决定如何调查。

> Tool 负责提供原始事实。

> 代码负责固化 Evidence、判断 Evidence 是否充分以及执行最终 Triage。

> 没有充分 Evidence，不得给出正常的确定性 Triage 结论。

---

# 3. 输入

## 3.1 TestSpec

至少包含：

```python
fault: str
expected_action: str
```

示例：

```json
{
  "fault": "RU_ERROR",
  "expected_action": "PULL_OVER"
}
```

---

## 3.2 Log File

一次运行对应一个完整测试窗口的日志文件。

日志采用简化、规则化格式，例如：

```text
10:24:01 /ru ERROR:FAULT=RU_ERROR
10:24:02 /mu CONTROL:ACTION=PULL_OVER
```

日志中允许存在少量与当前测试无关的干扰内容，例如其他模块日志或其他故障信息。

TASK 02 不要求解决复杂的多故障事件关联问题。

默认假设：

* 当前日志文件覆盖完整测试窗口；
* 目标事件如果存在，可以通过规范化关键词查询到；
* 对规范化日志进行完整查询后返回空结果，可视为该目标事件不存在的有效负证据。

日志文件路径属于单次运行的固定依赖，不应要求 LLM 自己生成或猜测。

---

## 3.3 Knowledge Base

使用简单的内存知识库即可，例如：

```python
{
    "RU_ERROR": {
        "expected_action": "PULL_OVER"
    },
    "SENSOR_ERROR": {
        "expected_action": "SAFE_STOP"
    }
}
```

知识库对象属于单次运行的固定依赖。

---

# 4. Tools

系统至少提供以下两个 Tool。

## 4.1 `query_logs`

职责：

> 在当前测试日志中查询符合条件的日志。

至少支持：

```python
keyword: str
```

可选支持时间范围参数。

日志文件路径不得作为要求 LLM 提供的 Tool 参数，应由运行环境提供。

Tool 返回原始查询结果，而不是直接返回 `Evidence` 或 Triage 结论。

示例：

```json
{
  "query": "RU_ERROR",
  "matches": [
    {
      "timestamp": "10:24:01",
      "raw": "10:24:01 /ru ERROR:FAULT=RU_ERROR"
    }
  ]
}
```

当没有匹配结果时：

```json
{
  "query": "PULL_OVER",
  "matches": []
}
```

---

## 4.2 `lookup_knowledge`

职责：

> 根据故障查询知识库中的规范行为。

例如：

```python
lookup_knowledge("RU_ERROR")
```

返回：

```json
{
  "fault": "RU_ERROR",
  "expected_action": "PULL_OVER"
}
```

Tool 负责访问知识库，但知识库对象本身不应作为 LLM Tool 参数。

---

# 5. Investigator

实现一个由 LLM 驱动的 `investigator`。

Investigator 的职责只有：

> 根据 TestSpec 和当前已经掌握的 Evidence，决定下一步是否需要调查，以及调用哪个 Tool、查询什么内容。

Investigator 应知道当前 Triage 至少需要确认：

1. Knowledge Evidence

   * 当前 `fault` 根据知识规则应对应什么行为；

2. Fault Observation

   * 当前目标故障是否实际出现在日志中；

3. Action Observation

   * TestSpec 中的预期行为是否实际出现在日志中。

Investigator 不负责：

* 判断 PASS；
* 判断 FAIL；
* 判断 RETEST；
* 修改已有 Evidence；
* 根据自然语言直接生成最终业务结论。

必须区分：

```text
尚未查询
```

和：

```text
已经查询但没有找到
```

二者语义不同。

Investigator 可以认为 Evidence 已经足够并停止产生 Tool Call，但最终是否真的足够必须由确定性代码再次检查。

---

# 6. Evidence

所有用于最终 Triage 的事实必须首先转换为结构化 Evidence。

建议结构至少包含：

```python
class Evidence(BaseModel):
    id: str

    type: Literal[
        "EXPECTATION",
        "OBSERVATION",
        "KNOWLEDGE",
    ]

    source: Literal[
        "test_spec",
        "log",
        "knowledge_base",
    ]

    key: str
    value: str

    present: bool

    timestamp: str | None
    raw_ref: str | None
    tool_call_id: str | None
```

其中：

### `present=True`

表示：

> 已明确观察到该事实。

例如：

```text
key = actual_action
value = PULL_OVER
present = True
```

---

### `present=False`

表示：

> 已经执行了足够可靠的查询，并明确没有找到该事件。

例如：

```text
key = actual_action
value = PULL_OVER
present = False
```

---

### 没有对应 Evidence

表示：

> 尚未调查清楚，状态仍为 UNKNOWN。

UNKNOWN 不等于 `present=False`。

---

# 7. Evidence ID 与更新规则

Evidence 应使用稳定 ID。

不要使用：

* UUID；
* 当前 Tool 调用次数；
* 随机 ID。

推荐根据 Evidence 本身的稳定字段生成 SHA256 fingerprint，例如综合：

```text
type
source
key
value
present
timestamp
raw_ref
```

Evidence State 应满足：

> append-only + 按 Evidence ID 去重。

同一事实被多个 Tool Call 重复获得时，只保留一份 Evidence。

不同时间、不同内容或不同事实应作为不同 Evidence 共存，不通过覆盖旧 Evidence 的方式更新。

---

# 8. Tool Result → Evidence

Tool 的原始输出不得直接作为最终业务 Evidence 使用。

需要存在一个确定性的 Evidence 收集阶段：

```text
Tool Result
    ↓
collect_evidence
    ↓
Structured Evidence
```

`collect_evidence` 必须使用代码完成。

TASK 02 不允许使用额外 LLM 将 Tool Result 转换成 Evidence。

系统还应避免重复处理相同的 Tool Result。

可利用 Tool Call ID 区分某次 Tool 调用是否已经被 `collect_evidence` 消费。

需要区分：

```text
tool_call_id
→ 标识一次调查动作
```

和：

```text
Evidence.id
→ 标识一条事实
```

---

# 9. Evidence Sufficiency

Evidence 是否充分必须由确定性代码判断。

不要让 LLM 决定最终 Evidence Sufficiency。

至少需要支持以下语义。

---

## 9.1 Knowledge 尚未查询清楚

```text
Knowledge = UNKNOWN
```

Evidence 不充分。

继续调查。

---

## 9.2 TestSpec 与 Knowledge 冲突

例如：

```text
TestSpec:
RU_ERROR → PULL_OVER

Knowledge:
RU_ERROR → SAFE_STOP
```

此时 Evidence 已经足以进行 Triage。

---

## 9.3 Fault 尚未查询

没有目标故障相关 Observation：

```text
Fault = UNKNOWN
```

Evidence 不充分。

继续调查。

---

## 9.4 目标故障明确不存在

例如已执行有效查询：

```text
RU_ERROR
present = False
```

Evidence 已经足以进行 Triage。

---

## 9.5 目标故障存在，但行为尚未查询

```text
fault = PRESENT
action = UNKNOWN
```

Evidence 不充分。

继续调查。

---

## 9.6 目标行为存在或明确不存在

```text
fault = PRESENT
action = PRESENT
```

或：

```text
fault = PRESENT
action = ABSENT
```

Evidence 已经充分。

---

# 10. Deterministic Triage Rules

最终 `triage` 必须完全由代码执行。

不得由 LLM 输出或修改 `triage_res`。

规则至少如下。

---

## RETEST — 测试设计问题

如果：

```text
TestSpec expected_action
!=
Knowledge expected_action
```

则：

```text
RETEST
```

---

## RETEST — 故障注入失败

如果经过有效查询确认：

```text
target fault
present = False
```

则：

```text
RETEST
```

---

## PASS

如果：

```text
Knowledge 与 TestSpec 一致
+
target fault present = True
+
expected action present = True
```

则：

```text
PASS
```

---

## FAIL

如果：

```text
Knowledge 与 TestSpec 一致
+
target fault present = True
+
expected action present = False
```

则：

```text
FAIL
```

---

`triage` 同时输出一个确定性的 `reason`。

---

# 11. Investigation Loop Guardrail

Agent 调查必须存在最大轮数限制。

最大调查轮数属于运行配置，不应作为会持续更新的业务 State。

State 只需要记录当前实际调查轮数。

如果：

```text
Evidence 仍然不充分
+
达到最大调查轮数
```

则进入统一的异常保底节点，例如：

```text
guardrail_fallback
```

当前 TASK 02 中该节点只需要处理：

```text
MAX_INVESTIGATION_ROUNDS
```

输出：

```text
triage_res = RETEST
```

并生成明确的系统级 `reason`。

需要区分：

```text
业务 RETEST
→ Evidence 已经充分，由 triage 得出
```

和：

```text
系统保底 RETEST
→ Evidence 不充分，但调查无法继续
```

---

# 12. State 与 Runtime Context

要求清楚地区分：

## State

保存单次 Graph 执行过程中不断变化的数据，例如：

```text
messages
valid
evidence
processed_tool_call_ids
investigation_rounds
triage_res
reason
friendly_content
```

其中 Evidence 应使用 reducer 实现追加和去重语义。

---

## Runtime Context

保存本次运行期间固定的依赖或配置，例如：

```text
log_path
knowledge_base
max_investigation_rounds
```

这些数据不应要求 LLM 自己生成。

---

# 13. Friendly Output

最终自然语言输出可以由 LLM 生成。

输入至少包括：

```text
triage_res
reason
relevant evidence
```

输出：

```text
friendly_content
```

LLM 只能负责表达和总结。

LLM 不得：

* 修改 `triage_res`；
* 推翻确定性 `reason`；
* 生成不存在的 Evidence。

LLM 调用失败时必须提供简单 deterministic fallback。

---

# 14. Graph 行为要求

整体行为应符合：

```text
START
  ↓
validate_input
  ↓
合法输入
  ↓
investigator
  ↓
是否产生 Tool Call？
 /                  \
Yes                  No
 ↓                    ↓
Tool Execution    Evidence Routing
 ↓
collect_evidence
 ↓
Evidence Routing
 /       |         \
充分     可继续       调查耗尽
 ↓        ↓            ↓
triage investigator guardrail_fallback
 ↓                       ↓
 └─────── make_output ───┘
              ↓
             END
```

Evidence Routing 本身不要求实现为独立 Node。

如果它只负责：

* 检查 Evidence；
* 检查调查轮数；
* 决定下一跳；

则应优先考虑作为 routing logic，而不是为了图形结构额外制造无状态 Node。

---

# 15. 实现约束

TASK 02 保持范围克制。

必须包含：

* LangGraph StateGraph；
* LLM Investigator；
* Tool Calling；
* Tool execution；
* `query_logs`；
* `lookup_knowledge`；
* Structured Evidence；
* Evidence reducer / 去重；
* deterministic evidence sufficiency；
* deterministic triage；
* investigation loop；
* max-loop guardrail；
* LLM friendly output + fallback；
* automated tests。

暂时不要加入：

* Checkpoint / Persistence；
* Human-in-the-loop；
* LangSmith Eval；
* RAG / Vector DB；
* MCP；
* Multi-Agent；
* `Send` 并行调查；
* Web UI；
* Database；
* 复杂重试框架；
* 复杂多故障事件关联；
* 与真实公司内部系统、工具或数据格式的耦合。

---

# 16. 测试要求

至少覆盖以下类别。

### PASS

知识规则正确，目标故障成功注入，预期行为存在。

---

### FAIL

知识规则正确，目标故障成功注入，但经过查询明确确认预期行为不存在。

---

### RETEST — Fault Injection

目标故障经过查询确认不存在。

---

### RETEST — TestSpec Invalid

TestSpec 的 expected action 与知识规则冲突。

---

### RETEST — Invalid Input

例如：

* TestSpec 缺字段；
* 字段类型错误；
* 日志文件不存在；
* 输入结构非法。

---

### RETEST — Guardrail

构造 Investigator 无法在规定轮数内补齐 Evidence 的情况，验证：

```text
guardrail_fallback
```

能够结束 Graph。

---

### Evidence Deduplication

重复调用 Tool 获得相同事实时：

```text
Evidence 不应重复追加
```

---

### Negative Evidence

必须验证：

```text
没有查询
```

与：

```text
查询过但 matches=[]
```

具有不同语义。

---

### Tool Result Consumption

同一个 Tool Call 不应被重复转换成 Evidence。

---

# 17. 验收要求

实现完成后必须能够证明：

1. LLM 只决定调查策略，不决定最终 Triage；
2. Agent 能根据已有 Evidence 选择合适的 Tool；
3. Tool Result 能被确定性转换成结构化 Evidence；
4. 重复事实不会导致 Evidence 无限重复；
5. 系统能够区分 UNKNOWN 与 ABSENT；
6. Evidence 不充分时 Agent 会继续调查；
7. Evidence 充分时确定性代码能够输出正确的 PASS / FAIL / RETEST；
8. Investigator 提前停止时，Evidence Routing 能阻止无证据结论；
9. Agent Loop 不会无限执行；
10. LLM 输出失败不会破坏最终 Triage 结果；
11. 所有核心测试能够自动运行并通过。

---

# 18. 交付物

至少提供：

```text
TASK 02 implementation
automated tests
test report
```

测试报告至少说明：

* 测试场景；
* 预期结果；
* 实际结果；
* 是否通过；
* 实际 Agent 调查路径 / Tool Calls；
* 最终 Evidence；
* 最终 Triage 结果。

不得仅使用：

```text
PASS accuracy = 100%
```

之类单一指标证明 Agent 正确。

重点验证的是：

> 调查过程是否合理。

> Evidence 是否正确。

> 最终确定性规则是否正确。

---

# 19. 设计原则

实现过程中优先保持：

```text
Deterministic things stay deterministic.

LLM is used only where uncertainty and dynamic decision-making are actually needed.

Evidence is auditable.

No sufficient evidence, no normal deterministic conclusion.

Keep TASK 02 narrow.
```

在满足上述需求和验收条件的前提下，具体模块拆分、函数组织、文件结构以及实现细节由开发者自行设计。
