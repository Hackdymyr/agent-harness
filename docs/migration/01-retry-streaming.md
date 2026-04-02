# v0.3.0 — API 重试 + 流式输出

## 概述

当前 agent_harness 的 LLM 调用无重试机制（失败直接报错），且 `BaseLLM.chat()` 是批量返回（等全部生成完才有结果）。本版本添加：
1. 指数退避重试 + 错误分类
2. 流式输出 (SSE streaming)，让调用方实时收到生成 token

---

## 一、API 重试与错误处理

### 原始代码

📄 SOURCE: `src/services/api/withRetry.ts` (822 lines)
- ⚡ KEY FN: `withRetry<T>()` — line 170 — 核心重试 async generator
- ⚡ KEY FN: `getRetryDelay()` — line 530 — 指数退避计算
- ⚡ KEY FN: `shouldRetry()` — line 696 — 错误是否可重试判断
- ⚡ KEY FN: `is529Error()` — line 610 — 过载检测
- ⚡ KEY FN: `parseMaxTokensContextOverflowError()` — line 550 — 上下文溢出解析
- ⚡ CLASS: `CannotRetryError` — line 144
- ⚡ CLASS: `FallbackTriggeredError` — line 160

📄 SOURCE: `src/services/api/errors.ts` (1207 lines)
- ⚡ KEY FN: `getAssistantMessageFromError()` — line 425 — 错误 → 用户消息
- ⚡ KEY FN: `classifyAPIError()` — line 965 — 错误分类 (rate_limit/server_error/auth_error 等)
- ⚡ KEY FN: `isPromptTooLongMessage()` — line 64 — prompt 过长检测
- ⚡ KEY FN: `parsePromptTooLongTokenCounts()` — line 85 — 提取 token 数

📄 SOURCE: `src/services/api/errorUtils.ts` (260 lines)
- ⚡ KEY FN: `formatAPIError()` — line 200 — 连接错误格式化
- ⚡ KEY FN: `extractConnectionErrorDetails()` — line 42 — 递归提取嵌套错误
- ⚡ KEY FN: `getSSLErrorHint()` — line 94 — SSL 错误提示

📄 SOURCE: `src/services/rateLimitMessages.ts` (344 lines)
- ⚡ KEY FN: `getRateLimitMessage()` — line 45 — 限流消息生成
- ⚡ KEY FN: `isRateLimitErrorMessage()` — line 32 — 限流消息检测

### 重试策略详情

```
Base delay:    500ms
Backoff:       500ms * 2^(attempt-1)，上限 32s
Jitter:        +0~25% 随机抖动
可重试状态码:  408, 409, 429, 5xx, 连接错误
不可重试:      400(非溢出), 401(非刷新), 403
特殊处理:      529 (过载) — 最多连续 3 次后触发模型降级
```

### Python 实现计划

🎯 TARGET: `agent_harness/llm/retry.py` (新建)

```python
class RetryConfig:
    base_delay_ms: int = 500
    max_delay_ms: int = 32_000
    max_retries: int = 5
    jitter_fraction: float = 0.25

class RetryableError(Exception): ...
class NonRetryableError(Exception): ...

async def with_retry(operation, config=None) -> AsyncGenerator[RetryEvent, T]:
    """指数退避重试，yield 重试事件，return 最终结果"""

def get_retry_delay(attempt, retry_after=None, max_delay_ms=32000) -> float:
    """计算退避延迟"""

def should_retry(error) -> bool:
    """判断错误是否可重试"""

def classify_error(error) -> str:
    """错误分类: rate_limit/server_error/auth_error/context_overflow/unknown"""
```

🎯 TARGET: `agent_harness/llm/base.py` (修改)
- 在 `BaseLLM` 中添加可选 `retry_config: RetryConfig`
- 各适配器的 `chat()` 方法包裹 `with_retry()`

---

## 二、流式输出 (Streaming)

### 原始代码

📄 SOURCE: `src/services/api/claude.ts` (3419 lines)
- ⚡ KEY FN: streaming event loop — line 1940 — `for await (const part of stream)` 迭代 SSE 事件
- ⚡ KEY FN: `cleanupStream()` — line 2895 — 流资源清理
- ⚡ KEY FN: streaming idle watchdog — line 1868-1912 — 90s 超时中止
- ⚡ 事件类型: message_start, content_block_start, content_block_delta, content_block_stop, message_delta, message_stop

📄 SOURCE: `src/utils/stream.ts` (77 lines)
- ⚡ CLASS: `Stream<T>` — 自定义 async iterator，支持 enqueue/done/error

### 流式事件类型

```typescript
BetaRawMessageStreamEvent:
  message_start     → {message: {id, usage}}
  content_block_start → {index, content_block: {type: text|tool_use|thinking}}
  content_block_delta → {index, delta: {type: text_delta, text} | {type: input_json_delta, partial_json}}
  content_block_stop  → {index}
  message_delta      → {delta: {stop_reason}, usage}
  message_stop       → {}
```

### Python 实现计划

🎯 TARGET: `agent_harness/llm/base.py` (修改)

```python
@dataclass
class StreamEvent:
    type: Literal["text_delta", "tool_input_delta", "message_start", "message_done", "content_block_start", "content_block_stop"]
    text: str | None = None
    index: int | None = None
    usage: Usage | None = None
    stop_reason: StopReason | None = None

class BaseLLM:
    async def chat(...) -> LLMResponse: ...              # 现有批量接口，保持不变
    async def chat_stream(...) -> AsyncGenerator[StreamEvent, LLMResponse]: ...  # 新增流式接口
```

🎯 TARGET: `agent_harness/llm/anthropic.py` (修改)
- 使用 `client.messages.stream()` 实现 `chat_stream()`

🎯 TARGET: `agent_harness/llm/openai.py` (修改)
- 使用 `client.chat.completions.create(stream=True)` 实现

🎯 TARGET: `agent_harness/llm/openai_compat.py` (修改)
- 同 openai.py

🎯 TARGET: `agent_harness/agent/loop.py` (修改)
- AgentLoop 添加 `streaming: bool = False` 参数
- streaming=True 时调用 `chat_stream()` 并 yield `AgentEvent(type="stream_delta")`
- streaming=False 时行为不变（向后兼容）

### 流式超时看门狗

```python
STREAM_IDLE_TIMEOUT_S = 90

async def _stream_with_watchdog(stream, timeout=90):
    """包装流式迭代器，超时无数据时中止"""
```

---

## 修改文件清单

| 操作 | 文件 | 说明 |
|------|------|------|
| 新建 | `agent_harness/llm/retry.py` | 重试引擎 |
| 修改 | `agent_harness/llm/base.py` | 添加 chat_stream() + RetryConfig |
| 修改 | `agent_harness/llm/anthropic.py` | 实现 chat_stream() + 重试 |
| 修改 | `agent_harness/llm/openai.py` | 实现 chat_stream() + 重试 |
| 修改 | `agent_harness/llm/openai_compat.py` | 实现 chat_stream() + 重试 |
| 修改 | `agent_harness/agent/loop.py` | 支持流式模式 |
| 修改 | `agent_harness/types.py` | 添加 StreamEvent |
| 新建 | `test_retry_streaming.py` | 测试 |
| 修改 | `pyproject.toml` + `__init__.py` | 版本 → 0.3.0 |
