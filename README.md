# Agent Development Learning Repository

## 仓库介绍

本仓库用于学习和实践 Agent 开发。

## 环境说明

项目使用 conda 环境 `helloagent`：

```bash
conda activate helloagent
```

API Key 通过环境变量 `DEEPSEEK_API_KEY` 配置：

```bash
export DEEPSEEK_API_KEY="<your-api-key>"
```

真实 API Key 仅用于本地运行，禁止提交到仓库。

## 交互规则

1. 所有陈述和动作都必须基于确定的文档或已知信息。禁止臆断、猜测，以及在信息不确定时修改代码。
2. 回复必须简洁、直接、真实。禁止长篇大论、重复和无关内容。
3. 发现用户语言或文档中存在错误或矛盾时，必须先指出并确认，再执行任务。禁止不加判断地直接执行。
