# LLM Desktop Control Roadmap

这个文档记录 `xiaozhi-desktop-mcp` 从“安全桌面工具层”走向“完整 LLM 桌面操控”的差距和实施顺序。

## 当前状态

| 层面 | 当前能力 | 状态 |
| --- | --- | --- |
| 看见桌面 | 全屏截图、白名单 App 窗口截图、macOS Vision OCR、MCP ImageContent | 已完成第一版 |
| 理解界面 | Accessibility UI 树：按钮、输入框、菜单、弹窗、值、启用/聚焦/选中状态、可执行动作和 bounds | 已完成第一版 |
| 操作界面 | 按 `element_id` 点击、输入、滚动、拖拽、菜单选择和安全路径文件选择 | 已完成第一版 |
| 闭环验证 | 调用方手动执行“观察 → 操作 → 再观察” | 待实现 |
| 自主规划 | 只执行调用方传入的固定 workflow steps | 待实现 |
| 通用 App 可靠性 | 依赖 App 的 Accessibility 质量和 macOS 权限 | 持续增强 |

## 第一阶段：桌面感知和语义操作

公开 Action：

```text
desktop_screenshot
desktop_window_screenshot
desktop_ocr
accessibility_capabilities
accessibility_tree
accessibility_action
```

原则：

- MCP 截图工具返回真正的图像内容块；HTTP API 返回 `image_base64`。
- 窗口截图、UI 树和 UI 操作只接受 `ALLOWED_APPS` 中的 App。
- UI 树返回路径式 `element_id`，例如 `ax:1.2.3`。界面变化后旧 ID 可能失效，操作前应重新读取。
- OCR bounds 使用 Vision 的左下角原点归一化坐标。
- 所有 UI 写操作都是中风险动作，API v2 和直接 MCP 工具都先创建 pending action，再单独确认。
- 文件对话框只能选择 Obsidian、任务目录、允许项目或 Xcode 项目安全根目录内已经存在的路径。
- 不向客户端暴露任意 JavaScript、任意 shell 或不受约束的坐标点击。

## 第二阶段：Observe–Act–Verify 闭环

目标流程：

```text
观察当前界面 → 选择语义元素 → 执行一步 → 重新观察 → 验证结果 → 重试或改计划
```

需要增加：

- observation/snapshot id 和操作前置条件；
- 操作后的自动 UI 树差异与截图验证；
- 等待元素出现、消失、启用或值变化；
- 有界重试、超时、错误分类和恢复策略；
- 防止界面变化后把旧 `element_id` 用到错误元素；
- 对密码框、支付、账户、权限和删除操作的更高风险策略。

## 第三阶段：动态工作流和可靠性

需要增加：

- 条件分支、循环、重试、等待和补偿步骤；
- 长任务的中断、恢复和主动通知；
- 稳定窗口标识，不只依赖窗口顺序；
- 多显示器、缩放、全屏 App、sheet、系统文件对话框适配；
- Chrome/Safari、Finder、Obsidian、Xcode、Terminal 等真实 macOS E2E 用例；
- 权限引导和 Screen Recording / Accessibility / Automation 自检。

LLM 规划、RAG、ASR 和 TTS 继续放在小智/Java 后端或独立 orchestrator；本仓库负责受控观察、执行、确认、持久化和审计。
