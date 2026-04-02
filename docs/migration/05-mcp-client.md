# v0.7.0 — MCP 客户端集成

## 概述

Model Context Protocol (MCP) 已成为 AI 工具生态的事实标准。
本版本让 agent_harness 能连接 MCP 服务器，自动将服务器提供的工具注册到 ToolRegistry。

---

## 原始代码

### MCP 客户端核心

📄 SOURCE: `src/services/mcp/client.ts` (3,348 lines)
- ⚡ MCP 客户端实现，基于 `@modelcontextprotocol/sdk`
- ⚡ 支持 3 种传输: StdioClientTransport, SSEClientTransport, StreamableHTTPClientTransport
- ⚡ 工具/提示词/资源的 listing 和调用

📄 SOURCE: `src/services/mcp/MCPConnectionManager.tsx`
- ⚡ 连接生命周期管理 (connect/disconnect/reconnect)
- ⚡ React 上下文（Python 需改为纯状态管理）

📄 SOURCE: `src/services/mcp/config.ts` (1,578 lines)
- ⚡ MCP 服务器配置加载与解析
- ⚡ 配置格式定义

📄 SOURCE: `src/services/mcp/types.ts`
- ⚡ TypeScript 类型定义 (MCPServerConfig, ScopedMcpServerConfig)

📄 SOURCE: `src/services/mcp/auth.ts` (2,465 lines)
- ⚡ OAuth token 管理 (checkAndRefreshOAuthTokenIfNeeded)
- ⚡ XAA 认证

📄 SOURCE: `src/services/mcp/envExpansion.ts`
- ⚡ 配置中的环境变量展开 (`${API_KEY}` → 实际值)

📄 SOURCE: `src/services/mcp/normalization.ts`
- ⚡ 工具/提示词名称规范化

📄 SOURCE: `src/services/mcp/channelPermissions.ts`
- ⚡ 权限强制执行

📄 SOURCE: `src/services/mcp/elicitationHandler.ts`
- ⚡ MCP 用户输入处理

### MCP 工具注册

📄 SOURCE: `src/tools/MCPTool/` (目录)
- ⚡ 将 MCP 服务器的工具包装为 Claude Code 的 Tool 类型

📄 SOURCE: `src/tools/ListMcpResourcesTool/` (目录)
- ⚡ 列出 MCP 资源

📄 SOURCE: `src/tools/ReadMcpResourceTool/` (目录)
- ⚡ 读取 MCP 资源内容

### 配置格式

```json
// settings.json 或 .claude/settings.json
{
  "mcpServers": {
    "filesystem": {
      "type": "stdio",
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/home/user"],
      "env": {}
    },
    "remote-server": {
      "type": "sse",
      "url": "https://mcp.example.com/sse"
    },
    "streamable": {
      "type": "http",
      "url": "https://mcp.example.com/mcp"
    }
  }
}
```

---

## Python 实现计划

Python MCP SDK: `pip install mcp` (官方 Python SDK)

🎯 TARGET: `agent_harness/mcp/` (新目录)

```
agent_harness/mcp/
├── __init__.py
├── client.py           # MCPClient — 连接管理 + 工具发现
├── config.py           # MCP 配置加载 (settings.json / dict)
├── tool_adapter.py     # 将 MCP Tool → agent_harness BaseTool
└── resource.py         # MCP 资源读取工具 (可选)
```

### 核心 API 设计

```python
from agent_harness.mcp import MCPClient, load_mcp_config

# 从配置加载
config = load_mcp_config("settings.json")  # 或传 dict

# 连接并发现工具
async with MCPClient(config) as client:
    mcp_tools = await client.get_tools()  # list[BaseTool]

    # 合并到现有 registry
    full_registry = ToolRegistry(builtin_tools + mcp_tools)

    ctx = AgentContext(tools=full_registry, ...)
```

### 依赖

```toml
[project.optional-dependencies]
mcp = ["mcp>=1.0.0"]
```

---

## 修改文件清单

| 操作 | 文件 | 说明 |
|------|------|------|
| 新建 | `agent_harness/mcp/__init__.py` | MCP 模块 |
| 新建 | `agent_harness/mcp/client.py` | MCPClient |
| 新建 | `agent_harness/mcp/config.py` | 配置加载 |
| 新建 | `agent_harness/mcp/tool_adapter.py` | MCP → BaseTool 适配 |
| 新建 | `agent_harness/mcp/resource.py` | 资源工具 |
| 修改 | `agent_harness/__init__.py` | 导出 |
| 修改 | `pyproject.toml` | 添加 mcp 可选依赖, 版本 → 0.7.0 |
| 新建 | `test_mcp.py` | 测试 |
