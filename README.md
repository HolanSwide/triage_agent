# Evidence-Based Test Triage Agent

这是一个用于学习 LangGraph 的小型项目。Task 00 只完成项目初始化，以及对当前 DeepSeek 模型配置的三项能力检查；正式 Triage Agent 会在后续任务中实现。

## 环境

使用 conda 环境 `helloagent`。当前配置从环境变量读取：

- `DEEPSEEK_API_KEY`
- `DEEPSEEK_MODEL`
- `DEEPSEEK_API_BASE`

可以 source 已有的本地 `env.sh`，或复制 `.env.example` 为 `.env` 后自行配置。不要提交真实 API Key。

## 运行

```bash
source env.sh
conda run -n helloagent python -m src.task00_model_check all
```

也可以只运行一项：

```bash
conda run -n helloagent python -m src.task00_model_check basic
conda run -n helloagent python -m src.task00_model_check tool
conda run -n helloagent python -m src.task00_model_check structured
```

本地无网络调用的最小单元测试：

```bash
conda run -n helloagent python -m unittest discover -s tests -v
```

能力检查脚本会输出 JSON，并在任意检查失败时返回非零退出码。Tool Calling 使用确定性的模拟温度工具；Structured Output 使用 `StructuredResult` Pydantic schema 和 LangChain 的 `json_mode` 方式。当前模型在 thinking mode 下不接受 `function_calling` 结构化输出所需的 tool choice，因此使用 JSON mode 作为兼容路径。
