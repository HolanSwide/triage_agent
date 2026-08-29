# Project Context

## 1. Project Goal

本项目是一个基于 LangGraph 实现的 **Evidence-Based Test Triage Agent**。

项目有两个目标：

1. 实现一个小而完整、具备实际工程闭环的 Agent Demo。
2. 通过该项目学习 LangGraph，并能够解释项目中的核心设计与实现。

项目强调：

* 功能范围小
* 架构清晰
* 代码可解释
* 具备可靠性机制
* 具备测试与 Eval
* 不追求复杂功能堆叠

---

## 2. Business Scenario

输入一次测试任务的两部分信息：

### Test Spec

包含：

* 测试目标
* 测试步骤
* 注入的故障类型
* 期望结果

### Test Bundle

包含模拟测试过程中产生的数据，例如：

* logs
* topic messages
* vehicle signals
* metadata

Agent 根据 Test Spec 主动查询 Test Bundle 中的证据，并完成 Triage。

---

## 3. Output

最终输出三个可能的 Verdict：

### PASS

测试执行有效，并且实际结果满足预期。

### FAIL

测试执行有效，但实际结果没有满足预期。

### RETEST

当前测试不能被可靠判定，例如：

* 测试步骤执行错误
* 关键数据缺失
* 故障未正确注入
* Evidence 不充分
* 测试数据存在异常

同时必须输出支持 Verdict 的 Evidence 和 Reason。

---

## 4. Core Invariant

本项目最重要的原则：

> No sufficient evidence, no deterministic triage conclusion.

即：

**没有充分 Evidence，就不能给出确定性的 PASS 或 FAIL。**

Agent 不允许仅根据自然语言描述猜测结论。

如果无法获得足够证据，应输出 RETEST 或对应的无法判断状态。

---

## 5. Architecture Principle

整个系统采用：

**Deterministic Workflow + Agentic Loop**

核心原则：

> 能通过确定性代码解决的问题，不交给 LLM。
> 只有真正需要动态判断和决策的问题才交给 Agent。

### Deterministic Workflow

负责：

* 输入校验
* 数据完整性检查
* Tool 参数和执行结果校验
* 最大执行次数
* 异常处理
* 最终输出 Schema 校验
* 明确的 Guardrail

### Agentic Loop

负责：

* 判断当前缺少什么 Evidence
* 决定下一步调查内容
* 选择合适的 Tool
* 生成 Tool 参数
* 根据已有 Evidence 判断是否需要继续调查

---

## 6. Main Execution Flow

整体逻辑：

```text
START
  ↓
Validate Input
  ↓
检查测试数据完整性
  ↓
Investigator Agent
  ↓
选择 Tool
  ↓
Execute Tool
  ↓
收集 / 更新 Evidence
  ↓
Evidence 是否充分？
  ├── No  → 返回 Investigator Agent
  └── Yes → Verdict
                ↓
        PASS / FAIL / RETEST
                ↓
               END
```

具体 Graph 结构允许在开发过程中调整，但必须保持：

**确定性控制逻辑与 LLM 动态决策逻辑分离。**

---

## 7. Initial Tools

第一阶段计划使用少量明确 Tool：

* `get_test_spec`
* `query_logs`
* `query_signal`
* `query_topic`
* `lookup_fault_spec`

Tool 应保持：

* 单一职责
* 明确输入输出
* 可测试
* 不包含 Agent 决策逻辑

具体 Tool 接口可以随着实现逐步确定。

---

## 8. Knowledge

Demo 使用公开、自定义的模拟知识和测试数据。

例如本地故障规则：

```text
camera_disconnect
→ expected behavior: exit autonomous mode within N seconds
```

第一版不引入完整 RAG。

---

## 9. State

LangGraph State 预计包含以下类型的信息：

* Test Spec
* Test Bundle reference
* messages
* collected evidence
* tool history
* current investigation state / hypothesis
* iteration count
* final verdict
* final reason

具体 State Schema 在实现阶段逐步确定。

不要未经讨论提前固定复杂 State 结构。

---

## 10. Reliability Requirements

最终 Demo 应逐步覆盖：

* Tool 输入校验
* Tool 执行异常处理
* Retry
* 最大 Agent 循环次数
* 防止无意义重复 Tool 调用
* Evidence 充分性检查
* Structured Output
* Checkpoint
* Persistence
* Trace / Observability

这些能力应随着学习进度逐步加入，而不是一次性实现。

---

## 11. Evaluation

项目最终需要构建一个小型模拟 Eval Dataset。

Eval 至少包含三个层次：

### Result Evaluation

判断最终 Verdict 是否正确。

### Evidence Evaluation

判断：

* Evidence 是否真实存在于 Tool 返回结果中
* Evidence 是否能够支持最终 Verdict

### Agent Behavior Evaluation

判断：

* Tool 是否选择合理
* 是否发生无意义 Tool 调用
* 是否重复查询
* 是否超过最大步骤
* 是否在 Evidence 不充分时错误地产生确定性结论

---

## 12. Skill Packaging

项目运行主体是：

**Test Triage Agent**

整个能力可以进一步包装为：

**Triage Skill**

Skill 可以包含：

* `SKILL.md`
* LangGraph implementation
* Tools
* Schemas
* Knowledge
* Eval

Skill 是应用层能力封装，不是 LangGraph 原生执行机制。

当前 Demo 不为了展示 Skill 而额外构建 General Agent。

---

## 13. Non-Goals

当前项目暂不实现：

* Multi-Agent
* 完整 RAG
* MCP Server
* 大规模真实车辆数据解析
* 企业内部知识库
* 复杂前端
* 自动修改代码
* 真实生产环境控制
* 深入 LangGraph 源码
* 完整 LangChain 学习

除非后续明确修改项目范围，否则不要主动引入这些能力。

---

## 14. Learning Context

该项目同时是 LangGraph 学习项目。

开发原则：

```text
理解问题
→ 理解机制
→ 最小实现
→ 集成到 Demo
→ 验证边界与异常
→ 总结面试表达
```

代码实现应优先帮助理解：

* 为什么需要这个机制
* 它解决什么问题
* 为什么采用当前设计
* 有什么替代方案和 Trade-off

目标不是记忆 LangGraph API，而是建立独立设计和实现 Agent 系统的能力。

