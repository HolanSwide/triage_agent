# Current Task

## Task 01 — Minimal Test Triage Workflow

### Goal

使用 LangGraph 实现一个最小的自动驾驶测试用例 Triage Workflow。

当前输入已经由上游系统完成结构化处理，本任务不涉及自然语言理解、原始日志解析、知识库查询或 Tool Calling。

系统需要完成：

* 输入合法性与完整性校验
* 故障注入检查
* 预期行为与实际行为比对
* 输出 `PASS / FAIL / RETEST`
* 生成结构化结果和用户可读描述
* 展示 Graph 执行过程中的节点调用与 State 更新

---

## Input

输入类型为 `Sample`：

```text
Sample
├── spec
│   ├── fault: str
│   └── expected: str
│
└── obs
    ├── complete: bool
    ├── fault: str
    └── actual: str
```

字段含义：

* `spec.fault`：测试设计要求注入的故障
* `spec.expected`：故障发生后期望出现的行为
* `obs.complete`：测试数据是否完整
* `obs.fault`：实际注入的故障
* `obs.actual`：实际观测到的行为

---

## Output

最终输出：

```text
Output
├── triage_res: PASS | FAIL | RETEST
├── reason: str
└── friendly_content: str
```

其中：

* `triage_res`：最终 Triage 结果
* `reason`：确定性的判定原因
* `friendly_content`：根据结果生成的用户可读描述

`friendly_content` 当前使用确定性 Python 逻辑生成，不使用 LLM。

---

## Business Rules

按照以下规则进行判定。

### RETEST

满足任意条件：

* 输入字段缺失
* 必要字段为空
* 输入值不符合预期类型或合法范围
* `obs.complete == False`
* `spec.fault != obs.fault`

### PASS

满足：

```text
输入合法且完整
AND
spec.fault == obs.fault
AND
spec.expected == obs.actual
```

### FAIL

满足：

```text
输入合法且完整
AND
spec.fault == obs.fault
AND
spec.expected != obs.actual
```

---

## Architecture Constraints

使用 LangGraph 实现。

Graph 至少包含：

```text
START
  ↓
validate_input
  ↓
 valid?
 /     \
No      Yes
↓        ↓
make_output ← triage
      ↓
     END
```

### validate_input

职责：

* 检查输入是否合法、完整
* 更新 `valid`
* 非法输入直接设置：

  * `triage_res = RETEST`
  * `reason = 对应原因`

校验完成后根据 `valid` 进行路由。

### triage

只处理合法输入。

职责：

* 检查实际故障是否与设计故障一致
* 比较实际行为与期望行为
* 更新：

  * `triage_res`
  * `reason`

### make_output

职责：

* 根据当前 Triage 结果生成 `friendly_content`
* 不重新执行 Triage 判断

---

## State

内部 State 至少应支持以下信息：

```text
sample
valid
triage_res
reason
friendly_content
```

State 使用 `TypedDict`。

最终输出与内部 State 应保持职责分离，避免为了返回结果重复保存相同数据。

---

## Implementation Constraints

本 Task：

* 必须使用 LangGraph
* 不使用 LLM
* 不使用 Tool Calling
* 不使用 Agentic Loop
* 不使用 RAG
* 不使用 MCP
* 不使用 Checkpoint / Persistence
* 不接入 LangSmith
* 不增加当前任务不需要的抽象或功能
* 不将执行 Trace 手工保存进 State
* 使用 LangGraph streaming 能力展示节点执行过程和 State 更新

实现代码：

```text
src/agent_01/agent.py
```

测试代码：

```text
tests/test_01/test.py
```

如果认为必须新增其他代码文件，请先说明原因。

---

## Required Test Cases

至少实际验证以下情况：

### PASS

* 数据完整
* 故障注入正确
* 实际行为等于预期行为

预期：

```text
PASS
```

### FAIL

* 数据完整
* 故障注入正确
* 实际行为不等于预期行为

预期：

```text
FAIL
```

### RETEST — Wrong Fault

* 实际故障与设计故障不同

预期：

```text
RETEST
```

### RETEST — Incomplete Data

* `obs.complete == False`

预期：

```text
RETEST
```

### RETEST — Invalid Input

至少覆盖：

* 缺失字段
* 空值
* 非法数据类型

预期：

```text
RETEST
```

---

## Acceptance Criteria

任务完成必须满足：

1. Graph 可以正常 compile 和执行。
2. PASS / FAIL / RETEST 核心场景均通过实际测试。
3. 输出包含：

   * `triage_res`
   * `reason`
   * `friendly_content`
4. 可以通过 streaming 查看 Graph 的节点执行和 State update。
5. 代码不存在明显语法或运行时错误。
6. 实现范围没有超出本 Task。
7. 完成后说明：

   * 实现方案
   * Graph 执行流程
   * 修改的文件
   * 实际运行的测试
   * 测试结果
   * 存在的限制

---

## Working Method

开始修改代码前：

1. 阅读 `AGENTS.md`
2. 阅读 `docs/PROJECT_CONTEXT.md`
3. 阅读当前任务文件
4. 检查现有代码

然后先给出简短实施计划。

计划确认合理后再开始实现。
