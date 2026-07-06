# Xiaozhi Integration

This project is a standard MCP server over stdio or Streamable HTTP. It does not talk to the ESP32 device directly.

## Integration Options

### `mcp_pipe.py`

Use the `78/mcp-calculator` style bridge when you want the smallest setup. Point the bridge at this server command:

```bash
python -m xiaozhi_desktop_mcp.server
```

This is best for quick demos and local experiments.

### `xiaozhi-mcphub`

Use `huangjunsen0406/xiaozhi-mcphub` when you want a dashboard, multiple MCP servers, grouping, logs, and tool routing.

Register this project as a stdio MCP server, then bind it to the Xiaozhi endpoint that should control this Mac.

### Streamable HTTP MCP Clients

Use this when a client can connect directly to a standard MCP Streamable HTTP endpoint:

```bash
xiaozhi-desktop-mcp-streamable
```

Then point the client at:

```text
http://127.0.0.1:8766/mcp
```

If the endpoint is not localhost-only, set `DESKTOP_MCP_AUTH_TOKEN` and pass it
as `Authorization: Bearer <token>` or `X-Desktop-Mcp-Token`.

### `xiaozhi-esp32-server`

Use `xinnan-tech/xiaozhi-esp32-server` when it is your main Xiaozhi backend. Keep this desktop MCP server running on the Mac, then add it through the server's MCP/tool configuration.

The Xiaozhi server handles ASR, TTS, LLM, memory, and intent selection. This project only performs local desktop actions.

## Voice Flows

- "小智，记一下：今天先做个人电脑工作流 MCP。"
  - Calls `obsidian_save_memory`.
- "小智，打开 Xcode。"
  - Calls `app_open` with `Xcode`.
- "小智，让 cc 帮我检查这个项目的 README。"
  - Calls `cc_create_task` and creates a pending Markdown task.

Keep desktop actions local. If Xiaozhi runs in the cloud, expose this MCP server only through a trusted local bridge or private network.
