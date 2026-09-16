# 偷偷学（SS）日志记录系统设计文档

- 日期：2026-09-16
- 状态：已批准
- 分支：feat-logging-system-wm0cMM

## 1. 背景与目标

为项目建立一套完整专业的日志记录系统，覆盖前端（React/Vite GUI）与后端（FastAPI sidecar），实现日志文件的规范化存储、前端控制台全量捕获与可靠上传、后端分级记录与日志轮转，并通过功能测试与压力测试保证交付质量。

## 2. 需求要点

- 日志统一输出到项目根目录 `log/` 文件夹（不存在则自动创建）。
- 文件命名 `{服务类型}_{YYYYMMDD_HHMMSS}.log`，服务类型仅 `frontend` / `backend`，两类日志完全分离。
- 前端：完整捕获 console 全部方法输出（log/info/warn/error/debug），日志内容与浏览器控制台在格式、顺序、时间戳、完整性上一致；本地存储 + 定期上传，网络不稳定时保证完整性。
- 后端：分级日志 DEBUG / INFO / WARN / ERROR / FATAL；内容含毫秒级时间戳、级别、模块名、请求 ID、用户 ID（如适用）、详细信息；按大小（50MB）与每日自动切割。
- 交付前完成功能测试与压力测试，输出测试报告。

## 3. 架构

```
┌──────────────────────┐   POST /v1/logs/frontend   ┌─────────────────────────────┐
│ 前端 (React/Vite)     │ ─────────────────────────▶ │ 后端 FastAPI                 │
│ 全局捕获 console.*    │      批量日志条目(JSON)      │ ss/logging_setup.py 配置     │
│ IndexedDB 本地缓存     │                            │  └▶ log/frontend_*.log      │
│ 定时上传+失败重试       │                            │  └▶ log/backend_*.log       │
└──────────────────────┘   X-Request-ID 回传          └─────────────────────────────┘
```

关键决策（已与用户确认）：
1. 前端日志最终通过后端新端点上传落盘（浏览器/WebView 沙箱无法直接写本地文件）。
2. 轮转策略：大小轮转（50MB）+ 按天归档，保留最近 14 个文件。

## 4. 组件设计

### 4.1 后端日志核心 `ss/logging_setup.py`（新增）

职责：初始化全局日志配置。暴露 `setup_logging(project_root, level)` 与 `get_logger(name)`。

- 自动创建 `<project_root>/log/` 目录。
- 根 logger 及关键第三方 logger（uvicorn、uvicorn.error、uvicorn.access、httpx、httpcore）统一格式。
- 日志格式：

```
2026-09-16 14:30:05,123 [INFO] [ss.server.app] [req=a1b2] [user=-] 日志消息
```

- 级别：`CRITICAL` 对应需求的 FATAL 级（Python 标准库语义）。
- 轮转处理：自定义 `DailyRotatingSizeHandler(RotatingFileHandler)`：

  - 主文件 `backend_{YYYYMMDD_HHMMSS}.log`，启动时间戳。
  - `maxBytes` 默认 50MB（支持环境变量覆盖），超限切割为 `{主文件}.1`、`.2` …。
  - 跨日归档：检测文件日期变化后重命名旧文件（保留 mtime 命名 `{service}_{YYYYMMDD_HHMMSS}`），新建当日文件。
  - 清理：仅保留最近 14 个 backend 文件（环境变量覆盖）。

- 环境变量（测试与部署可覆盖）：

  - `SS_LOG_DIR`：日志目录（默认 `<project_root>/log`）。
  - `SS_LOG_LEVEL`：级别（默认 INFO）。
  - `SS_LOG_MAX_BYTES`：大小轮转阈值（默认 50MB）。
  - `SS_LOG_BACKUP_COUNT`：大小轮转备份份数（默认 5）。
  - `SS_LOG_KEEP_FILES`：按天归档保留文件数（默认 14）。

- contextvars：`request_id_var`、`user_id_var`；格式化器从 contextvars 取填充，无值显示 `-`。
- 返回与全局 handler 相同格式的记录方法，供 get_logger(name) 使用。

### 4.2 请求上下文中间件（扩展 `ss/server/app.py`）

- 新增 `RequestContextMiddleware`，位于现有 token 中间件之前执行：

  - 为每个请求生成短随机 request id（如 `secrets.token_hex(3)`），`request_id_var` 写入 contextvar。
  - 响应头回传 `X-Request-ID`。
  - 用户 ID：优先取 `X-SS-Actor` 请求头（board 场景），其次 `profile_id` 查询参数，无则 `-`；写入 `user_id_var`。
  - `finally` 清除 contextvar，防止跨请求泄漏。

### 4.3 前端日志接收端点 `POST /v1/logs/frontend`（扩展 `app.py`）

- 认证走现有 token 中间件（前端 `api.ts` 自动注入 `X-SS-Token`）。
- 请求体：

```json
{
  "logs": [
    { "ts": "2026-09-16T14:30:05.123Z", "level": "INFO", "message": "页面加载完成", "stack": null }
  ]
}
```

- 校验：数组长度 1~10000；每条必含 `ts`（ISO 时间戳字符串）与 `message`（string）；`level` 限白名单 `DEBUG/INFO/WARN/ERROR/FATAL`；非法条目跳过并计数。
- 落盘：写入 `log/frontend_{启动时间戳}.log`，每行格式与前端 console 输出一致：

```
2026-09-16 14:30:05,123 [INFO] 页面加载完成
```

  栈信息（stack）附加在 message 行后。
- 复用 4.1 的轮转机制（frontend 文件同样 50MB/按日切割）。
- 响应：`{ "accepted": n, "skipped": m, "rotated": bool }`。

### 4.4 启动接线（`ss/server/run.py`）

- `main()` 中于 build_app 前调用 `setup_logging(project_root, level)`，project_root 取自 `--cwd`（未提供则退回当前工作目录）。

### 4.5 前端日志模块（新增 `surfaces/gui/src/lib/logger.ts`）

职责：捕获、缓存、上传。导出 `initLogCapture()` 与 `flushLogs()`。

- 捕获：模块启动时保存原始 console 方法引用，包装后：

  - 统一生成毫秒级时间戳（`YYYY-MM-DD HH:MM:SS,mmm`）。
  - 组装 `[LEVEL] 消息` 行，将多参数与对象格式化（JSON.stringify、Error 转 stack）为完整消息。
  - 先调用原始 console 方法（保持控制台原行为与输出顺序），再推入本地缓存。
  - 额外捕获 `window.onerror`（含 stack）与 `unhandledrejection`。
  - 仍将完整日志行输出到 `console.debug` 便于开发排障（记录为 DEBUG 条目）。

- 缓存（IndexedDB，objectStore `entries`，keyPath 自增序号）：

  - 写入失败（如隐私模式）自动退化为内存队列。
  - 上限保留最近 5000 条，超出丢弃最旧。

- 上传：定时（30s）或积累 20 条触发批量 `POST /v1/logs/frontend`：

  - 成功后从 IndexedDB 删除已上传条目。
  - 失败保留，指数退避重试：300ms → 30s → 60s … 上限 5min。
  - 会话启动时回放（上传）本地残留日志。

### 4.6 启动接入（`surfaces/gui/src/main.tsx`）

- `initI18n().finally(...)` 渲染前调用 `initLogCapture()`。

## 5. 数据流

1. 前端 console 调用 → logger 包装层 → 原始 console（对外即时可见）+ IndexedDB 队列。
2. 定时/条数触发 → `POST /v1/logs/frontend`（带 token）→ 后端校验 → `log/frontend_*.log`。
3. 后端各模块 `get_logger(__name__).info(...)` → contextvar request_id/user_id → `log/backend_*.log`。
4. 任意日志文件超 50MB/跨日 → 切割/归档 → 清理超过保留数的旧文件。

## 6. 错误处理

- 日志目录创建失败（权限等）：降级到临时目录继续记录，不影响业务。
- 前端上传失败：本地缓存保留 + 指数退避重试；IndexedDB 不可用走内存队列。
- 后端接收端点校验失败条目：跳过并计数，不整体拒绝。
- contextvar 未设置：req/user 显示 `-`。

## 7. 测试策略

### 7.1 后端功能测试（pytest）

- 文件：`tests/test_logging.py`、`tests/test_log_endpoints.py`。
- 用例：
  - 目录自动创建、主文件命名 `backend_{YYYYMMDD_HHMMSS}.log`。
  - 格式包含毫秒时间戳、级别、模块、req、user。
  - 环境变量覆盖（SS_LOG_DIR/MAX_BYTES 等）生效。
  - 大小轮转触发 `.1` 备份；按日归档（mock datetime）；保留清理。
  - 中间件：request id 生成与 `X-Request-ID` 响应头；user_id 推导。
  - 端点：token 认证 401；合法/非法载荷；落盘格式；frontend 文件命名。
  - 并发（asyncio 多任务）写入不丢行不交错。
- 隔离：`isolated_state_dir` autouse fixture 已隔离状态；新增自动清理 logger 配置的 fixture。

### 7.2 前端功能测试（vitest + jsdom）

- 文件：`surfaces/gui/src/lib/__tests__/logger.test.ts`。
- 用例：
  - console 五种方法全部捕获，顺序与原调用一致，时间戳格式正确。
  - window.onerror / unhandledrejection 捕获 stack。
  - 缓存入队、超限丢弃最旧。
  - 上传时序：条数触发/定时触发（fake timers）；成功删除条目。
  - 失败重试：mock fetch 失败，退避时间递增，恢复成功后续传。

### 7.3 压力测试

- 后端：循环写入 10 万条，断言吞吐量（ms/条）与轮转切割正确。
- 前端：构造 1 万条日志模拟上传，断言无丢条目。
- 标记 `@pytest.mark.stress`，默认 CI 之外运行。

### 7.4 测试报告

- 文档：`docs/logging-system-test-report.md`，包含测试用例清单、结果、性能指标。

## 8. 分阶段提交计划（每阶段提交并推送，禁止推主分支）

| 阶段 | 内容 | 提交类型 |
|------|------|---------|
| 1 | 本设计文档 | docs |
| 2 | 后端日志核心 + 请求中间件 | feat |
| 3 | 前端日志接收端点 | feat |
| 4 | 前端捕获与本地缓存 | feat |
| 5 | 前端定期上传与重试 | feat |
| 6 | 功能测试 + 修复 | test |
| 7 | 压力测试 + 测试报告 | test + docs |

## 9. 关键决策记录

- FATAL 级别使用 Python 标准库 `CRITICAL` 实现。
- 轮转归档文件带 `.1`/日期后缀；主文件严格满足 `{service}_{YYYYMMDD_HHMMSS}.log`。
- 前端本地存储采用 IndexedDB（上限 5000 条），上传成功即删除。
- 新增 `POST /v1/logs/frontend` 复用现有 token 认证。