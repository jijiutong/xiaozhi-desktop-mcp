# Xiaozhi Desktop MCP 4.0 大版本升级计划

> 版本主题：从“能看、能点”升级为“可验证、可恢复、可审计的桌面执行层”。

## 当前实施状态（2026-07-29）

`4.0.0` 已落地：版本化 SQLite migration、短期 Observation、窗口与语义目标重校验、结构化前置条件、pending confirmation、幂等执行、操作后 expectation 轮询、客户端细粒度 scope，以及带只读重试、租约、事件和安全恢复的动态工作流。

固定真实 Mac smoke 矩阵已写入脚本和运维文档。本次因实例无人使用而直接切 GA，未保留原计划的 3 个工作日 RC soak；启用真实客户端前仍应在已登录且授予 Screen Recording、Accessibility、Automation 权限的 Mac 上执行矩阵。人工确认边界没有放宽。

## 1. 结论

4.0 不继续横向堆 App action，而是补齐可靠桌面自动化的闭环：

```text
Observe（观察）
  -> Check（检查前置条件和目标是否仍然有效）
  -> Confirm（按风险确认）
  -> Act（只执行一个有界动作）
  -> Verify（重新观察并验证结果）
  -> Recover（有界重试、补偿或安全停止）
```

计划先把当前主分支的截图、OCR、Accessibility UI 树和语义操作作为 `3.1.0` 发布并稳定下来，再开始 4.0。4.0 GA 的核心交付是 Observe–Act–Verify 闭环、动态但有界的工作流、可迁移状态库、客户端权限策略，以及真实 macOS E2E 验证。

建议周期为 **7 周 / 35–45 人日**。如果只有一名开发者，按下文 P0 范围交付；P1 App 适配可以顺延到 4.1。

## 2. 当前基线

截至计划制定时：

- 稳定版本：`3.0.0`；主分支包含尚未发布的桌面感知与语义 UI 操作。
- 入口：MCP stdio、MCP Streamable HTTP、HTTP API v1/v2。
- 状态：SQLite 持久化 pending actions、workflows 和脱敏 audit events。
- 安全边界：App/项目/路径白名单，中风险动作独立确认，无任意 shell、JavaScript 或坐标点击。
- 工作流：只支持调用方给出的线性 action steps；可暂停确认、重启恢复和取消。
- 桌面控制：能截图、OCR、读 Accessibility 树，并按路径式 `element_id` 操作。
- 主要缺口：路径式元素 ID 会随 UI 变化失效；动作前没有快照校验；动作后没有自动验证；工作流没有条件、等待、重试和补偿；状态库没有显式 schema migration 机制。
- 工程基线：96 个测试通过，Ruff 通过；CI 覆盖 Python 3.10–3.13，并有 macOS import smoke。

## 3. 4.0 目标与非目标

### 目标（P0）

1. 每次 UI 写操作都能绑定 observation，并在执行前检测界面漂移。
2. 操作后自动生成新 observation，按明确 expectation 判断成功或失败。
3. 支持等待、条件分支、有界重试和补偿，不支持无界循环。
4. pending action、workflow 和执行 step 在进程崩溃或重启后不重复执行。
5. SQLite schema 可版本化、可前向迁移，并提供迁移前备份说明和 dry-run 检查。
6. 客户端能通过能力发现知道 action、schema、风险、所需权限和支持的验证方式。
7. 在 Chrome/Safari、Finder、Obsidian、Xcode、Terminal 上建立可重复的 macOS E2E 用例。
8. 保持现有 `/api/v1`、`/api/v2` 请求响应 envelope 和已有 action 名兼容。

### P1（允许进入 4.1）

- 多显示器、缩放、全屏窗口和 sheet 的完整适配。
- 更丰富的 App 专用稳定定位器。
- workflow 完成/失败的 webhook 或系统通知。
- 批量 observation 压缩和长期运行统计面板。

### 非目标

- 不在本仓库实现 LLM 规划、RAG、ASR 或 TTS。
- 不增加任意 shell、任意 JavaScript、任意坐标点击。
- 不支持支付、账户、权限变更、密码管理器或破坏性文件操作。
- 不承诺用一个通用 Driver 覆盖所有 macOS App；通用 Accessibility 不可靠时使用显式 Driver。

## 4. 对外能力设计

坚持“少而通用”。建议只新增两个核心 action，并扩展现有 workflow action：

| Action | 风险 | 作用 |
| --- | --- | --- |
| `desktop_observe` | sensitive-read | 一次返回窗口身份、UI tree、可选截图/OCR、`observation_id` 和内容指纹 |
| `desktop_execute_step` | medium | 绑定旧 observation，重定位目标，检查前置条件，确认后执行一个动作并自动验证 |
| `workflow_plan` | mixed | 兼容旧 action step，新增 wait/condition/branch/retry/compensation 描述 |
| `workflow_execute` | mixed | 驱动状态机，遇到确认、外部等待或失败时安全暂停 |
| `workflow_get` | low | 返回当前状态、step 结果、等待原因和脱敏事件摘要 |

### 4.1 Observation

`desktop_observe` 最少返回：

```json
{
  "observation_id": "obs_...",
  "captured_at": "...",
  "expires_at": "...",
  "app": "Google Chrome",
  "window": {
    "window_id": "win_...",
    "title": "Example",
    "bounds": {"x": 0, "y": 0, "width": 1200, "height": 800}
  },
  "tree_fingerprint": "sha256:...",
  "elements": [],
  "truncated": false
}
```

约束：

- `observation_id` 有 TTL，过期后必须重新观察。
- 默认只持久化窗口元数据、元素摘要和 hash；不持久化截图、OCR 全文和输入框 value。
- `include_values=false` 继续作为默认值，secure text 永远脱敏。
- 窗口身份优先使用系统 window id / AXIdentifier；缺失时用进程、标题、bounds 组合生成弱身份，并明确返回 `identity_strength`。
- observation 记录 `truncated` 时，客户端不能假设未返回元素不存在。

### 4.2 Execute Step

`desktop_execute_step` 包含：

- `observation_id`：动作依据的快照；
- `target`：element id 加语义属性（role/title/identifier/bounds）双重定位；
- `preconditions`：目标存在、可见、启用、值匹配等；
- `action`：click/input/scroll/drag/menu_select/file_dialog_choose；
- `expectation`：元素出现/消失/启用/值变化、窗口标题变化或 tree fingerprint 变化；
- `timeout_ms` 和 `retry`：服务端有硬上限；
- `idempotency_key`：防止客户端重试造成重复动作。

执行顺序固定为：校验 observation → 重新读取最小 UI 状态 → 重定位并比对目标 → 创建/复用 pending action → 用户确认 → 原子 claim → 执行一次 → 重新观察 → 验证 → 记录结果。

任何目标不唯一、窗口身份变化、前置条件不成立或 observation 过期都必须停止，并返回稳定错误码；不能猜测目标继续点击。

建议新增错误码：

```text
OBSERVATION_EXPIRED
WINDOW_CHANGED
TARGET_STALE
TARGET_AMBIGUOUS
PRECONDITION_FAILED
EXPECTATION_TIMEOUT
RETRY_EXHAUSTED
RECOVERY_REQUIRED
```

### 4.3 动态工作流

保留 3.x 的 `{"action": ..., "params": ...}` step。4.0 实际支持三种显式 `kind`：

```text
action       调用已有安全 action；观察和闭环操作分别调用 desktop_observe / desktop_execute_step
wait         每次 execute 只轮询一次只读 action，有明确次数和间隔上限
condition    根据较早步骤的受限结构化字段选择 then/else 普通 action
```

补偿不是独立 step kind，而是 action step 上预先声明的 `compensation` 字段。

规则：

- 仍禁止嵌套 workflow 控制 action。
- 最多 20 steps；条件分支只能落到普通 action，不允许递归分支；只读单步最多尝试 3 次，wait 最多轮询 20 次。
- 不提供通用表达式执行器。条件使用受限字段、比较运算符和 schema 校验。
- 不支持无界 loop；重复行为展开为带明确 `max_attempts` 的 retry。
- step 状态至少包含 `planned/running/waiting_confirmation/waiting_condition/completed/failed/compensating/cancelled`。
- workflow runner 使用可续租 run token 和 fencing；闭环桌面写操作使用显式 idempotency key。崩溃后只读步骤可恢复，结果不确定的写操作停在 `RECOVERY_REQUIRED`。

## 5. 内部架构改造

建议新增或拆分以下模块：

```text
src/xiaozhi_desktop_mcp/
  schemas.py                 显式 JSON Schema/类型定义，替代从描述字符串推断 schema
  policy.py                  风险、客户端权限、确认和敏感读取策略
  observations.py            observation 创建、TTL、指纹、差异计算
  execution.py               precondition -> act -> verify 状态机
  migrations/                SQLite 顺序迁移
  workflows_v2.py            兼容入口；内部委托给新状态机
  tools/accessibility.py     保留薄适配层和安全参数校验
```

### 5.1 Schema 与 Registry

- `ActionSpec.params` 从“描述字符串推断类型”迁移到显式 schema。
- action registry 继续是 HTTP/MCP/文档/策略的单一事实源。
- 增加 registry contract tests：action handler、schema、pending spec、MCP exposure 必须一致。
- 先提供兼容转换层，避免一次性重写所有 action。

### 5.2 SQLite 迁移

实际新增：

```text
schema_migrations
observations
idempotency_keys
workflow_events
workflows.run_token / workflows.lease_expires_at
```

迁移要求：

- schema version 从数据库读取，不依赖代码猜测。
- 每个 migration 在事务中执行，可重复启动但不可重复应用。
- 启动前检查磁盘与写权限；迁移失败时服务拒绝写操作并给出可操作错误。
- 3.x 数据必须保留；pending action 和 workflow 不允许静默丢失。
- 文档提供迁移前复制 state DB、迁移检查和回滚到 3.x 的限制说明。

### 5.3 Policy

将“动作影响”和“数据敏感度”分开：

- impact：`read / low / medium / denied`
- sensitivity：`public / local / screen / content / secret`

截图、OCR、Accessibility value 属于敏感读取，不再仅用 `low risk` 表达。4.0 默认仍允许可信 localhost 客户端使用当前能力；非 localhost 必须鉴权，且 token 可选配置 action scope。高风险目标即使客户端有 scope 也继续拒绝。

## 6. 分阶段实施

### M0：3.1 稳定与 4.0 设计冻结（第 1 周）

- 发布当前 perception/accessibility 为 `3.1.0`。
- 增加真实 Mac 只读 smoke：截图、OCR、UI tree、权限失败提示。
- 冻结 4.0 action schema、错误码、状态机和 SQLite migration ADR。
- 录制 Chrome、Finder、Obsidian、Xcode、Terminal 的最小 E2E 场景。

退出条件：3.1 无 P0/P1 回归；4.0 ADR 和 API 示例评审通过。

### M1：基础设施（第 2 周）

- 引入显式 schema 与 registry 兼容层。
- 建立 `schema_migrations`、迁移测试和 3.x 数据 fixture。
- 增加 idempotency store 和 execution event 模型。
- 建立 API v1/v2 golden contract tests。

退出条件：3.x 数据原地升级成功；重复迁移无副作用；所有旧 contract tests 通过。

### M2：Observe 与陈旧目标保护（第 3 周）

- 实现 `desktop_observe`、observation TTL、窗口身份和 tree fingerprint。
- 实现 observation diff、最小重观察和多条件语义重定位。
- 实现 stale/ambiguous/precondition 错误分类。
- 验证 screenshot/OCR/value 不进入日志、审计和默认持久化。

退出条件：UI 变化后旧 element id 不会误操作新元素；歧义目标 100% fail closed。

### M3：Act–Verify 闭环（第 4 周）

- 实现 `desktop_execute_step` 状态机。
- 接入 pending action、idempotency、timeout、有界 retry。
- 支持元素出现/消失/启用/值变化和窗口/tree 变化 expectation。
- 处理确认后窗口变化、执行中取消、进程崩溃和验证超时。

退出条件：相同 idempotency key 不重复执行；重启不会重放已经成功的写动作；失败均有稳定错误码和下一步建议。

### M4：动态 Workflow（第 5 周）

- 扩展 workflow schema，保持旧线性 step 兼容。
- 实现 wait、condition、branch、retry、compensation。
- 增加 step run/event 持久化、恢复、取消和并发 claim。
- 增加 workflow 总时限、step 数、分支深度和重试预算。

退出条件：等待确认和服务重启后能恢复；并发 execute 只有一个 owner；超预算安全停止。

### M5：安全与真实 App 可靠性（第 6 周）

- 加入客户端 action scope 和敏感读取策略元数据。
- 完成权限自检与引导：Screen Recording、Accessibility、Automation。
- 增加 Chrome/Safari、Finder、Obsidian、Xcode、Terminal E2E。
- 测试多窗口、弹窗、sheet、窗口关闭、App 重启和 Accessibility 缺失。
- 完成日志/DB 隐私扫描和 threat model 更新。

退出条件：安全测试和 E2E 门槛通过；默认配置不扩大 3.x 的危险能力边界。

### M6：Alpha → Beta → RC → GA（第 7 周）

- `4.0.0-alpha.1`：schema migration + observation。
- `4.0.0-beta.1`：act–verify + dynamic workflow，开始真实任务试跑。
- `4.0.0-rc.1`：API/DB schema 冻结，只修缺陷和文档。
- `4.0.0`：发布 migration guide、operations runbook、回滚说明和完整 changelog。

原计划要求 GA 前保留 3 个工作日 RC soak；本次无人使用实例按明确决定直接 GA，风险记录在状态段和 macOS E2E 报告中。

## 7. 测试与验收门槛

### 自动化测试

- 单元：fingerprint、locator、precondition、expectation、retry budget、policy、migration。
- 属性/参数化：随机 UI tree 变化不得把旧目标映射到错误元素。
- 并发：pending confirm、workflow execute、idempotency key 的竞争测试。
- 故障注入：动作前/动作后/DB commit 前后终止进程并恢复。
- Contract：v1/v2 旧请求、响应字段和 action 名 golden tests。
- 隐私：日志、audit、observation DB 中不存在截图 base64、输入文本、OCR 全文和 secure value。

### 真实 macOS E2E

每个 GA 必测 App 至少覆盖：观察、等待、执行、成功验证、陈旧目标拒绝、权限缺失。固定 E2E 场景连续运行 30 次：

- 不允许发生误点、重复写操作或越界路径访问；
- 无 UI 漂移时成功率不低于 95%；
- UI 漂移时必须安全停止或重新定位到唯一相同目标；
- 取消和超时后不得继续执行后续 step。

### 发布硬门槛

```bash
.venv/bin/python -m ruff check .
.venv/bin/python -m pytest -q
.venv/bin/python -m compileall -f src
DESKTOP_MCP_STATE_DB=/tmp/xiaozhi-smoke.db .venv/bin/python scripts/mac_smoke.py
```

此外必须满足：

- Python 3.10–3.13 CI 全绿；
- macOS smoke 与固定 E2E 全绿；
- 3.0/3.1 数据迁移 fixture 全绿；
- API compatibility、并发、故障恢复和隐私测试全绿；
- 无未关闭 P0/P1 缺陷。

## 8. 兼容、迁移与回滚

- `/api/v1` 和 `/api/v2` endpoint、envelope、已有 action 名保持兼容。
- 现有 `accessibility_action` 保留；新客户端推荐使用 `desktop_execute_step`。4.0 不删除旧 action。
- 现有线性 workflow 数据可继续读取和执行；新 step kind 只在 4.0 客户端显式使用。
- MCP stdio、Streamable HTTP 和 HTTP 启动命令保持不变。
- 新配置均提供安全默认值；旧 `.env` 可以直接启动。
- 升级前复制 state DB。4.0 数据库完成迁移后，不承诺 3.x 可直接写入同一文件；回滚需要恢复升级前备份。
- 先对本机 HTTP adapter 灰度，再升级 Java/小智桥接；桥接只依赖旧 action 时可独立回滚。

## 9. 风险与控制

| 风险 | 影响 | 控制措施 |
| --- | --- | --- |
| AX 树在不同 App/版本不稳定 | 误定位或失败 | observation TTL、双重定位、歧义即拒绝、App 显式 Driver |
| 确认后 UI 已变化 | 确认对象与执行对象不一致 | 确认记录绑定 observation/target fingerprint，执行前再校验 |
| 重试导致重复写操作 | 重复输入、重复提交 | idempotency key、step run 原子状态、写动作默认不自动重试 |
| SQLite 迁移损坏状态 | pending/workflow 丢失 | 事务 migration、fixture、备份、失败时只读降级 |
| 截图/OCR/value 泄露 | 隐私风险 | 默认不持久化、不审计响应值、敏感读取 scope、secure value 永久脱敏 |
| 动态 workflow 失控 | 长时间循环或越权 | 无界 loop 禁止、全局预算、每步 schema/policy、取消检查 |
| E2E 在 CI 中波动 | 阻塞发布或漏报 | 单元测试 mock + 固定本机/自托管 Mac E2E 分层，记录环境版本 |

## 10. 建议 Issue/Epic 拆分

```text
EPIC-40  4.0 Reliable Desktop Execution
  40-01  Release 3.1 perception/accessibility baseline
  40-02  Explicit ActionSpec schemas and contract tests
  40-03  SQLite migration framework and 3.x fixtures
  40-04  Observation store, TTL and privacy policy
  40-05  Stable window identity and semantic locator
  40-06  Tree diff, preconditions and expectations
  40-07  Idempotent execute-step state machine
  40-08  Pending confirmation bound to observation fingerprint
  40-09  Dynamic workflow schema and bounded runtime
  40-10  Crash recovery, concurrency and cancellation
  40-11  Client scopes and permission diagnostics
  40-12  macOS App E2E matrix and reliability report
  40-13  Migration, operations, security and client docs
  40-14  Alpha/Beta/RC/GA release engineering
```

## 11. Go / No-Go 检查

4.0 GA 只有在以下问题都能回答“是”时发布：

- 老客户端不改代码还能调用原有 v1/v2 action 吗？
- 一个确认动作能明确证明它操作的还是用户确认时看到的目标吗？
- 网络重试、并发确认和服务重启都不会重复执行写操作吗？
- UI 发生未知变化时系统会停下，而不是猜测点击吗？
- workflow 的步数、时长、分支、重试和权限都有硬边界吗？
- DB 升级前后数据可验证，失败时有明确恢复路径吗？
- 截图、OCR、输入文本和 secure value 不会进入日志或审计吗？
- 真实 Mac E2E 达到门槛，且没有 P0/P1 缺陷吗？

任意一项为“否”，延后 GA，不通过放宽安全边界换取按期发布。
