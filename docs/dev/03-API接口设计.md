# 03 API 接口设计 — campus REST 契约

| 项 | 内容 |
|---|---|
| 文档编号 | dev/03 |
| 版本 | v1.0 |
| 日期 | 2026-09-08 |
| 作者 | 徐名可 |
| 上游依据 | `docs/PRD-CampusLearning.md` v1.1（66 条需求池 §4.8）、`docs/dev/01-系统架构设计.md` §2.1/§4.2/ADR-07、`docs/dev/02-数据库设计.md`（数据契约） |
| 读者 | 后端工程师 / 前端工程师 / QA |
| 关联文档 | `04-前端设计.md`（`campus/api.ts` 函数清单）、`07-开发任务分解.md`（T 系列） |

---

## 1. 总体约定

| 约定 | 规则 |
|---|---|
| Base URL | 与既有 API 同源：`http://127.0.0.1:<sidecar-port>`（前端经 `window.__COWORKER_HTTP__` 注入，`api.ts:8-14` 同款解析） |
| 路径前缀 | 全部端点挂 `APIRouter(prefix="/v1/campus")`，与既有 180 条 `/v1/*` 路由零冲突 |
| 鉴权 | 沿用既有 `X-StealthStudy-Token` 头（`server/app.py` 的 `_request_authenticated`）。campus 端点**不加入** `tokenless_paths` 白名单，自动受保护，campus 不自建鉴权 |
| 方法语义 | GET 读（无副作用）；POST 建/触发动作；PATCH 部分更新（只发变更字段）；DELETE 删。**不使用 PUT**（与既有路由风格一致） |
| 请求/响应体 | JSON（`Content-Type: application/json`）。资源对象的字段定义**引用 02 文档 §4 的表结构**（`camelCase` 由前端 TS 类型转换，后端保持 snake_case——与既有 `api.ts` 现状一致，前端 hook 层做一次映射） |
| 时间 | 请求/响应中的时间均为 ISO 8601 UTC 字符串；日期为 `YYYY-MM-DD` |
| 分页 | 列表端点统一 `?page=1&page_size=50`，响应含 `{"items": [...], "total": n, "page": p, "page_size": s}`。错题本/题库/批改历史适用 |
| 幂等 | POST 幂等键：导入/创建类端点接受可选 `Idempotency-Key` 头，重复提交返回首次结果（防资料重复导入） |
| AI 超时 | 涉及模型调用的端点统一超时 **60s**（长任务可放宽至 120s），超时返回 `504` + `MODEL_TIMEOUT`，不无限等待（PRD §7.1 "超时 + 可中断"） |

**错误响应体（统一格式）**：FastAPI `HTTPException` 的 `detail` 允许传 dict，campus 全部用它返回结构化错误，与既有路由（detail 为字符串）向后兼容：

```json
{ "detail": { "code": "DOC_NOT_READY", "message": "资料尚未解析完成", "retryable": true } }
```

全部错误码见 §6。

---

## 2. 挂载落点（侵入点 #9，唯一一处既有文件改动）

位置：`coworker/server/app.py` 的 `create_app()` 内，**`app = FastAPI(title="coworker", version="0.0.0", lifespan=lifespan)`（`:187`）之后、`tokenless_paths` 定义之前**：

```python
# --- StealthStudy 备考台路由（PRD v1.1 / dev-01 ADR-07）：单点挂载，随 include_router 完成初始化 ---
from ..campus.routes import build_campus_router
app.include_router(build_campus_router(manager))
```

要点：

1. `build_campus_router(manager)` 在构造 `CampusService` 时执行 `CampusStore.migrate()`（02 文档 §3.4 "路由挂载即初始化"），**不触碰 `manager.py` 的 store 初始化序列**。
2. import 放在函数体内而非文件顶部（与 `app.py` 现有风格一致——该文件大量函数内 import，避免顶层依赖膨胀）。
3. `manager` 只被 `automation_templates.py`（TaskStore CRUD）与 audit 路径引用；campus 不读写 manager 的引擎状态。
4. 迁移失败时 `include_router` 抛异常 → 应用启动失败 + 明确错误日志（PRD §7.6 "不静默失败"）。

---

## 3. WebSocket 结论：**复用既有通道，campus 不新增 WS**

**结论**：V0.1 不新建任何 WebSocket 端点。理由与替代：

| 考量 | 结论 |
|---|---|
| 交互模式 | campus 全部交互是短请求-响应（CRUD + 一次性 AI 调用），无服务端主动推送刚需，REST 语义足够 |
| 长任务（资料解析 / 批改 / 出题） | 解析与批改是**秒级到分钟级**一次性任务：资料解析用前端轮询 `GET /library/{doc_id}`（1.5s 间隔，读到 `ready/failed` 即止）；批改走同步请求 + 前端超时可中断（§1 AI 超时）。**不做后台任务队列**，请求线程内完成（与 engine 的 `asyncio.to_thread` 模式一致） |
| 既有 WS 的语义 | 既有通道（`broadcast_session`，`manager.py:4957-4968`）绑定 `session_id`，事件类型为对话流事件；campus 无 session 概念，强行复用会造成事件语义污染 |
| 自动化任务完成通知 | CERT-13 走应用内提醒（ADR-12）：`once` 任务触发后产出 Inbox 条目，**沿用既有 Inbox 通道呈现**，campus 不复制通知逻辑 |
| 未来扩展位 | 若 V0.2 需要细粒度解析进度推送，再议在既有 WS 上追加 `campus_*` 事件类型（复用通道、新增事件名），本契约不预留字段 |

前端 `campus/api.ts` 因此**不需要 WebSocket 客户端**，仅 REST（`04-前端设计.md` §5）。

---

## 4. 接口契约表

> 格式：`方法 路径` ｜ 请求体（字段摘要）｜ 响应体 ｜ 错误码 ｜ 对应需求 ID。
> 资源字段定义见 02 文档 §4；下表只列交互形状。`profile_id` 是几乎所有端点的公共参数（多档案隔离横切约束，缺失即 400 `PROFILE_REQUIRED`）。

### 4.1 全局与设置（G-01~G-06、G-09、G-14）

| # | 端点 | 请求 | 响应 | 错误 | 需求 |
|---|---|---|---|---|---|
| A1 | `GET /v1/campus/profiles` | query: `track?`, `status?` | `{items: ExamProfile[]}` | — | G-02/G-03 |
| A2 | `POST /v1/campus/profiles` | `{track_type, title, exam_date?, target_score?, subjects?, cert_type?, level?, daily_minutes?}` | ExamProfile | `DUPLICATE_TITLE` | G-03 |
| A3 | `GET /v1/campus/profiles/{pid}` | — | ExamProfile | `PROFILE_NOT_FOUND` | G-03 |
| A4 | `PATCH /v1/campus/profiles/{pid}` | 任意可变字段（`exam_date/target_score/status/...`） | ExamProfile | `PROFILE_NOT_FOUND`, `PROFILE_READ_ONLY`（finished） | G-03/KY-04 |
| A5 | `DELETE /v1/campus/profiles/{pid}` | — | `{deleted: true, cascade: {表: 行数}}` | `PROFILE_NOT_FOUND` | G-03（级联见 02 §7.3） |
| A6 | `GET /v1/campus/app-state` | — | `{active_profile_id?, settings}` | — | G-03/G-09 |
| A7 | `PATCH /v1/campus/app-state` | `{active_profile_id?}`, `{settings?}`（每日时长/推送时间/间隔强度/三类任务模型） | 同 A6 | `PROFILE_NOT_FOUND` | G-09 |
| A8 | `GET /v1/campus/capabilities` | — | `{current_model, tasks: [{task, recommended, minimum, supported: bool, reason}]}`（静态推荐清单判定，ADR-06） | — | G-03 自检卡/§7.1 |
| A9 | `GET /v1/campus/privacy` | — | `{data_dir, library_dir, db_size_bytes, model_endpoints[]}` | — | G-03 隐私面板 |
| A10 | `DELETE /v1/campus/privacy/data` | — | `{cleared: true, freed_bytes}` | — | G-03 一键清除本地数据 |

### 4.2 资料库与按页问答（G-07/G-10/G-11、KY-09/KY-10）

| # | 端点 | 请求 | 响应 | 错误 | 需求 |
|---|---|---|---|---|---|
| B1 | `POST /v1/campus/library/import` | multipart：`file`（PDF/MD/TXT，≤10MB 与 attachments 上限一致）+ `profile_id` | SourceDoc（`parse_status=pending`） | `FILE_TOO_LARGE`, `UNSUPPORTED_TYPE`, `DISK_FULL` | G-10 |
| B2 | `GET /v1/campus/library` | query: `profile_id`, `parse_status?` | `{items: SourceDoc[]}` | — | G-07 |
| B3 | `GET /v1/campus/library/{doc_id}` | — | SourceDoc | `DOC_NOT_FOUND` | G-10（解析状态轮询） |
| B4 | `DELETE /v1/campus/library/{doc_id}` | — | `{deleted: true}` | `DOC_NOT_FOUND` | G-11（级联 chunk+文件） |
| B5 | `POST /v1/campus/library/{doc_id}/retry` | — | SourceDoc | `DOC_NOT_FOUND`, `DOC_SCAN_EMPTY` | G-10 |
| B6 | `POST /v1/campus/qa` | `{profile_id, doc_id?, question}` | `{answer, citations: [{doc_id, page_no, snippet}], used_retrieval: "toc_route"\|"keyword", chunks_used: n}` | `DOC_NOT_READY`, `DOC_SCAN_EMPTY`, `MODEL_NOT_CONFIGURED`, `MODEL_TIMEOUT` | KY-09（L1 目录路由/L2 关键词，02 §5.2） |
| B7 | `POST /v1/campus/qa/generate-questions` | `{profile_id, doc_id?, point_id?, count=5}` | `{items: QuestionBankItem[]}` | 同 B6 | KY-10/CERT-06 |

### 4.3 批改（CET-09/10、CERT-07/14、KY-05/06、G-15；共享端点）

| # | 端点 | 请求 | 响应 | 错误 | 需求 |
|---|---|---|---|---|---|
| C1 | `POST /v1/campus/grading` | `{profile_id, question_id?, kind: "essay"\|"translation"\|"short_answer"\|"essay_material"\|"lesson_plan"\|"practical", answer, rubric_id?, custom_rubric?}` | GradeResult（见下）+ `attempt_id` | `MODEL_NOT_CONFIGURED`, `MODEL_TIMEOUT`, `RUBRIC_NOT_FOUND`, `PROFILE_READ_ONLY` | CET-09/10、CERT-07/14、KY-05/06 |
| C2 | `GET /v1/campus/grading/{attempt_id}` | — | attempt（含 grading_json, degrade_level） | `ATTEMPT_NOT_FOUND` | CET-04 批改结果回看 |
| C3 | `GET /v1/campus/grading/history` | query: `profile_id`, `subject?`, `kind?`, 分页 | 分页 attempt 列表 | — | CET-12/CERT-07 |
| C4 | `GET /v1/campus/grading/common-errors` | query: `profile_id`, `kind?` | `{top3: [{type, count, samples}]}` | — | CET-12（≥3 次批改后非空） |

`GradeResult` 形状（与 `attempt.grading_json` 同构，02 §4.13）：

```json
{
  "attempt_id": "…",
  "degrade_level": 0,
  "rubric": "四六级作文四档评分",
  "dimensions": [{ "name": "内容", "score": 12, "max": 15, "comment": "…" }],
  "errors": [{ "original": "I thinks", "suggestion": "I think", "type": "主谓一致", "offset": 12 }],
  "model_answer_outline": "…",
  "model_used": "openai:gpt-5.5",
  "notice": null
}
```

`degrade_level∈{0,1,2,3}`；≥1 时 `notice` 必须非空（如"评分仅供参考（弱模型或解析降级时）"，PRD v1.1 B 类①），前端强渲染。

### 4.4 错题本与复习队列（G-16/G-17、CERT-08/09、CET-05）

| # | 端点 | 请求 | 响应 | 错误 | 需求 |
|---|---|---|---|---|---|
| D1 | `GET /v1/campus/mistakes` | query: `profile_id`, `attribution?`, `resolved?`, `point_id?`, `track_type?`, 分页 | 分页 MistakeBook | — | G-16/CERT-08 |
| D2 | `PATCH /v1/campus/mistakes/{id}` | `{attribution?, note?, resolved?, point_id?}` | MistakeBook | `INVALID_ATTRIBUTION` | CERT-08（用户改归因） |
| D3 | `GET /v1/campus/mistakes/stats` | query: `profile_id` | `{distribution: {attribution: count}, top_attribution}` | — | CERT-09 |
| D4 | `POST /v1/campus/review/items` | `{profile_id, item_type, item_id}` | ReviewQueueItem | `ITEM_NOT_FOUND` | CERT-03/CET-02 |
| D5 | `GET /v1/campus/review/due` | query: `profile_id`, `as_of?` | `{items: [{...ReviewQueueItem, payload}]}`（payload 内联错题/词卡/知识点内容） | — | CET-05/G-17 |
| D6 | `POST /v1/campus/review/{rq_id}/result` | `{correct: bool}` | ReviewQueueItem（新 interval/streak/due_at） | `RQ_NOT_FOUND` | CET-05（SM-2，02 §4.15） |
| D7 | `POST /v1/campus/review/attributions` | `{profile_id, attempt_ids: []}` | `{items: [{attempt_id, suggestion, confidence_note}]}`（AI 建议归因，**只建议不落库**） | `MODEL_NOT_CONFIGURED` | CERT-08（v1.1 B④：AI 建议、用户确认） |

### 4.5 题库与作答（CERT-02/04/05、CET-03、KY-08）

| # | 端点 | 请求 | 响应 | 错误 | 需求 |
|---|---|---|---|---|---|
| E1 | `POST /v1/campus/questions/import` | `{profile_id, format: "md"\|"csv", content}` | `{imported, skipped, items}` | `PARSE_ERROR`（行号定位） | CERT-04 |
| E2 | `GET /v1/campus/questions` | query: `profile_id`, `point_id?`, `qtype?`, `subject?`, 分页 | 分页 QuestionBankItem | — | CERT-05 |
| E3 | `POST /v1/campus/questions` | `{profile_id, ...题面字段}` | QuestionBankItem | `POINT_NOT_FOUND` | 手动录题 |
| E4 | `PATCH /v1/campus/questions/{qid}` / `DELETE` | 同上 | QuestionBankItem / `{deleted}` | — | 录入修正 |
| E5 | `POST /v1/campus/attempts` | `{profile_id, question_id, session_type?, mock_exam_id?, answer}` | Attempt（客观题即判分返回 `is_correct` + 标准答案；主观题返回 `pending_grading` 并同步调 C1 链路） | `QUESTION_NOT_FOUND`, `PROFILE_READ_ONLY` | CERT-05/KY-08/CET-03 |

### 4.6 CET 备考台（CET-01/02/04/06/13/14）

| # | 端点 | 请求 | 响应 | 错误 | 需求 |
|---|---|---|---|---|---|
| F1 | `POST /v1/campus/assessments` | `{profile_id}` | Assessment（含 20 题，`status=draft`） | `EXAM_DATE_REQUIRED`（生成计划时）, `MODEL_NOT_CONFIGURED` | CET-01 |
| F2 | `GET /v1/campus/assessments/{id}` | — | Assessment（续做恢复） | `ASSESSMENT_NOT_FOUND` | CET-01（可中断续做） |
| F3 | `PATCH /v1/campus/assessments/{id}` | `{answers: {qid: answer}}`（增量） | Assessment | `ASSESSMENT_FINISHED` | CET-01 |
| F4 | `POST /v1/campus/assessments/{id}/finish` | — | `{scores, estimate_total, gap_table}`（分项与 425 差距） | `ASSESSMENT_FINISHED`, `MODEL_TIMEOUT` | CET-01/02 |
| F5 | `POST /v1/campus/plans/generate` | `{profile_id}`（读取 exam_date/target/薄弱项） | `{plan_id, task_count, first_date}` | `EXAM_DATE_REQUIRED`, `MODEL_NOT_CONFIGURED`, `MODEL_TIMEOUT` | CET-03/KY-01/02（按 TrackSpec 分台） |
| F6 | `GET /v1/campus/vocab/today` | query: `profile_id` | `{new_items: VocabItem[], review_items: [...]}` | — | CET-04 |
| F7 | `PATCH /v1/campus/vocab/{id}` | `{mastery: "known"\|"fuzzy"\|"unknown"}` | VocabItem（"不认识"自动入复习队列） | — | CET-04 |
| F8 | `POST /v1/campus/vocab/import` | `{profile_id, format: "csv"\|"md", content}` | `{imported, skipped}` | `PARSE_ERROR` | CET-06 |
| F9 | `POST /v1/campus/vocab/mnemonic` | `{vocab_id}` | `{mnemonic}`（写入 memories 走既有工具链） | `MODEL_NOT_CONFIGURED` | CET-04 |
| F10 | `POST /v1/campus/mock-exams` | `{profile_id, paper_title}` | MockExam（`current_stage=writing`, `stage_deadline` 已算好） | `PROFILE_READ_ONLY` | CET-13 |
| F11 | `GET /v1/campus/mock-exams/{id}` | — | MockExam（刷新后恢复计时：服务端时间重算） | `MOCK_NOT_FOUND` | CET-13 验收 2 |
| F12 | `POST /v1/campus/mock-exams/{id}/stage` | `{to: "listening"\|"reading_translation"}` | MockExam（推进 + 锁定前序阶段 `locked_stages`） | `ILLEGAL_STAGE`, `STAGE_LOCKED` | CET-13 验收 1 |
| F13 | `POST /v1/campus/mock-exams/{id}/pause` | — | MockExam（累计 `paused_seconds` ≤180，超限 409） | `PAUSE_EXCEEDED` | CET-13 |
| F14 | `POST /v1/campus/mock-exams/{id}/submit` | — | `{estimate_score, by_section, attempt_ids}` | `MOCK_SUBMITTED` | CET-14 |

### 4.7 考研备考台（KY-01/02/04/11/12/13/14）

| # | 端点 | 请求 | 响应 | 错误 | 需求 |
|---|---|---|---|---|---|
| G1 | `GET /v1/campus/tasks` | query: `profile_id`, `date?`, `status?`, `track?` | `{items: PlanTask[]}` | — | KY-11/自建看板（ADR-11） |
| G2 | `PATCH /v1/campus/tasks/{id}` | `{status?, scheduled_date?, priority?}` | PlanTask | `ILLEGAL_TRANSITION`（按 PRD §6.4 状态机校验） | KY-13/看板拖卡写回（campus 自建看板） |
| G3 | `POST /v1/campus/plans/{plan_id}/reschedule` | `{new_exam_date?}` | `{rescheduled, preserved_done: n}` | — | KY-04/KY-13（todo 重排，done 不动） |
| G4 | `GET /v1/campus/progress` | query: `profile_id` | `{by_track: {track: {done, total, rate}}, streak_days, heatmap: [{date, count}]}` | — | KY-11 |
| G5 | `POST /v1/campus/weekly-reports/generate` | `{profile_id}`（手动触发生成；cron 触发走 automation 模板） | WeeklyReport | `NO_TASK_DATA` | KY-12 |
| G6 | `GET /v1/campus/weekly-reports` | query: `profile_id` | `{items: WeeklyReport[]}` | — | KY-12 |
| G7 | `GET /v1/campus/school-profile` | query: `profile_id` | SchoolProfile | — | KY-14 |
| G8 | `PATCH /v1/campus/school-profile` | 任意字段 | SchoolProfile | — | KY-14 |
| G9 | `POST /v1/campus/school-profile/extract` | `{profile_id, text}`（粘贴简章） | `{prefill: {school?, major?, subjects?, ...}, confidence}` | `MODEL_NOT_CONFIGURED` | KY-14（抽 ≥3 字段） |

### 4.8 证书备考台（CERT-01/02/03/11/12/13）

| # | 端点 | 请求 | 响应 | 错误 | 需求 |
|---|---|---|---|---|---|
| H1 | `GET /v1/campus/knowledge-tree` | query: `profile_id` | `{roots: KnowledgePoint[]}`（含 children 嵌套 + question_count/mistake_count） | — | CERT-01 |
| H2 | `POST /v1/campus/knowledge-points` | `{profile_id, parent_id?, title, desc?, order_index?}` | KnowledgePoint | `POINT_NOT_FOUND` | CERT-01 |
| H3 | `PATCH /v1/campus/knowledge-points/{id}` / `DELETE` | 同上 / — | KnowledgePoint / `{deleted, orphaned_children: n}`（子节点提升为未分类） | — | CERT-01 验收 3 |
| H4 | `POST /v1/campus/knowledge-tree/generate` | `{profile_id, text}` 或 `doc_id`（考纲 PDF） | `{created: n, roots: [...]}` | `MODEL_NOT_CONFIGURED`, `MODEL_TIMEOUT` | CERT-02（≥2 层 ≥15 节点） |
| H5 | `PATCH /v1/campus/mastery` | `{profile_id, point_id?, dimension?, level}` | Mastery（UPSERT） | `INVALID_LEVEL` | CERT-03 |
| H6 | `GET /v1/campus/mastery/coverage` | query: `profile_id` | `{coverage: 0.xx, weak_top5: [{point_id, title, level}]}` | — | CERT-03 |
| H7 | `POST /v1/campus/deadlines` | `{profile_id, node_type, date, is_reference?}` | CertDeadline | `DUPLICATE_NODE` | CERT-11/12 |
| H8 | `GET /v1/campus/deadlines` | query: `profile_id` | `{items: [{...CertDeadline, days_left}]}` | — | CERT-11 |
| H9 | `POST /v1/campus/deadlines/{id}/reminders` | — | `{automation_ids: [3个]}`（once 任务 D-30/D-7/D-1，经既有 TaskStore CRUD） | `AUTOMATION_UNAVAILABLE` | CERT-13 |
| H10 | `GET /v1/campus/reminders` | query: `profile_id` | `{banner: DeadlineView[], expired: [...]}`（应用内横幅数据源，ADR-12） | — | CERT-13 验收（打开应用即见） |

### 4.9 自动化模板、人设与导出（G-12/G-13/G-18、INF-02）

| # | 端点 | 请求 | 响应 | 错误 | 需求 |
|---|---|---|---|---|---|
| I1 | `GET /v1/campus/personas` | — | `{items: [{id, name, icon, tagline, available}]}`（registry 只读过滤） | — | G-12 |
| I2 | `GET /v1/campus/automation-templates` | — | `{items: [{id, title, cron_desc, kind}]}`（4 模板） | — | G-18 |
| I3 | `POST /v1/campus/automation-templates/{tpl_id}/install` | `{profile_id}` | `{task_ids: [...]}` | `MODEL_NOT_CONFIGURED`（周报模板需要模型） | G-18/CET-05/KY-12/CERT-13 |
| I4 | `POST /v1/campus/exports` | `{profile_id, format: "md"\|"json"\|"csv"}` | `{filename, path}`（落 `campus/exports/`） | `PROFILE_NOT_FOUND` | INF-02 |
| I5 | `GET /v1/campus/exports/{filename}` | — | 文件流（`Content-Disposition` 附件下载） | `EXPORT_NOT_FOUND` | INF-02 |
| I6 | `POST /v1/campus/exports/wipe` | `{restore_filename?}`（缺省为纯清除；给出时清库后按 02 §7.4 恢复该 json 导出包，07 §2 INF-03"I6 为 I4 的逆过程"） | `{wiped: true}`（恢复时另含 `restored`/`schema_migration`） | `EXPORT_NOT_FOUND`、`PARSE_ERROR`、`SCHEMA_VERSION_ERROR` | PRD §7.3/INF-03 |

**端点合计**：A10 + B7 + C4 + D7 + E5 + F14 + G9 + H10 + I6 = **72 个**。

---

## 5. 需求覆盖矩阵（66 条需求 → 端点）

| 需求组 | 覆盖端点 | 说明 |
|---|---|---|
| G-01 品牌 | 无独立端点 | 纯前端 + 配置覆盖（04 文档） |
| G-02/03 | A1–A6 | 导航与档案 |
| G-04 隐私 | A8–A10 | 自检卡 + 一键清除本地数据 |
| G-05/06/07（减法） | 无后端端点 | 纯前端 flags 短路（04 文档 §4）；后端语音/登录接口保持原样不调用 |
| G-08 i18n | 无端点 | 静态资源 |
| G-09 设置 | A6–A7 | |
| G-10/11 资料库 | B1–B5 | |
| G-12/13 人设技能 | I1（人设只读）；技能经由人设会话链路，campus 不直接执行技能 | 技能包由人设 manifest.skills 加载（05 文档），campus 的 AI 端点内嵌同源 rubric prompt |
| G-14 骨架 | 全部 | 路由与 store |
| G-15/CET-09/10 | C1–C4 | |
| G-16/CERT-08/09 | D1–D3、D7 | |
| G-17/CET-05 | D4–D6 | |
| G-18 模板 | I2–I3 | |
| CET-01/02 | F1–F4 | |
| CET-03/04/06 | E5、F6–F9 | |
| CET-13/14 | F10–F14 | |
| KY-01/02/04/13 | F5、G1–G3 | |
| KY-03（自建看板） | G1–G2 | ADR-11：看板数据即 `plan_task`，不触 Teams |
| KY-05/06/07 | C1（分 kind）+ E5 | 各轨复用批改与作答 |
| KY-08 | E5 + E1（真题录入） | |
| KY-09/10 | B6–B7 | |
| KY-11/12/14 | G4–G9 | |
| CERT-01/02/03 | H1–H6 | |
| CERT-04/05/07/14/15 | E1–E5 + C1 | CERT-15（未命中得分点降级掌握度）由 C1 的服务端副作用完成，无独立端点 |
| CERT-11/12/13 | H7–H10 | |
| INF-01 | §2 挂载 | |
| INF-02/03 | I4–I6 | INF-03 导入复用 I4 的逆过程（02 §7.4） |
| INF-04/05/06/07/08 | 无独立端点 | 前端/测试/配置项（04、08 文档） |

**无遗漏**：66 条需求中所有需要前后端交互的点均有端点承载；纯展示、纯前端 flag、静态资源类需求（G-01/05/06/07/08、INF-04~08）按设计无后端交互。

---

## 6. 错误码清单

| code | HTTP | retryable | 场景 |
|---|---|---|---|
| `PROFILE_REQUIRED` | 400 | 否 | 缺 `profile_id` 公共参数 |
| `PROFILE_NOT_FOUND` | 404 | 否 | |
| `PROFILE_READ_ONLY` | 409 | 否 | `finished` 档案拒绝写（02 §7.2） |
| `DUPLICATE_TITLE` / `DUPLICATE_NODE` | 409 | 否 | 档案重名（只与未归档档案比较，02 §7.2）/ 节点类型重复 |
| `EXAM_DATE_REQUIRED` | 400 | 否 | 生成计划前未设置考试日期（PRD §5.1 异常分支） |
| `FILE_TOO_LARGE` / `UNSUPPORTED_TYPE` / `DISK_FULL` | 413/415/507 | 否 | 导入校验（磁盘检查在导入前，PRD §7.6） |
| `DOC_NOT_FOUND` / `DOC_NOT_READY` / `DOC_SCAN_EMPTY` | 404/409/422 | 部分 | `DOC_SCAN_EMPTY` 不可重试（ADR-09：疑似扫描件，提示需 OCR/手动录入） |
| `PARSE_ERROR` | 422 | 否 | 题库/词表导入格式错误，detail 附行号 |
| `QUESTION_NOT_FOUND` / `POINT_NOT_FOUND` / `ATTEMPT_NOT_FOUND` / `RQ_NOT_FOUND` / `MOCK_NOT_FOUND` | 404 | 否 | |
| `INVALID_ATTRIBUTION` / `INVALID_LEVEL` / `ILLEGAL_TRANSITION` / `ILLEGAL_STAGE` | 400/409 | 否 | 枚举/状态机校验（plan_task 状态机见 PRD §6.4） |
| `STAGE_LOCKED` / `MOCK_SUBMITTED` / `PAUSE_EXCEEDED` / `ASSESSMENT_FINISHED` | 409 | 否 | 模考/测评会话约束 |
| `MODEL_NOT_CONFIGURED` | 409 | 否 | 未配置任何模型（引导到设置页，PRD §7.6） |
| `MODEL_TIMEOUT` | 504 | 是 | AI 调用超时（§1：60s/120s），前端提示可切换模型 |
| `MODEL_OUTPUT_INVALID` | 502 | 是 | 模型返回连续 2 次不可解析（L3 降级已在服务端完成后，此码仅在完全失败时返回） |
| `RUBRIC_NOT_FOUND` | 404 | 否 | `rubric_id` 无效 |
| `AUTOMATION_UNAVAILABLE` | 503 | 是 | TaskStore 不可用（罕见） |
| `TEMPLATE_NOT_FOUND` | 404 | 否 | 自动化模板 id 不存在（T13 交付，VERIFY 阶段回流补录） |
| `EXPORT_NOT_FOUND` | 404 | 否 | |
| `SCHEMA_VERSION_ERROR` | 500 | 否 | 库版本新于应用（02 §3.2；实际发生在启动期，此处为防御性） |

约定：所有 5xx（除 `DISK_FULL`/`SCHEMA_VERSION_ERROR`）均为 `retryable=true`；前端按此决定是否展示"重试"按钮（PRD §7.6 不静默失败）。

---

## 7. 与前端 `campus/api.ts` 的映射约定

1. 函数命名与端点一一对应：`listProfiles` / `createProfile` / `gradeEssay` / `listDueReviews` / `submitMockStage` 等，完整清单在 `04-前端设计.md` §5 给出（含 TS 类型）。
2. 错误处理：`campus/api.ts` 统一解包 `{detail: {code, message, retryable}}` 为 `CampusApiError`（携带 `retryable`），hook 层据此渲染重试按钮或引导条。
3. `degrade_level >= 1` 的批改响应、`is_reference=1` 的节点，前端必须渲染提示文案（G5 双语 key 在 04 文档 §6）。
