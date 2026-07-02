# Xiaozhi Desktop MCP

把小智接到本机 Mac 工作流的桌面 MCP 服务

从 Obsidian 记忆、App 控制，到 Claude Code / Codex 可见会话、项目别名、待确认动作和多语言 HTTP 接入。  
一套面向语音助手、桌面自动化和本地 AI 编程工作流的安全工具层。

中文 · [API](docs/api.md) · [Client Examples](docs/clients.md) · [Operations](docs/operations.md) · [Security](docs/security.md)

License: MIT · Version: 1.0.0 · MCP / HTTP Desktop Workflow

一个语音指令进来，Obsidian 记忆、Claude Code 会话、项目任务、状态查询和安全确认出去。  
它不是新的小智服务器，也不是任意 shell 执行器，而是一个受白名单约束、可被 Java / Python / Go 调用的本机桌面工具服务。

```text
Voice / Client
  -> API v1 Dispatch
  -> Safety Checks
  -> Obsidian / App / Claude Code / Pending Action
  -> Spoken Result
```

## 为什么需要它

小智能听懂你说什么，但真正接入桌面工作流时，难点不是“调用一个命令”：

- 语音误识别可能打开或关闭错误 App
- Claude Code / Codex 只能在允许项目里启动
- Obsidian 写入必须限制在 vault 内
- 中风险动作需要先确认，而不是直接执行
- Java、Python、Go 客户端不应该各自适配一堆散乱路由
- 桌面会话长期运行后需要自检、清理和可观测状态

Xiaozhi Desktop MCP 把这些约束编码成一套稳定接口：

```text
统一 HTTP API
  -> 白名单边界
  -> 语音友好返回
  -> 待确认动作
  -> 多语言接入
  -> 本机桌面执行
```

## 核心能力

| 能力 | 覆盖范围 |
| --- | --- |
| API v1 | `GET /api/v1/actions`、`GET /api/v1/health`、`POST /api/v1/dispatch` |
| 多语言接入 | Java、Python、Go 或任意 HTTP 客户端 |
| Obsidian | 保存记忆、新建/打开/追加笔记、每日笔记、搜索、读取最近记忆 |
| Claude Code / Codex | 打开项目、发送任务、slash 命令、切模型、查看状态、继续、聚焦、停止 |
| 项目别名 | 从 `CC_ALLOWED_PROJECTS` 生成安全项目目录 |
| App 控制 | 打开或关闭 `ALLOWED_APPS` 白名单内的 macOS App |
| Xcode | 打开项目、build、test、clean、查看最近错误摘要 |
| 待确认动作 | 中风险动作先入队，确认后执行 |
| 自检与目录 | 环境自检、配置摘要、工具目录、会话清理 |

## 30 秒开始

```bash
git clone git@github.com:jijiutong/xiaozhi-desktop-mcp.git
cd xiaozhi-desktop-mcp
python3 -m venv .venv
. .venv/bin/activate
pip install -e .
cp .env.example .env
```

编辑 `.env`，至少确认：

```env
OBSIDIAN_VAULT=/path/to/your/obsidian-vault
DEFAULT_PROJECT_ROOT=/path/to/your/project
CC_ALLOWED_PROJECTS=/path/to/your/project
XCODE_ALLOWED_PROJECTS=/path/to/your/project
ALLOWED_APPS=Obsidian,Terminal,Google Chrome
```

启动 HTTP 服务：

```bash
xiaozhi-desktop-http
```

如果把 HTTP 服务绑定到非本机地址，必须设置 `DESKTOP_MCP_AUTH_TOKEN`。调用受保护接口时传：

```bash
curl -H "Authorization: Bearer change-me" http://127.0.0.1:8765/api/v1/actions
```

检查服务：

```bash
curl http://127.0.0.1:8765/api/v1/health
```

## 多语言统一调用

推荐所有新客户端使用：

```text
POST /api/v1/dispatch
```

请求：

```json
{
  "request_id": "client-001",
  "action": "list_projects",
  "params": {}
}
```

响应：

```json
{
  "success": true,
  "request_id": "client-001",
  "action": "list_projects",
  "spoken_message": "当前有 1 个允许的项目。",
  "error_spoken_message": "",
  "error": "",
  "data": {}
}
```

客户端建议：

- 成功时读 `spoken_message`
- 失败时读 `error_spoken_message`
- 调试信息读 `data`
- 日志串联使用 `request_id`

## Java 接入

```java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

public class DesktopMcpDemo {
  public static void main(String[] args) throws Exception {
    String body = """
      {
        "request_id": "java-demo-1",
        "action": "list_projects",
        "params": {}
      }
      """;

    HttpRequest request = HttpRequest.newBuilder()
        .uri(URI.create("http://127.0.0.1:8765/api/v1/dispatch"))
        .header("Content-Type", "application/json")
        .POST(HttpRequest.BodyPublishers.ofString(body))
        .build();

    HttpResponse<String> response = HttpClient.newHttpClient()
        .send(request, HttpResponse.BodyHandlers.ofString());

    System.out.println(response.body());
  }
}
```

## Python 接入

```python
import requests

payload = {
    "request_id": "python-demo-1",
    "action": "ask_cc_project",
    "params": {
        "project": "your-project-alias",
        "text": "帮我检查这个项目的 README。"
    },
}

response = requests.post(
    "http://127.0.0.1:8765/api/v1/dispatch",
    json=payload,
    timeout=10,
)

data = response.json()
print(data["spoken_message"] if data["success"] else data["error_spoken_message"])
```

## Go 接入

```go
package main

import (
	"bytes"
	"fmt"
	"io"
	"net/http"
)

func main() {
	body := []byte(`{
	  "request_id": "go-demo-1",
	  "action": "list_projects",
	  "params": {}
	}`)

	resp, err := http.Post(
		"http://127.0.0.1:8765/api/v1/dispatch",
		"application/json",
		bytes.NewReader(body),
	)
	if err != nil {
		panic(err)
	}
	defer resp.Body.Close()

	data, _ := io.ReadAll(resp.Body)
	fmt.Println(string(data))
}
```

## 常用 Action

| 任务 | Action |
| --- | --- |
| 保存一条记忆 | `remember` |
| 列出允许项目 | `list_projects` |
| 按项目名交给 Claude Code | `ask_cc_project` |
| 给 Claude Code 发 slash 命令 | `cc_send_slash_command` |
| 切换 Claude Code 模型 | `cc_switch_model` |
| 查看 Claude Code 状态 | `check_cc` |
| 让 Claude Code 继续 | `continue_cc` |
| 停止 Claude Code | `stop_cc` |
| 打开 App | `app_open` |
| 关闭 App | `app_close` |
| 搜索 Obsidian | `search_obsidian` |
| 新建 Obsidian 笔记 | `create_note` |
| 打开 Obsidian 笔记 | `open_note` |
| 写入每日笔记 | `append_daily_note` |
| 打开 Xcode 项目 | `xcode_open_project` |
| Xcode 构建 | `xcode_build` |
| Xcode 测试 | `xcode_test` |
| Xcode 清理 | `xcode_clean` |
| 查看 Xcode 最近错误 | `xcode_last_errors` |
| 创建待确认动作 | `pending_create` |
| 确认待执行动作 | `pending_confirm` |
| 桌面环境自检 | `health` |
| 查看工具目录 | `tool_catalog` |

查看完整 action 列表：

```bash
curl http://127.0.0.1:8765/api/v1/actions
```

## 典型语音

```text
小智，记一下：这个项目先做成桌面 MCP。
小智，打开这个项目的 Claude Code。
小智，把这个任务交给 cc：检查 README 是否清楚。
小智，让 cc 执行 /status。
小智，看看 cc 现在卡在哪。
小智，搜索 Obsidian 里关于桌面 MCP 的笔记。
小智，打开 Xcode 项目并构建。
小智，创建一篇 Obsidian 笔记，标题是今天的想法。
```

## 安全边界

| 边界 | 说明 |
| --- | --- |
| 任意 shell | 不提供 |
| App | 只能操作 `ALLOWED_APPS` |
| 项目 | 只能进入 `CC_ALLOWED_PROJECTS` |
| Xcode | 只能操作 `XCODE_ALLOWED_PROJECTS` |
| Obsidian | 只能访问 `OBSIDIAN_VAULT` |
| 中风险动作 | API v1 默认创建 pending action，`confirm=true` 才直接执行 |
| 会话状态 | 仅保存进程内状态，重启清空 |

## 目录结构

| 路径 | 作用 |
| --- | --- |
| `src/xiaozhi_desktop_mcp/api_v1.py` | 多语言统一 dispatch API |
| `src/xiaozhi_desktop_mcp/http_server.py` | FastAPI HTTP 服务 |
| `src/xiaozhi_desktop_mcp/server.py` | MCP stdio 服务 |
| `src/xiaozhi_desktop_mcp/tools/` | Obsidian、App、cc、项目、待确认动作等工具 |
| `docs/api.md` | API 协议 |
| `docs/clients.md` | Java / Python / Go 示例 |
| `docs/operations.md` | 启动、检查和排障 |
| `docs/security.md` | 安全模型 |

## 文档

| 文档 | 适合谁 |
| --- | --- |
| [API v1](docs/api.md) | 接入方、后端服务、SDK 作者 |
| [Client Examples](docs/clients.md) | Java / Python / Go 客户端 |
| [Operations](docs/operations.md) | 部署、启动、排障 |
| [Security Model](docs/security.md) | 关心边界和风险的人 |
| [Xiaozhi Integration](docs/xiaozhi-integration.md) | 小智服务接入 |
| [Changelog](CHANGELOG.md) | 版本变化 |

## License

MIT
