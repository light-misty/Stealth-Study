# HIU-WorkSpace 已有能力盘点与可行性矩阵

- 文档日期：2026-09-08
- 角色：架构师（高见远）
- 项目定位：基于 OpenWorker（已改名 HIU-WorkSpace / coworker）二次开发，重构为通用大学生 AI 备考学习桌面应用
- 范围：仅学生端；三个备考台（四六级 / 考研 / 证书）；核心闭环为「学生向 AI 获取资料与讲解 → 将 AI 总结保存进系统本地 → 本地沉淀、检索与复习」
- 技术基线：Tauri 2 + 本地 Python 服务（FastAPI + aisuite）；模型 BYOK（学生自带 Key）；本地优先

---

## 0. 核实范围与来源（重要）

本审计结论以「实际读到的代码」为准。未作独立复读、由交付总监预先核实的结论，在表格中标注「总监已核实（未独立复读）」，建议进入实现规划前再读一遍原文件。

### 0.1 本次已直接读取并核对的文件

| 文件 | 核对内容 |
|------|----------|
| `coworker/tools/files.py` | 仅 `read_file`，只读、workspace 限定（行 1-127） |
| `coworker/tools/search.py` | `grep` 代码搜索，只读、workspace 限定（行 82-139） |
| `coworker/memory/sqlite_store.py` | `memories` 表 schema（行 23-34）、CRUD 方法 |
| `coworker/memory/tools.py` | `remember` / `memory_read` / `memory_update` / `memory_forget`（行 63-138） |
| `coworker/personas/manifest.py` | `VALID_GROUPS={"general","security"}`（行 29）、`ships`/`group`/`team`/`skills` 字段（行 23-98）、解析逻辑（行 249-341） |
| `coworker/skills/store.py` | 文件夹式 CRUD、staging→预览→确认（行 1-81） |
| `coworker/agents/chat.py` | 通用对话 agent，无 file/shell 访问（行 1-22） |
| `coworker/providers/registry.py` | openai/codex/anthropic/gemini/bedrock/vertex/ollama 工厂（行 120-197），国产与开源提供商（行 205-636） |
| `coworker/automation/store.py` | croniter 调度 + sqlite3 存储（行 4、44、79-80） |
| `stt/src/lib.rs` | 默认英文模型 `ggml-base.en.bin`（行 27-33） |
| `surfaces/gui/src/components/PersonasTab.tsx` | 人设管理 UI（git/dir/zip 安装） |
| `surfaces/gui/src/components/SkillsTab.tsx` | 技能管理 UI（staging/确认上传） |
| `surfaces/gui/src/components/MemorySection.tsx` | 记忆列表 UI（开关/编辑/删除） |
| `surfaces/gui/src/components/ScheduledView.tsx` | 定时任务 UI（cron 编辑器） |

### 0.2 总监已核实、本次未独立复读（建议实现前复核）

- 内置 16 个人设中 13 个标注 `ships: false`（change/appsec/design/infra/devops/ops/devsecops/swe-lead/posture/swe-worker/logs/secrets/triage/test），默认仅分发 security / cloud-posture / dep-audit。
- `coworker/automation/models.py` 的 `Schedule` 支持 `cron`/`once`，`ScheduledTask` 含 `always_allowed_tools`。
- `surfaces/gui/src/i18n.ts` 已支持 `en`/`zh` 双语（跟随系统、可手动切换、localStorage 持久化）。
- `Composer.tsx` 的语音输入入口；`AuditView / PlanCard / TodoPanel / BoardPanel / SearchModal / FolderGate / Onboarding / IntegrationsView / SettingsView` 等组件存在。
- `coworker/agents/` 含 chat / code / cowork / myhelper 四类；`code.py` 为成熟 solo 编码代理。

---

## 1. 能力清单表（与备考学习相关）

复用评级说明：**A = 直接复用**，**B = 小幅改造**，**C = 必须新写**。

| # | 能力名称 | 代码位置 | 现在能做什么 | 前端入口 | 复用评级 |
|---|----------|----------|--------------|----------|----------|
| 1 | 多提供商 BYOK 接入 | `coworker/providers/registry.py:120-205, 587-636` | openai/codex/anthropic/gemini/bedrock/vertex/ollama 原生工厂；Z AI(GLM)/DeepSeek/Kimi(Moonshot)/MiniMax/Qwen/xAI/Mistral/Ark(豆包)/Meta 走 OpenAI 兼容路径，BYOK 无需新增适配 | `IntegrationsView` / `SettingsView` / `ModelChecklist` | **A** |
| 2 | 中文界面（国际化） | `surfaces/gui/src/i18n.ts`（总监已核实） | 已支持 en/zh 双语，跟随系统、可手动切换、localStorage 持久化 | 全局 | **A** |
| 3 | 技能包机制（文件夹 CRUD + 预览-确认） | `coworker/skills/store.py:1-81` | global（state_dir/skills）与 project（<workspace>/.coworker/skills）两类；上传 staging→预览→确认；个人启用/禁用；`save_skill` 可在对话中由 Agent 提议写入用户技能库 | `SkillsTab.tsx` | **A**（几乎零改造承载备考技能包） |
| 4 | 定时自动化 | `coworker/automation/store.py:44,79-80` + `models.py`（总监已核实） | 基于 SQLite + croniter 的 `Schedule`（cron/once），`ScheduledTask` 含 `always_allowed_tools`；可作为「每日复习提醒/打卡」 | `ScheduledView.tsx`, `AutomationQuickstart.tsx` | **A** |
| 5 | 代码搜索（本地检索） | `coworker/tools/search.py:82-139` | 只读、workspace 限定的 `grep`，ripgrep 优先、Python 回退，返回 file:line:text | 对话内工具 | **A** |
| 6 | 文件只读读取 | `coworker/tools/files.py:50-126` | 只读、workspace 限定的 `read_file`，带行号、大文件分窗 | 对话内工具 | **A**（读取资料用，但无写能力） |
| 7 | 对话与 Markdown 渲染 | `Composer.tsx` / `Markdown.tsx` / `Transcript.tsx`（总监已核实） | AI 讲解的流式对话与富文本展示，含语音输入入口 | `Composer` 等 | **A** |
| 8 | 通用长期记忆（键值） | `coworker/memory/sqlite_store.py:23-34` + `tools.py:63-138` | `memories` 表（scope/key/content/summary/workspace/session_id）；`remember`/`memory_read`/`memory_update`/`memory_forget`，带保存开关与 Undo 通知 | `MemorySection.tsx` | **B**（可承载笔记/错题本，但需上层封装「用户知识卡片」语义） |
| 9 | 人设 / Persona 体系 | `coworker/personas/manifest.py:23-98, 249-341` | manifest 解析（YAML frontmatter + markdown 正文）；支持 `tools`/`skills`/`team`/`ships`/`group`/`connectors` 等字段；`PersonasTab` 可 git/dir/zip 安装 | `PersonasTab.tsx` | **B**（新增 `hiu-student-*` 目录即可，不改 `VALID_GROUPS` 枚举） |
| 10 | 计划卡 / 待办 | `PlanCard.tsx` / `TodoPanel.tsx`（总监已核实） | 对话中生成计划卡与待办清单 | 对话内组件 | **B**（备考计划模板可承载，需定制题型/阶段） |
| 11 | 审计视图 | `AuditView.tsx`（总监已核实） | 行为审计展示 | `AuditView` | **A**（可选：学习行为留痕/家长查看） |
| 12 | 语音输入（STT） | `stt/src/lib.rs:25-33` | 本地离线 whisper_rs；默认 `ggml-base.en.bin`（~142MB 英文短句模型） | `Composer` 语音入口 | **C（前置改造）**（默认英文模型，多语种/中文需换模型） |
| 13 | 本地文件写入 | 缺失 | 现有 `files.py` 只有 `read_file`，**无写文件工具** | 无 | **C（核心缺口）**（「一键沉淀本地」无原生支撑） |
| 14 | 本地资料检索 / 复习视图 | 缺失（检索可借 #5 grep，复习 UI 需新做或增强 #8） | 无面向备考的笔记库浏览/检索/复习界面 | 无 | **C / B**（取决于是否复用 MemorySection 增强） |

---

## 2. 可行性矩阵

### A 档：直接复用（约 9 项）

| 项 | 改造点 | 涉及文件 |
|----|--------|----------|
| 多提供商 BYOK 接入 | 无（仅需在 onboarding 推荐国产免费额度模型） | `providers/registry.py` |
| 中文界面 | 无（现成可用） | `surfaces/gui/src/i18n.ts` |
| 技能包机制 | 无（按备考场景新增 SKILL.md 内容即可） | `skills/store.py`, `SkillsTab.tsx` |
| 定时自动化 | 无（复用做复习提醒/打卡） | `automation/store.py`, `ScheduledView.tsx` |
| 代码搜索 | 无 | `tools/search.py` |
| 文件只读读取 | 无 | `tools/files.py` |
| 对话与 Markdown | 无 | `Composer.tsx`, `Markdown.tsx`, `Transcript.tsx` |
| 审计视图 | 无（可选启用） | `AuditView.tsx` |
| 计划卡/待办 | 轻量定制题型与阶段 | `PlanCard.tsx`, `TodoPanel.tsx` |

### B 档：小幅改造（约 4 项）

| 项 | 改造点 | 涉及文件 |
|----|--------|----------|
| 通用记忆 → 「用户知识卡片」 | 上层封装语义（卡片类型：笔记/错题/单词），补复习字段 | `memory/sqlite_store.py`, `memory/tools.py`, `MemorySection.tsx` |
| 备考人设新增 | 新增 `hiu-student-cet`/`hiu-student-kaoyan`/`hiu-student-cert` 目录与 manifest；不改 `VALID_GROUPS` | `personas/manifest.py`, `personas/builtin/`（新目录） |
| 人设分发机制 | 新人设 `ships:true` / `group:general`，或纳入 release 构建（避免仅 `OPENWORKER_UNSHIPPED` 内部可见） | `personas/manifest.py`, release 构建脚本 |
| 计划模板 | 三备考台的计划模板（每日打卡/冲刺计划/阶段计划）配置化 | `PlanCard.tsx`, `TodoPanel.tsx` |

### C 档：必须新写（约 3 项，含核心缺口）

| 项 | 改造点 | 涉及文件 |
|----|--------|----------|
| **写文件工具（核心闭环最大缺口）** | 新增受 workspace 限定的 `write_file`（含目录创建、覆盖保护），对齐 `save_skill` 的「预览-确认」审批范式，让学生对 AI 总结说「保存」即落盘到 `<workspace>/.hiu/notes/` | 新增 `tools/write_file.py`，注册到 catalog，人设 `tools` 声明 |
| STT 多语种 / 中文模型 | 替换默认英文模型为支持中文/多语种的 whisper 模型，加入模型选择、下载与 SHA256 校验 | `stt/src/lib.rs`, STT 模型管理 |
| 本地资料检索 / 复习视图 | 基于 memory 封装或新做笔记库浏览、检索、复习（闪卡/错题重练）界面 | 新增组件或增强 `MemorySection.tsx` |

### 核心闭环最大缺口（重点标注）

> **文件写入能力缺失**。`coworker/tools/files.py` 当前仅提供 `read_file`（只读、workspace 限定），系统中没有任何「把 AI 产出写成本地文件」的原生工具。长期记忆（`memories` 表）是通用键值存储，不适合承载结构化、可检索、可复习的学习资料文件；`save_skill` 仅用于技能包写入，不泛化到一般笔记。因此「AI 产出 → 一键沉淀本地」这一环节目前**没有原生支撑**，是三环节里覆盖度最低、必须新写的一项。

---

## 3. 核心闭环缺口分析

核心闭环：学生向 AI 获取学习资料与讲解 → 将 AI 的总结**保存进系统本地** → 在本地沉淀、检索与复习。

### 逐环节覆盖度与缺口

| 环节 | 现有覆盖 | 缺口 | 覆盖度 |
|------|----------|------|--------|
| ① AI 产出（资料与讲解） | `chat` agent + 多提供商 BYOK + Markdown 渲染 + 语音输入（英文） | 中文/多语种语音需换模型；人设提示词需备考化 | 高 |
| ② 一键沉淀本地 | `remember`（记忆 KV）、`save_skill`（仅技能） | **无写文件工具**；记忆非文件、不可结构化检索 | 低（最大缺口） |
| ③ 本地检索 / 复习 | `grep` 可检索文本文件；`MemorySection` 展示事实列表 | 无面向备考的笔记库浏览/闪卡/错题重练界面；记忆 UI 非复习视图 | 中 |

### 最省力的补法

1. **新增一个受 workspace 限定的写文件工具 `write_file`**：支持写入 `<workspace>/.hiu/notes/`（或用户指定子目录）、自动建目录、覆盖前确认。这是打通环节②的最小改动。
2. **对齐 `save_skill` 的「预览-确认」审批范式**：`save_skill`（`skills/store.py`）已用 staging→预览→确认 治理写入风险；`write_file` 应复用同一种「Agent 提议 → 用户预览内容 → 确认后落盘」的交互，避免静默写盘。
3. **检索与复习复用既有能力**：落盘后的 markdown 用 `grep`（`search.py`）即可全文检索；复习视图优先增强 `MemorySection`（B 档）而非从零新写；仅当卡片/闪卡语义复杂再升级为 C 档新组件。
4. **人设层声明工具**：在 `hiu-student-*` 人设的 `tools` 中声明新工具，使「保存」成为学生单机会话里的原生能力，无需改上游枚举。

结论：环节②用 1 个新工具（C 档）即可补齐，环节③优先走 B 档增强，整体投入可控。

---

## 4. 三个备考台的技术差异

### 4.1 可共用（无需为差异写代码）

| 共用能力 | 说明 |
|----------|------|
| 人设机制 | 三台各自一个 `hiu-student-*` 人设，共用 manifest 体系，仅 system_prompt / tools / skills 不同 |
| 技能包机制 | 真题解析 / 作文批改 / 单词卡生成 等技能包，均按 `SKILL.md` 新增，机制零改造 |
| 记忆 | 通用 `memories` 表承载笔记/错题，三台共用存储，按 scope/key 区分 |
| 自动化 | `Schedule` 复用做各台「每日复习提醒/打卡」，cron 表达式一致 |
| BYOK / i18n / 对话 / Markdown | 全部共用，无差异 |

### 4.2 必须分开（差异来源）

| 差异维度 | 四六级 | 考研 | 证书 | 差异解决办法 |
|----------|--------|------|------|--------------|
| 词库 | 四六级核心词 | 考研英语/政治/专业课词 | 各证书专有术语 | 人设提示词 + 单词卡技能内容（配置层） |
| 题型 | 听力/阅读/写作/翻译 | 政治/英语/数学/专业课 | 各证书科目卷 | 技能包 SKILL.md 内容（配置层） |
| 计划模板 | 每日打卡 + 阶段性词汇计划 | 长线冲刺计划（按月/周） | 报名-备考-冲刺节点 | PlanCard/TodoPanel 模板文本（配置层） |
| 语音语种需求 | 听力/口语需中文+英语多语种 | 同上，且口试场景多 | 视证书而定（多数中文） | STT 多语种模型（C 档前置改造，三台共用） |
| 资料结构 | 真题/范文/词表 | 真题/讲义/错题 | 大纲/真题/案例 | 写文件落盘目录与命名约定（约定层） |

### 4.3 差异可由配置解决、无需写代码的部分

- 各台**人设 system_prompt**（讲解风格、知识边界、推荐模型）。
- 各台**技能包 SKILL.md 内容**（真题解析步骤、作文批改维度、单词卡格式）。
- 各台**计划模板文本**与**打卡 cron**。
- 各台**词库 / 题型提示词**。

即：三台的差异几乎全部落在「人设 + 技能包 + 计划模板」的内容配置上，技术底座（人设、技能、记忆、自动化、BYOK、i18n）完全共用，无需为某个台单独写代码。

---

## 5. 前置改造项与风险

| # | 改造项 | 影响面 | 风险等级 | 建议 |
|---|--------|--------|----------|------|
| R1 | **STT 多语种 / 中文模型** | 四六级/考研口语与听力必须换默认英文模型；否则中文识别不可用 | 高（功能前置） | 引入多语种 whisper 模型（如 large-v3-turbo / 中文 whisper），做模型选择、下载与 SHA256 校验，替换 `stt/src/lib.rs:28` 的 `DEFAULT_MODEL_FILE`；注意模型体积（142MB+ 更大）的分发策略 |
| R2 | **人设分发机制（ships / group / release）** | 新增 `hiu-student-*` 人设如何进入 release 构建；当前内置多为 `ships:false`，仅 `OPENWORKER_UNSHIPPED=1` 内部构建可见 | 中 | 新人设用 `ships:true` + `group:general`，或调整 release 构建脚本纳入备考人设；避免仅内部构建可见 |
| R3 | **本地 Python sidecar 启动** | Tauri 2 需稳定拉起 FastAPI + aisuite 本地服务；首启动依赖（模型/Python 包）就绪 | 中 | 确认 sidecar 打包路径与启动顺序、失败重试与状态提示；首启动引导完成依赖就绪 |
| R4 | **BYOK 首次配置门槛** | 学生需自备 Key，首启可能卡在「没有可用模型」 | 中 | Onboarding 引导；默认推荐有免费额度的国产模型（DeepSeek / Kimi / Z AI GLM），降低门槛 |
| R5 | **跨平台打包** | Win / macOS / Linux 桌面分发；STT 模型体积大、sidecar 体积大 | 中 | Tauri 2 打包流水线；模型按需下载而非随包体积膨胀；校验各平台 sidecar 路径 |

---

## 6. 「不使用」清单（首期明确不纳入）

| 能力 | 代码位置（参考） | 不纳入理由 |
|------|------------------|------------|
| 编码代理 `code.py` | `coworker/agents/code.py` | 成熟 solo 编码代理，属「编程课设/日常课业」，不在首期备考主线 |
| 团队协作 / 多 agent | `TeamChatView.tsx`, `BoardPanel.tsx`, manifest `team: lead/worker` | 学生单机备考，无需 LEAD/WORKER 团队编排与看板 |
| MCP / 自定义连接器 | `connectors/CustomMcp.tsx`, `manifest.mcp` | 不对接校方/第三方系统，MCP 与自定义 MCP server 暂不启用 |
| 外部连接器（GitHub/Gmail/Slack/HubSpot/Calendar 等） | `connectors/*` | 备考场景不接入外部 SaaS，品牌去校名化、不对接校方系统 |
| 安全向内置人设 | `personas/builtin/`（13 个 `ships:false`） | change/appsec/design/infra/devops/ops/devsecops/swe-lead/posture/swe-worker/logs/secrets/triage/test 均为安全/工程向，且系统提示要求「对 LEAD 说话、绝不使用 ask_user」，不适用于学生单机会话 |
| 企业 / 教师端能力 | — | 产品方向明确仅学生端，教师端不产出 |
| 邮件 / 日历深度集成 | `connectors/GmailDetail.tsx`, `CalendarDetail.tsx` | 复习提醒用本地 `Schedule` 即可，不依赖外部日历 |

---

## 7. 结论摘要（供决策）

- **A 档（直接复用）约 9 项**：BYOK 多提供商、中文 i18n、技能包、定时自动化、代码搜索、只读文件读取、对话/Markdown、审计视图、计划卡/待办（轻定制）——技术底座已齐备。
- **B 档（小幅改造）约 4 项**：记忆封装为「用户知识卡片」、新增备考人设、人设分发纳入 release、计划模板配置化。
- **C 档（必须新写）约 3 项**，其中**核心闭环最大缺口是「写文件工具缺失」**——现有 `files.py` 只有只读 `read_file`，「一键把 AI 总结沉淀到本地」无原生支撑；最省力补法为新增受 workspace 限定的 `write_file`，并复用 `save_skill` 的「预览-确认」审批范式。
- **最关键 3 个前置改造项**：① STT 多语种/中文模型替换（R1，功能前置）；② 人设分发机制纳入 release（R2）；③ 本地 Python sidecar 稳定启动（R3）。
- 三备考台差异几乎全部可由「人设 + 技能包 + 计划模板」配置解决，技术底座共用，无需为单台写代码。
