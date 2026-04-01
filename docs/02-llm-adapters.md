# 02 LLM 适配器 / LLM Adapters

## 概述 / Overview

`BaseLLM` 是一个 Python Protocol（类似接口），定义了所有 LLM 适配器必须实现的方法。本库内置三个适配器，你也可以自己写。

`BaseLLM` is a Python Protocol (interface) that defines the methods all LLM adapters must implement. Three are built-in; you can also write your own.

---

## 内置适配器 / Built-in Adapters

### 1. AnthropicLLM — Claude 系列

```python
from agent_harness import AnthropicLLM

llm = AnthropicLLM(
    model="claude-sonnet-4-20250514",  # 模型 ID
    api_key="sk-ant-...",             # 可选，默认读 ANTHROPIC_API_KEY 环境变量
    base_url=None,                     # 可选，自定义 API 端点
)
```

**依赖**：`pip install anthropic`

**特点**：
- Anthropic 使用 content blocks 格式（`tool_use` 嵌在 assistant message 的 content 数组里）
- 适配器自动处理格式转换，你不需要关心

### 2. OpenAILLM — GPT 系列

```python
from agent_harness import OpenAILLM

llm = OpenAILLM(
    model="gpt-4o",
    api_key="sk-...",                  # 可选，默认读 OPENAI_API_KEY 环境变量
    base_url=None,
)
```

**依赖**：`pip install openai`

**特点**：
- OpenAI 使用 `tool_calls` 字段（和 Anthropic 格式不同）
- 工具结果通过 `role: "tool"` 的独立消息返回
- 适配器自动处理这些差异

### 3. OpenAICompatLLM — 任何兼容 OpenAI 接口的模型

```python
from agent_harness import OpenAICompatLLM

# Ollama 本地模型
llm = OpenAICompatLLM(
    base_url="http://localhost:11434/v1",
    model="llama3",
    api_key="not-needed",  # Ollama 不需要 key
)

# 阿里云百炼
llm = OpenAICompatLLM(
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    model="qwen-plus",
    api_key="sk-...",
)

# DeepSeek
llm = OpenAICompatLLM(
    base_url="https://api.deepseek.com/v1",
    model="deepseek-chat",
    api_key="sk-...",
)

# vLLM 本地部署
llm = OpenAICompatLLM(
    base_url="http://localhost:8000/v1",
    model="Qwen/Qwen2-7B-Instruct",
    api_key="not-needed",
)
```

**依赖**：`pip install openai`（OpenAI SDK 支持自定义 base_url）

**特点**：
- 继承自 `OpenAILLM`，只是覆盖了 `base_url`
- 适用于所有提供 OpenAI 兼容 API 的服务

---

## 自定义适配器 / Custom Adapter

如果你的模型不兼容 OpenAI 格式，可以自己实现 `BaseLLM`：

If your model isn't OpenAI-compatible, implement `BaseLLM` yourself:

```python
from agent_harness.types import LLMResponse, Message, Role, StopReason, ToolCall, Usage
from agent_harness.llm.base import BaseLLM

class MyCustomLLM:
    """只需要实现 chat() 方法。"""

    async def chat(self, messages, tools=None, system=None, max_tokens=4096, **kwargs):
        # 1. 把 messages 转成你的模型的格式
        # 2. 调用你的模型 API
        # 3. 把响应转成 LLMResponse

        # 解析工具调用（如果有）
        tool_calls = None
        if 模型返回了工具调用:
            tool_calls = [
                ToolCall(id="xxx", name="tool_name", input={"key": "value"})
            ]

        return LLMResponse(
            message=Message(
                role=Role.ASSISTANT,
                content="模型的文本回复",
                tool_calls=tool_calls,
            ),
            stop_reason=StopReason.TOOL_USE if tool_calls else StopReason.END_TURN,
            usage=Usage(input_tokens=100, output_tokens=50),
        )

    async def chat_stream(self, messages, tools=None, system=None, max_tokens=4096, **kwargs):
        # 流式版本（可选，简单实现可以直接调 chat() 然后 yield）
        result = await self.chat(messages, tools, system, max_tokens, **kwargs)
        yield result
```

**关键**：你只需要保证：
1. `chat()` 返回 `LLMResponse`
2. `LLMResponse.message.tool_calls` 是 `list[ToolCall]` 或 `None`
3. `stop_reason` 在有工具调用时设为 `TOOL_USE`，否则 `END_TURN`

---

## 消息格式转换原理 / Message Format Conversion

不同提供商的消息格式差异很大，适配器的核心工作就是做格式转换：

```
统一格式 (agent_harness)          Anthropic 格式                 OpenAI 格式
───────────────────────          ──────────────                 ──────────────
Message(                         {                              {
  role="assistant",                role: "assistant",             role: "assistant",
  content="好的",                  content: [                     content: "好的",
  tool_calls=[ToolCall(              {type:"text",text:"好的"},   tool_calls: [{
    name="read",                     {type:"tool_use",              id: "c1",
    input={path:"x"}                  id:"c1",name:"read",          type: "function",
  )]                                  input:{path:"x"}}            function: {
)                                  ]                                name: "read",
                                 }                                  arguments: '{"path":"x"}'
                                                                  }}]
                                                                }

工具结果:
───────────────────────          ──────────────                 ──────────────
{role:"user", content:[          {role:"user", content:[        {role:"tool",
  {tool_use_id:"c1",              {type:"tool_result",           tool_call_id:"c1",
   content:"文件内容"}]}            tool_use_id:"c1",             content:"文件内容"}
                                   content:"文件内容"}]}
```

你不需要手动处理这些——适配器会自动完成。但如果你在 debug，了解这个映射关系很有帮助。
