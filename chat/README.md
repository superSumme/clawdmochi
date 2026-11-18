# chat/ · DeepSeek 触感层（demo 灵魂）

- `demo_chat.py` — 终端流式对话入口：自动把最新触摸记录翻译成【体感】便签喂给 DeepSeek
- `feel.py` — jsonl → 体感便签的翻译器（可单独跑 `python chat/feel.py` 看当前体感）

## 为什么是 API 而不是教程的 MCP 路线

claude.ai 自定义连接器是 Claude 专属；DeepSeek 网页/App 不开放自定义连接器。
所以 demo 用本地脚本把触摸记录喂给 DeepSeek 的 OpenAI 兼容 API
（`https://api.deepseek.com`，模型 `deepseek-chat`）。这套"身体接口"以后接任何 AI 都能复用。

## 环境变量（仓库根目录 .env，参考 .env.example）

```
DEEPSEEK_API_KEY=sk-你的key
DEEPSEEK_MODEL=deepseek-chat   # 可选，想用 R1 可改 deepseek-reasoner
```
