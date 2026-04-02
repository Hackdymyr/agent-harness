# v0.4.0 — 上下文压缩 (Compaction)

## 概述

当前 agent_harness 的上下文管理是简单截断 (`_manage_context` 在 loop.py 中保留首尾消息)。
Claude Code 有完整的 compaction 系统：用 LLM 对旧消息生成摘要，替换原始消息，保留近期上下文。
这是长对话场景的核心功能。

---

## 原始代码

### 主压缩引擎

📄 SOURCE: `src/services/compact/compact.ts` (1706 lines)
- ⚡ KEY FN: `compactConversation()` — line 387 — 主压缩函数：摘要旧消息 + 保留近期
- ⚡ KEY FN: `partialCompactConversation()` — line 772 — 部分压缩 (direction='from'|'up_to')
- ⚡ KEY FN: `stripImagesFromMessages()` — line 145 — 压缩前移除图片
- ⚡ KEY FN: `stripReinjectedAttachments()` — line 211 — 移除注入的附件
- ⚡ KEY FN: `truncateHeadForPTLRetry()` — line 243 — prompt 过长时的兜底截断
- ⚡ KEY FN: `createPostCompactFileAttachments()` — line 1415 — 压缩后重新注入最近访问的文件
- ⚡ KEY FN: `streamCompactSummary()` — line 1136 — 调用 LLM 流式生成摘要

### 自动触发

📄 SOURCE: `src/services/compact/autoCompact.ts` (352 lines)
- ⚡ KEY FN: `autoCompactIfNeeded()` — line 241 — 主入口，编排压缩尝试
- ⚡ KEY FN: `shouldAutoCompact()` — line 160 — 判断是否需要自动压缩
- ⚡ KEY FN: `getAutoCompactThreshold()` — line 72 — 计算 token 阈值
- ⚡ KEY FN: `getEffectiveContextWindowSize()` — line 33 — 有效上下文窗口大小
- ⚡ KEY FN: `calculateTokenWarningState()` — line 93 — 警告/错误阈值计算

**阈值常量:**
```
AUTOCOMPACT_BUFFER_TOKENS = 13,000
WARNING_THRESHOLD_BUFFER_TOKENS = 20,000
MAX_CONSECUTIVE_AUTOCOMPACT_FAILURES = 3  (熔断: 3 次连续失败后停止)
MAX_OUTPUT_TOKENS_FOR_SUMMARY = 20,000
```

### 微压缩 (MicroCompact)

📄 SOURCE: `src/services/compact/microCompact.ts` (531 lines)
- ⚡ KEY FN: `microcompactMessages()` — line 253 — 清除旧工具结果（不修改消息文本）
- ⚡ KEY FN: `estimateMessageTokens()` — line 164 — 粗略 token 估算
- ⚡ KEY FN: `collectCompactableToolIds()` — line 226 — 收集可压缩的 tool_use ID

**可压缩的工具类型:**
```
read_file, bash, grep, glob, web_search, web_fetch, edit_file, write_file
```

### Session Memory 压缩

📄 SOURCE: `src/services/compact/sessionMemoryCompact.ts` (631 lines)
- ⚡ KEY FN: `trySessionMemoryCompaction()` — line 514 — 基于 session memory 的压缩
- ⚡ KEY FN: `shouldUseSessionMemoryCompaction()` — line 403 — 功能门控
- ⚡ KEY FN: `calculateMessagesToKeepIndex()` — line 324 — 计算保留消息索引

### API 侧压缩

📄 SOURCE: `src/services/compact/apiMicrocompact.ts` (154 lines)
- ⚡ KEY FN: `getAPIContextManagement()` — line 64 — API 层上下文管理策略

### 压缩提示词

📄 SOURCE: `src/services/compact/prompt.ts` (375 lines)
- ⚡ KEY FN: `getCompactPrompt()` — line 293 — 完整压缩提示词
- ⚡ KEY FN: `getPartialCompactPrompt()` — line 274 — 部分压缩提示词
- ⚡ KEY FN: `formatCompactSummary()` — line 311 — 格式化摘要输出
- ⚡ CONST: `BASE_COMPACT_PROMPT` — line 61-143 — 摘要模板

**摘要必须包含的 9 个部分:**
1. Primary Request and Intent
2. Key Technical Concepts
3. Files and Code Sections
4. Errors and Fixes
5. Problem Solving
6. All User Messages (non-tool-result)
7. Pending Tasks
8. Current Work
9. Optional Next Step

### 消息分组

📄 SOURCE: `src/services/compact/grouping.ts` (64 lines)
- ⚡ KEY FN: `groupMessagesByApiRound()` — line 22 — 按 API 轮次分组

### 压缩后清理

📄 SOURCE: `src/services/compact/postCompactCleanup.ts` (77 lines)
- ⚡ KEY FN: `runPostCompactCleanup()` — line 31 — 清理缓存/状态

### Token 计数

📄 SOURCE: `src/utils/tokens.ts` (~110 lines)
- ⚡ KEY FN: `getTokenUsage()` — 从 assistant 消息提取 usage
- ⚡ KEY FN: `tokenCountFromLastAPIResponse()` — 最近一次 API 调用的上下文大小

📄 SOURCE: `src/utils/context.ts` (~100 lines)
- ⚡ KEY FN: `getContextWindowForModel()` — 模型上下文窗口大小

### 在查询循环中的调用位置

📄 SOURCE: `src/query/query.ts` (lines 400-470)
```
执行顺序:
1. line 403: Snip (历史裁剪)
2. line 414: Microcompact (微压缩)
3. line 441: Context collapse (上下文折叠)
4. line 454: Autocompact (自动压缩)
```

---

## Python 实现计划

### 简化策略

Claude Code 的压缩系统极其复杂（涉及缓存共享、feature flags、API 侧策略等）。
agent_harness 采用简化版本：

1. **LLM 摘要压缩** — 核心功能，必须实现
2. **微压缩 (工具结果清理)** — 实现简化版
3. **自动触发** — 基于 token 估算
4. **跳过**: Session Memory 压缩、API 侧压缩、缓存共享（Anthropic 特有）

### 新建文件

🎯 TARGET: `agent_harness/compact/` (新目录)

```
agent_harness/compact/
├── __init__.py
├── compactor.py          # 主压缩引擎
├── prompt.py             # 压缩提示词
├── auto_compact.py       # 自动触发逻辑
├── micro_compact.py      # 工具结果清理
└── token_estimation.py   # Token 粗估
```

🎯 TARGET: `agent_harness/compact/compactor.py`
```python
class CompactConfig:
    buffer_tokens: int = 13_000
    max_summary_tokens: int = 20_000
    max_consecutive_failures: int = 3
    context_window: int = 200_000

async def compact_conversation(
    messages: list[dict],
    llm: BaseLLM,
    config: CompactConfig,
) -> CompactResult:
    """调用 LLM 生成旧消息摘要，返回压缩后的消息列表"""

async def micro_compact(
    messages: list[dict],
    compactable_tools: set[str],
) -> list[dict]:
    """清理旧的工具调用结果，用简短占位替代"""
```

🎯 TARGET: `agent_harness/agent/loop.py` (修改)
- 在 LLM 调用前添加 `await self._auto_compact_if_needed()`
- 使用 token 估算判断是否需要压缩

---

## 修改文件清单

| 操作 | 文件 | 说明 |
|------|------|------|
| 新建 | `agent_harness/compact/__init__.py` | 模块导出 |
| 新建 | `agent_harness/compact/compactor.py` | 主压缩引擎 |
| 新建 | `agent_harness/compact/prompt.py` | 摘要提示词模板 |
| 新建 | `agent_harness/compact/auto_compact.py` | 自动触发 |
| 新建 | `agent_harness/compact/micro_compact.py` | 工具结果清理 |
| 新建 | `agent_harness/compact/token_estimation.py` | Token 粗估 (~4 chars/token) |
| 修改 | `agent_harness/agent/loop.py` | 集成自动压缩 |
| 修改 | `agent_harness/agent/context.py` | 添加 context_window 配置 |
| 新建 | `test_compaction.py` | 测试 |
| 修改 | `pyproject.toml` + `__init__.py` | 版本 → 0.4.0 |
