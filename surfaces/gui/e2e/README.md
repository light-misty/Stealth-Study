# E2E 测试 (Playwright)

GUI 的端到端回归测试。它们在 Chromium 中驱动真实应用，但具有**封闭性**：
所有 `/v1` 请求和事件 WebSocket 都在网络层被 mock，因此测试**无需
Python 后端**即可运行，结果具有确定性，且永远不会改变真实状态。

## 运行

```bash
npm run e2e          # 无头模式
npm run e2e:ui       # Playwright UI 模式 (watch/inspect)
npx playwright test e2e/settings.spec.ts   # 运行单个 spec
```

## Live冒烟测试（非 CI）

`npm run e2e:live` 运行 `e2e-live/`（使用单独的 `playwright.live.config.ts`）针对**:8765 上的真实**
后端。两种模式，当后端不可用时都会自动跳过：

- **API-shape 冒烟测试** (`api-smoke.spec.ts`) — 不使用模型 token，无凭据。断言 `/v1/health` 和
  `/v1/providers` 返回 GUI 所读取的结构，用于捕获 mock 与真实后端之间的漂移。
  足够轻量，可在 sidecar 运行时随时执行。
- **完整垂直测试** (`fib.spec.ts`, …) — 要求一个新的 Cowork 会话生成 `fib.md` 并
  验证文件落盘。需要配置模型，结果非确定性，每次运行消耗少量 token。
  覆盖了封闭 spec 所 mock 的垂直流程：模型连接、tool/approval 循环、
  文件 I/O 以及 WebSocket 流式传输。

配置文件 (`playwright.config.ts`) 在端口 **5199** 上启动 Vite
开发服务器（专用端口，避免与 5173 上运行的 `npm run dev` 冲突），如果已启动则复用。

## mock 工作原理

`e2e/fixtures.ts` 导出一个 `test`，其 `page` 在导航前已安装 `mockApi()`：

- `page.route("**/v1/**", …)` 根据路径名和方法分派到结构镜像真实后端的 fixture
  （从实时服务器捕获）。未知端点返回一个有效但为空的主体。
- 变更保存在各测试独立的内存状态中，因此在重新获取时能通过真实 UI 反映出来：
  sessions（归档/重命名/删除）、personas（启用/表面/删除 — 启用意味着表面，
  与后端的语义一致）inbox 项 + 路由绑定、roots、channel subscriptions。
- 会话 WebSocket (`routeWebSocket`) 是一个**脚本化的伪 agent**，使用真实的
  `{type, data}` 事件协议：连接时发送 `ready`；发送 `user_message` 后触发 `turn_start` → deltas →
  `assistant_message "Echo: <text>"` → `turn_done`；包含 **"run a tool"** 的消息会触发
  `tool_proposal` + `permission_required`，并挂起直到客户端的 `approval` 决策
  到达。这使得 send/stream/approve 生产代码路径可以零模型成本运行。
- 值得了解的种子数据：固定的会话 "Draft the launch note" 是最新的（启动恢复
  目标）；7 个未固定的 "Weekly plan N" cowor k 会话用于测试侧边栏预览上限；两个待处理的
  Inbox 项（cowork 上的审批、ops 上的问题）驱动 Inbox 过滤器；`acme-notes` 是一个
  已禁用的非内置 persona，用于 enable/delete 流程。Provider 以三种状态种子化
  （OpenAI 已配置+已使用，Anthropic 已配置-未使用，Z AI 未配置但预填充了端点）—
  `POST /v1/providers` 在保存时翻转 `configured` 状态，`/verify` 在 key 包含 "bad" 时失败。
  一个自动化任务（"Daily AI News"）有一个正在运行的 run — `POST .../run` 追加一个 run，`PATCH`/`DELETE`
  切换和移除。

- **种子化 transcript**：每个会话的 `GET /v1/sessions/{id}/messages` 返回 `[]`，因此
  重新打开时从空白开始。`seedSessionMessages(page, sessionId, messages)`（从
  fixtures 导出）注册一个后注册的、优先级更高的路由，为单个会话预置完整的重放历史 —
  tool_calls + `role:"tool"` 结果（通过 `tool_call_id` 关联）、`_display`
  侧栏、`reasoning`、`notice` 标记、connector `source` 消息。使用它来断言
  重新打开的路径（`itemsFromMessages`）— 重放的步骤组、connector 卡片、尾部错误
  Retry — 这些是实时 echo 驱动测试无法覆盖的。参见 `seeded-history.spec.ts`。

## 添加 spec

```ts
import { test, expect } from "./fixtures";

test("…", async ({ page }) => {
  await page.goto("/");
  // 交互 + 断言
});
```

如果某个流程读取了新端点，请在 `fixtures.ts` 中添加对应的 fixture 和路由分支 — 通用兜底
返回 `{}`，这会崩溃期望数组的组件（例如 persona 的 `recommends`）。优先使用
`getByRole`，但注意某些控件（Sources 栏、✕ 删除按钮）的可访问名称来自
内部内容 — 这些需要使用 `getByTitle`/`getByLabel` 来定位。
```
