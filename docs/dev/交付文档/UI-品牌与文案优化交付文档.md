# 前端品牌一致性与文案优化交付文档

- 任务：对「偷偷学 / Stealth Study」桌面 GUI 做前端界面全面检查与优化 —— 项目名一致性、文字提示转向学习类定位、界面一致性验证
- 分支：`feat/frontend-brand-copy-polish`（基线 `7885d77`）
- 规模：65 个文件，519 行新增 / 512 行删除；语言包改写 187 个键（中英合计约 330 条可见文案）
- 结论：前端可见文案中 `OpenWorker` 残留为 0；类型检查与 539 项单测全部通过；e2e 226 通过 / 3 失败，失败项在未改动的基线 `7885d77` 上同样失败

## 1. 命名规范（本次采用）

| 场景 | 规范 | 说明 |
| --- | --- | --- |
| 中文界面产品名 | 偷偷学 | 云登录入口为「偷偷学云」 |
| 英文界面产品名 | Stealth Study | 与 Rust 外壳窗口标题、托盘提示、`index.html` 标题一致 |
| 侧栏/标题栏字标 | Stealth Study + BETA | 原侧栏为连写 `StealthStudy`，已统一 |
| 数据与技术标识 | 保持 `StealthStudy` | Slack 机器人句柄 `@StealthStudy`、`publisher` 比较值、WebSocket 子协议、`productName`/`identifier`、打包产物名 |
| 角色称谓 | 学习伙伴 / study partner | 原「同事 / coworker」直译 |

## 2. 分阶段提交记录

| 提交 | 内容 | 理由 |
| --- | --- | --- |
| `e1de927` | 品牌名一致性：语言包 76 条、侧栏字标、overlay 字标、Info.plist 权限说明、注释、单测与 e2e 断言 | 改名提交只改了组件字面量，语言包与 macOS 权限文案仍是 `OpenWorker` |
| `9225370` | 补齐 WebSocket 子协议改名 | 见第 3 节，属改名遗漏导致的功能缺陷 |
| `31bbcbd` | 称谓统一：en 52 条 / zh 54 条 + personaScope 显示层 | 学习场景下「同事」突兀；后端 persona 名称不动，仅显示层 |
| `67014f6` | 补齐称谓改名的 e2e 断言（8 个文件） | 设置页标签、伙伴选择菜单、会话副标题随显示层改名 |
| `ee97b24` | 首屏与外壳：新建会话问候语、引导语、三张任务卡、hero 快捷任务、侧栏空状态 | 任务重点项 |
| `118a5ef` | 设置页与运行时提示 | 含事实性修正：「自动跟随你 Mac 的外观」→「跟随系统外观」（产品仅支持 Windows 打包） |
| `1d48875` | 自动化定位、内置模板、审批/计划/目录请求主语，中文人称统一为「你」 | 模板改写受连接器真实依赖约束，见第 5 节 |
| `aa0b9f2` | 引导流程、角色与画廊、技能与记忆 | 技能示例改为「出 10 道自测题」「整理本周错题」 |
| `eb1e384` | 审查提示与团队门禁 | `agent`/`workers` 主语改为学习伙伴 |
| `acdac5b` | 角色显示名接入 i18n | 中文界面伙伴选择器曾显示英文 `Study Partner` |

## 3. 改名遗漏造成功能缺陷（重点）

`2c294af refactor: 完成项目重命名为 Stealth Study` 把服务端 `accept(subprotocol=)` 改为 `StealthStudy`，但 GUI 仍上报 `openworker`：

- `surfaces/gui/src/api.ts:36` 上报 `["openworker", token]`
- `ss/server/app.py:2131`、`2911` 选择 `subprotocol="StealthStudy"`
- `tests/test_server.py:630` 断言客户端应上报 `["StealthStudy", token]`

按 RFC 6455 §1.9，服务端返回了客户端未上报的子协议时，客户端必须断开连接。主检出真实日志证据：单场会话 `WS closed unexpectedly (1006)` 共 303 次，每 5 秒重连一次；同期后端对同一请求均为 `accepted` 且无干净关闭，REST 调用全部 200 —— 即事件流与会话流从未连上。修复后实测（本地起真实后端 + 真实前端）：一次页面加载 3 次握手全部建立，空闲 30 秒内 0 次重连、0 条 WS 错误（仅开发模式 StrictMode 造成的一次初始连接主动关闭）。

## 4. 界面一致性验证

| 项 | 方式 | 结果 |
| --- | --- | --- |
| 类型检查 | `npx tsc --noEmit` | 无错误 |
| 单测 | `npx vitest run` | 79 文件 / 539 用例全通过（含 en/zh 键集一致性用例） |
| e2e | `npx playwright test --workers=4` | 226 通过 / 3 失败；失败项为基线（未改动 `7885d77`）同样失败的本地环境问题：Send 按钮 `bg-accent` 类名断言 ×2、任务卡 hover 透明度断言 ×1 |
| 多语言多宽度 | Chromium 真实渲染，1440/1100/1024/820 宽 × 中英双语 | 文档级横向溢出 0；`.greeting`、`.intro-lede`、任务卡标题/副标题/CTA、字标、按钮均无文字裁切 |
| 真实链路 | 隔离状态目录启动 `ss.server.run` + `npm run dev`，浏览器加载 | 中文首屏为「今天学点什么？」、输入框「问问学习伙伴…」、伙伴选择器「学习伙伴」，无英文标签残留 |

改写过程使用脚本化 JSON 值替换，逐条断言：键集合不变、`{{var}}` 与 `<b>/<strong>/<code>` 占位符集合不变、未映射键零改动，因此不存在漏改键或破坏插值的风险。

## 5. 有意保留与未改项

| 位置 | 保留内容 | 理由 |
| --- | --- | --- |
| `tauri.conf.json` | `productName`/`publisher` = `StealthStudy` | 决定安装包与产物文件名（`packaging/make_update_manifest.py` 按此名映射），改后需同步发布链路与已装用户的更新路径 |
| `tauri.conf.json:49` | `https://download.openworker.com/latest.json` | 更新端点属发布基础设施，非界面文案；已在第 6 节列为待决策项 |
| `zh.json` `hubspot.hidden_fields_foot` | 「人类同事」 | 指 HubSpot 里的真人同事，非 AI 角色 |
| `en.json` `settings.trusted_workspaces_help` | `.coworker/config.toml` | 真实工作区配置路径 |
| 组件内 `onOpenWorker`、`coworker-chip`、`coworker:*` 事件名、`__COWORKER_*` 注入变量 | 代码标识符 | 非可见文案，改名会扩大改动面且无用户收益 |
| 后端返回值（persona 名、审批 `reason` 文本、`DEFAULT_SCRATCH_BASE = "~/OpenWorker"`） | 后端数据 | 超出前端范围，见第 6 节 |
| Slack / GitHub / HubSpot / Gmail / MCP 等连接器技术文案 | 原有表述 | 属第三方服务的准确描述，改写为学习话术会造成能力夸大或失真 |

## 6. 待你决策的遗留项

1. 新建会话页第二张任务卡仍是 HubSpot 线索案例。该卡的连接器门控（hubspot 是否已连接）与预填指令是功能逻辑，改成学习场景需要改组件的数据绑定或删除这张卡，已超出文案范围，本次只做了「案例讲解」的最小润色。
2. 更新端点 `https://download.openworker.com/latest.json` 仍指向上游项目域名（GitHub Releases 为并列第二端点）。建议确认后移除，属发布链路改动。
3. 后端 `DEFAULT_SCRATCH_BASE = "~/OpenWorker"`（`ss/server/manager.py:473`）与状态目录 `%APPDATA%\coworker` 仍是旧名，会在用户硬盘生成旧名目录；改动涉及既有数据迁移。
4. 审批卡的 `reason` 等由后端生成的句子仍含「coworker」措辞（前端 mock 同步保留），需在后端文案任务中统一。
5. `tauri.conf.json` 的 `productName` 若也要显示为 `Stealth Study`，需同步改 `packaging/make_update_manifest.py` 的产物名映射与 release 校验。

## 7. 完整文案变更明细

下表为 `surfaces/gui/src/locales/{en,zh}.json` 中所有发生改动的键（187 项），按基线 `7885d77` 与分支 HEAD 对比生成。

| 键 | 原文（en） | 新文（en） | 原文（zh） | 新文（zh） |
| --- | --- | --- | --- | --- |
| access.scope_note | Connecting makes {{title}} available to all your coworkers — the toggle in this list controls just this session. | Connecting makes {{title}} available to all your study partners — the toggle in this list controls just this session. | 连接后 {{title}} 对所有同事可用 —— 此列表中的开关仅控制本次会话。 | 连接后 {{title}} 对所有学习伙伴可用 —— 此列表中的开关仅控制本次会话。 |
| app.build_skill_prefill | Build a new skill for me: {{description}} | Help me build a new study skill: {{description}} | 为我构建一个新技能：{{description}} | 帮我做一个新技能：{{description}} |
| app.build_skill_prefill_empty | Build a new skill for me: (describe what the skill should do) | Help me build a new study skill: (describe what it should do) | 为我构建一个新技能：（描述这个技能应做什么） | 帮我做一个新技能：（描述这个技能要做什么） |
| app.notice.max_iterations | Stopped: max iterations reached. | Stopped: reached the step limit. | 已停止：达到最大迭代次数。 | 已停止：达到步数上限。 |
| app.sleep.status_prompt | Quick status check, please — what's moving, what's blocked, and does anything need me? | Quick check on my studying, please — what's done, what's stuck, and does anything need me? | 请快速汇报一下状态 —— 哪些在推进、哪些被卡住、有没有需要我处理的？ | 帮我快速看一眼进展 —— 哪些已经做完、哪些卡住了、有什么需要我决定？ |
| app.waiting_for_agent | Waiting for agent... | Waiting for your study partner… | 正在等待 agent… | 正在等待学习伙伴… |
| approval.btn.this_run_title | Covers {{name}} until the agent finishes answering your current message. Later calls in this answer run without showing you their arguments first — you'll see them in the transcript afterward. Nothing survives past this answer. | Covers {{name}} until your study partner finishes answering your current message. Later calls in this answer run without showing you their arguments first — you'll see them in the transcript afterward. Nothing survives past this answer. | 在智能体回答完您当前这条消息之前，{{name}} 的后续调用将不再展示参数、直接执行 —— 事后可在会话记录中查看。回答结束后此授权即失效，不会保留任何设置。 | 在学习伙伴回答完你当前这条消息之前，{{name}} 的后续调用将不再展示参数、直接执行 —— 事后可在会话记录中查看。回答结束后此授权即失效，不会保留任何设置。 |
| audit.sub | Recent connector and browser tool activity. Arguments are sanitized before storage. | Recent connector and browser tool activity. Arguments are sanitized before they are stored. | 最近的连接器和浏览器工具活动。参数在存储前已脱敏。 | 最近的连接器与浏览器工具活动记录。参数在存储前已脱敏。 |
| automations.bot_member_hint | The bot must be a member of the channel — invite @OpenWorker in Slack if it isn't. | The bot must be a member of the channel — invite @StealthStudy in Slack if it isn't. | 机器人必须是该频道成员 —— 若未加入，请在 Slack 邀请 @OpenWorker。 | 机器人必须是该频道成员 —— 若未加入，请在 Slack 邀请 @StealthStudy。 |
| automations.cloud_brokered | Connections are brokered by OpenWorker Cloud — your tokens stay on this computer. | Connections are brokered by Stealth Study Cloud — your tokens stay on this computer. | 连接由 OpenWorker Cloud 代理 —— 你的令牌保留在本机。 | 连接由偷偷学云代理 —— 你的令牌保留在本机。 |
| automations.empty_state | No scheduled tasks yet — use a template above, click <strong>+ New automation</strong>, or just ask OpenWorker in a session. | No scheduled tasks yet — use a template above, click <strong>+ New automation</strong>, or just ask Stealth Study in a session. | 还没有定时任务 —— 使用上方模板，点击 <strong>+ 新建自动化</strong>，或在会话里直接让 OpenWorker 做。 | 还没有定时任务 —— 使用上方模板，点击 <strong>+ 新建自动化</strong>，或在会话里直接让偷偷学做。 |
| automations.instructions_placeholder | What should it do each run? (e.g. Summarize today's calendar and open tasks.) | What should it do each run? (e.g. Summarise what's due for review today and the questions I got wrong.) | 每次运行做什么？（例如：总结今天的日历和待办。） | 每次运行做什么？（例如：汇总今天到期的复习项和我做错的题。） |
| automations.runs_desc | Each run is a live conversation — open one to see what the agent did and ask a follow-up. | Each run is a live conversation — open one to see what your study partner did and ask a follow-up. | 每次运行都是一次实时对话 —— 打开可看到 agent 做了什么并追问。 | 每次运行都是一次实时会话 —— 打开即可看到学习伙伴做了什么，并继续追问。 |
| automations.server_hint | Runs only while openworker-server is up — a missed schedule catches up once when it next starts. | Runs only while the Stealth Study background service is up — a missed schedule catches up once when it next starts. | 仅在 openworker-server 运行时执行 —— 错过的计划会在下次启动时补跑一次。 | 仅在偷偷学后台服务运行时执行 —— 错过的计划会在下次启动时补跑一次。 |
| automations.sign_in_to_cloud | Sign in to OpenWorker Cloud | Sign in to Stealth Study Cloud | 登录 OpenWorker Cloud | 登录偷偷学云 |
| automations.sub | Recurring tasks OpenWorker runs on a schedule. | Review reminders, digests and other recurring study tasks Stealth Study runs on a schedule. | OpenWorker 按计划运行的重复任务。 | 偷偷学按计划执行的复习提醒、学习汇总等周期性任务。 |
| automations.title_placeholder | Title (e.g. Daily standup notes) | Title (e.g. Nightly mistake review) | 标题（例如：每日站会纪要） | 标题（例如：每晚错题复盘） |
| automations.tmpl_brief_blurb | Calendar and unread email, summarized before your day starts. | Today's schedule and free slots, plus the email that arrived overnight. | 在一天开始前，汇总您的日历与未读邮件。 | 汇总今天的日程与空闲时段，以及夜间新到的邮件。 |
| automations.tmpl_brief_instructions_prefix | Prepare a short morning brief: today's calendar events and gaps, plus email that arrived since yesterday evening.  | Prepare a short daily study brief: today's classes, deadlines and free slots, plus email that arrived since yesterday evening.  | 准备一份简短晨间简报：今天的日历事件和空闲，加上昨晚以来到达的邮件。 | 准备一份简短的每日学习简报：今天的课程、截止事项与空闲时段，加上昨晚以来到达的邮件。 |
| automations.tmpl_brief_save | Save it as the session deliverable. | Save it as this session's output. | 把它保存为会话交付物。 | 把它保存为本次会话的产出。 |
| automations.tmpl_brief_title | Morning brief | Daily study brief | 晨间简报 | 每日学习简报 |
| automations.tmpl_github_blurb | Merged PRs and commits, posted to your team's Slack. | Merged PRs and commits from your practice repos, posted to Slack. | 已合并的 PR 与 commit，发布到您团队的 Slack。 | 把练习仓库里合并的 PR 与 commit 汇总发布到 Slack。 |
| automations.tmpl_github_title | GitHub digest | Coding practice digest | GitHub 摘要 | 编程练习周报 |
| automations.tmpl_inbox_blurb | One short digest of your unread email. | One short digest of the email you still haven't read. | 一份简短的未读邮件摘要。 | 把你还没读的邮件浓缩成一份简短摘要。 |
| automations.tmpl_inbox_title | Inbox digest | Unread-mail digest | 收件箱摘要 | 未读邮件摘要 |
| automations.tmpl_news_blurb | A 5-bullet tech & world news digest, saved as markdown. | Five bullets from the last 24 hours, saved as markdown — material for essays and reading. | 5 条科技与全球新闻摘要，保存为 Markdown。 | 过去 24 小时的 5 条科技与时政要闻，保存为 Markdown，用作写作与阅读素材。 |
| automations.tmpl_news_title | Morning news briefing | Daily current-affairs notes | 晨间新闻简报 | 每日时政与科技素材 |
| automations.why_meetings_gaps | Today's meetings and gaps | Today's classes and free slots | 今天的会议与空档 | 今天的课程与空闲时段 |
| automations.why_unread_email | Your unread email | Your unread email | 您的未读邮件 | 你的未读邮件 |
| board.open_worker_session | Open this coworker's session | Open this study partner's session | 打开该同事的会话 | 打开该学习伙伴的会话 |
| boot.restoring | Restoring your session… | Restoring your last study session… | 正在恢复你的会话… | 正在恢复上次学习会话… |
| cloud.checking | Checking OpenWorker Cloud sign-in… | Checking Stealth Study Cloud sign-in… | 正在检查 OpenWorker Cloud 登录状态… | 正在检查偷偷学云登录状态… |
| cloud.sign_in | Sign in to OpenWorker Cloud | Sign in to Stealth Study Cloud | 登录 OpenWorker Cloud | 登录偷偷学云 |
| cloud.sign_in_first | Sign in to OpenWorker Cloud first | Sign in to Stealth Study Cloud first | 请先登录 OpenWorker Cloud | 请先登录偷偷学云 |
| cloud.sign_in_oneclick | Sign in to OpenWorker Cloud for one-click — or add a token below | Sign in to Stealth Study Cloud for one-click — or add a token below | 登录 OpenWorker Cloud 启用一键连接 —— 或在下方添加令牌 | 登录偷偷学云启用一键连接 —— 或在下方添加令牌 |
| composer.placeholder | Ask the coworker…  (drop or paste files) | Ask your study partner…  (drop or paste files) | 问问同事…（拖入或粘贴文件） | 问问学习伙伴…（拖入或粘贴文件） |
| composer.placeholder_chat | Ask anything…  (drop or paste files) | Ask anything about your studies…  (drop or paste files) | 随便问…（拖入或粘贴文件） | 知识点、题目、复习计划，随便问…（拖入或粘贴文件） |
| composer.placeholder_code | Ask the coder to build, fix, or explain…  (drop or paste files) | Ask your coding partner to build, fix, or explain…  (drop or paste files) | 让程序员构建、修复或解释…（拖入或粘贴文件） | 让学习伙伴帮你构建、修复或讲解…（拖入或粘贴文件） |
| composer.placeholder_cowork | Ask the coworker…  (drop or paste files) | Ask your study partner…  (drop or paste files) | 问问同事…（拖入或粘贴文件） | 问问学习伙伴…（拖入或粘贴文件） |
| composer.placeholder_gate | Reply to adjust the proposal — or use the buttons above | Reply to adjust the plan — or use the buttons above | 回复以调整提案 —— 或使用上方按钮 | 回复以调整方案 —— 或使用上方按钮 |
| dirreq.requesting_access | The agent is requesting access to a folder | Your study partner is asking for access to a folder | agent 正在请求访问一个文件夹 | 学习伙伴请求访问一个文件夹 |
| dirreq.requesting_workspace | The agent asks to make a folder this session's workspace | Your study partner asks to make a folder this session's workspace | agent 请求将一个文件夹设为本次会话的工作区 | 学习伙伴请求将某个文件夹设为本次会话的工作区 |
| folder_gate.choose_sub | This coworker needs a workspace to read, edit, and run in. | Your study partner needs a folder to read, edit and run things in. | 这位同事需要一个工作区来读取、编辑和运行。 | 学习伙伴需要一个文件夹来读取、编辑和运行。 |
| folder_gate.send_sub | Code work happens inside a folder — pick your project, or start somewhere temporary. | Coding practice happens inside a folder — pick your project, or start somewhere temporary. | 代码工作在文件夹里进行 —— 选择你的项目，或从临时位置开始。 | 编程练习在文件夹里进行 —— 选择你的项目，或先从临时位置开始。 |
| gallery.all_personas | All coworkers | All study partners | 全部同事 | 全部学习伙伴 |
| gallery.connect_yourself_note | You connect these yourself (one click when signed in) — installing the coworker grants it nothing until you do. | You connect these yourself (one click when signed in) — installing the study partner grants it nothing until you do. | 这些由你自己连接（登录后一键）—— 在你连接之前，安装该同事不会授予任何权限。 | 这些由你自己连接（登录后一键）—— 在你连接之前，安装该学习伙伴不会授予任何权限。 |
| gallery.empty_none | No coworkers published yet. | No study partners published yet. | 还没有发布的同事。 | 还没有发布的学习伙伴。 |
| gallery.empty_search | No coworkers match your search. | No study partners match your search. | 没有匹配的同事。 | 没有匹配的学习伙伴。 |
| gallery.filter_brand | From OpenWorker | From Stealth Study | 来自 OpenWorker | 来自偷偷学 |
| gallery.installed_waiting | Installed — it's waiting in Personas, disabled until you approve and enable it. | Installed — it's waiting under Study partners, disabled until you approve and enable it. | 已安装 —— 已放入角色页，启用前需你审批。 | 已安装 —— 已放入「学习伙伴」页，启用前需你审批。 |
| gallery.search_placeholder | Search coworkers | Search study partners | 搜索同事 | 搜索学习伙伴 |
| gallery.signin_desc | The Gallery is a curated set of coworkers from OpenWorker Cloud and needs a (free) cloud sign-in. Installing personas from a folder or Git URL — on the Personas page — always works without an account. | The Gallery is a curated set of study partners from Stealth Study Cloud and needs a (free) cloud sign-in. Installing study partners from a folder or Git URL — on the Study partners page — always works without an account. | 画廊是来自 OpenWorker Cloud 的精选同事集合，需要（免费的）云登录。从文件夹或 Git URL 安装角色 —— 在角色页 —— 始终无需账户即可使用。 | 画廊是来自偷偷学云的精选学习伙伴集合，需要（免费的）云登录。从文件夹或 Git URL 安装学习伙伴 —— 在学习伙伴页 —— 始终无需账户即可使用。 |
| gallery.subtitle | Curated coworkers · installs stay disabled until you approve them | Curated study partners · installs stay disabled until you approve them | 精选同事 · 安装后默认禁用，待你审批启用 | 精选学习伙伴 · 安装后默认禁用，待你审批启用 |
| gallery.team_teaser | From your team — nothing shared yet. Publishing a coworker to your teammates is coming soon. | From your team — nothing shared yet. Publishing a study partner to your teammates is coming soon. | 来自你的团队 —— 暂无分享。向队友发布同事即将推出。 | 来自你的团队 —— 暂无分享。向队友发布学习伙伴即将推出。 |
| gallery.title | Coworker Gallery | Study Partner Gallery | 同事画廊 | 学习伙伴画廊 |
| hero.build_greeting | Let's build something. | Let's build something. | 来做点什么吧。 | 来动手做点东西吧。 |
| hero.chat_greeting | How can I help? | What would you like to understand? | 我能帮你什么？ | 有什么想弄明白的？ |
| hero.suggest_fix_build | Find and fix the failing build. | Find the failing build and teach me how to fix it. | 找到并修复失败的构建。 | 找出构建失败的原因，并教我如何修复。 |
| hero.suggest_overview | Read the project and give me a 5-bullet overview. | Read the project and give me a 5-bullet walkthrough. | 读项目并用 5 条要点给我一个概览。 | 读一遍项目，用 5 条要点讲清结构。 |
| hero.suggest_tests | Run the test suite and summarize any failures. | Run the tests and explain what each failure means. | 运行测试套件并总结失败项。 | 跑一遍测试，逐条讲解失败原因。 |
| hero.try_a_task | Try a task | Try a study task | 试试一个任务 | 试试一个学习任务 |
| inbox.all_coworkers | All coworkers | All study partners | 全部同事 | 全部学习伙伴 |
| inbox.no_subscriptions | No channel subscriptions yet — add one below or ask a coworker to watch a channel. | No channel subscriptions yet — add one below, or ask your study partner to watch a channel. | 还没有频道订阅 —— 在下方添加一个，或让一位同事监听某频道。 | 还没有频道订阅 —— 在下方添加一个，或让一位学习伙伴监听某频道。 |
| inbox.sub | Approvals, questions, and notifications from your coworkers — including sessions running unattended. | Approvals, questions, and notifications from your study partners — including sessions running unattended. | 来自同事的审批、提问和通知 —— 包括无人值守会话。 | 来自学习伙伴的审批、提问和通知 —— 包括无人值守会话。 |
| integrations.connectors_sub | Apps and tools your coworkers can use. Connected ones come first. | Apps and tools your study partners can use. Connected ones come first. | 同事可以使用的应用和工具，已连接的排在前面。 | 学习伙伴可以使用的应用和工具，已连接的排在前面。 |
| intro.folder_prompt | Analyze the files in this folder and summarize what matters. | Go through the material in this folder: outline the key points, then set me a few questions on it. | 分析此文件夹中的文件并总结要点。 | 梳理这个文件夹里的资料：先列出考点与重点，再据此给我出几道题。 |
| intro.ghslack_prompt | Set up a weekly progress report: summarize activity in my GitHub repos and post it to Slack every Friday morning. | Set up a weekly progress summary: review what I did in my GitHub repos and post it to Slack every Friday morning. | 设置一份每周进展报告：总结我 GitHub 仓库的动态，并在每周五早上发布到 Slack。 | 设置一份每周学习进展总结：回顾我在 GitHub 仓库里的推进，并在每周五早上发布到 Slack。 |
| intro.greeting | What should we produce? | What are we studying today? | 需要我产出什么？ | 今天学点什么？ |
| intro.hubspot_prompt | Create a report on my recent HubSpot leads: sources, stages, and who needs follow-up. | Build a worked example from my recent HubSpot leads: sources, stages, and who needs follow-up. | 针对我最近的 HubSpot 线索生成一份报告：来源、阶段，以及需要跟进的对象。 | 把我最近的 HubSpot 线索整理成一份案例讲解：来源、阶段，以及需要跟进的对象。 |
| intro.lede | Pick a task to start — I'll do the work and save the result. Or just type what you need below. | Pick a study task — I'll explain it, set questions, grade your answers and save the result. Or just type what you need below. | 选一个任务开始 —— 我来做并把结果保存。或在下面直接输入你的需求。 | 挑一个学习任务开始 —— 我来讲解、出题、批改，并保存结果。也可以直接在下面输入你的问题。 |
| intro.task_folder_sub | I'll read them and summarize what matters | I'll read your notes and pull out what matters | 我会读取并总结要点 | 我会读取笔记并提炼考点与重点 |
| intro.task_folder_title | Analyze the files in a directory | Go through the material in a folder | 分析目录中的文件 | 梳理资料夹里的讲义 |
| intro.task_ghslack_sub | Repo activity, summarized and posted every Friday | Repo activity, summarised and posted every Friday | 仓库动态，每周五总结后发布 | 仓库与练习动态，每周五总结后发布 |
| intro.task_ghslack_title | Automate a weekly GitHub progress report to Slack | Summarise my week's progress to Slack every Friday | 自动生成每周 GitHub 进展报告并发到 Slack | 每周五自动把我的进展总结发到 Slack |
| intro.task_hubspot_title | Create a report from my HubSpot leads | Turn my HubSpot leads into a worked example | 从我的 HubSpot 线索生成报告 | 把 HubSpot 线索整理成案例讲解 |
| manage.tools_exposed | Tools exposed to OpenWorker | Tools exposed to Stealth Study | 向 OpenWorker 提供的工具 | 向偷偷学提供的工具 |
| mcp.trust_tooltip | You chose 'Always allow this tool' on an approval card — its calls run without asking. 'Revoke' undoes this. | You chose 'Always allow this tool' on an approval card — its calls run without asking. 'Revoke' undoes this. | 您曾在审批卡上选择“始终允许此工具”——其调用将不再询问。“撤销”可取消此设置。 | 你曾在审批卡上选择“始终允许此工具”——其调用将不再询问。“撤销”可取消此设置。 |
| memory.empty | Nothing yet. When you mention a lasting preference in chat — or say "remember that…" — it will show up here. | Nothing yet. When you mention a lasting preference in chat — or say "remember that I'm weak on listening" — it will show up here. | 暂时没有。当你在聊天中提到长期偏好，或说“记住……”，就会显示在这里。 | 暂时没有。当你在对话中提到长期偏好，或说“记住我听力薄弱”，就会显示在这里。 |
| memory.rules_help | Your coworkers follow these in every conversation. | Your study partners follow these in every conversation. | 同事在每个会话中都会遵循这些指令。 | 学习伙伴在每个会话中都会遵循这些指令。 |
| memory.section_sub | Your coworkers can remember useful things about you between conversations. Everything they know is listed here. | Your study partners can remember useful things about you between conversations. Everything they know is listed here. | 同事可以在会话之间记住关于你的有用信息。它们知道的一切都列在这里。 | 学习伙伴可以在会话之间记住关于你的有用信息。它们知道的一切都列在这里。 |
| modal.github_blurb | Opens GitHub in your browser — approve OpenWorker there. An existing @ocw-agent App installation links right up; otherwise you'll pick an account and repos. No tokens typed; the agent acts as ocw-agent[bot]. | Opens GitHub in your browser — approve Stealth Study there. An existing @ocw-agent App installation links right up; otherwise you'll pick an account and repos. No tokens typed; the agent acts as ocw-agent[bot]. | 在浏览器中打开 GitHub —— 在那里授权 OpenWorker。已有的 @ocw-agent App 安装会直接关联；否则你将选择账户和仓库。无需输入令牌；agent 以 ocw-agent[bot] 身份操作。 | 在浏览器中打开 GitHub —— 在那里授权偷偷学。已有的 @ocw-agent App 安装会直接关联；否则你将选择账户和仓库。无需输入令牌；agent 以 ocw-agent[bot] 身份操作。 |
| modal.mcp_blurb | Opens {{title}} in your browser — sign in and approve access there. No tokens typed, and no OpenWorker account needed: the sign-in runs entirely on this computer. | Opens {{title}} in your browser — sign in and approve access there. No tokens typed, and no Stealth Study account needed: the sign-in runs entirely on this computer. | 在浏览器中打开 {{title}} —— 在那里登录并授权。无需输入令牌，也无需 OpenWorker 账户：登录完全在本机运行。 | 在浏览器中打开 {{title}} —— 在那里登录并授权。无需输入令牌，也无需偷偷学账户：登录完全在本机运行。 |
| onboarding.connect_tools_intro | Chat can only advise. Connected, your coworker does the actual work: | Chat on its own can only advise. Connected, your study partner can actually do it: | 仅聊天只能建议。连接后，你的同事才能真正干活： | 只聊天只能给建议。连上工具后，学习伙伴才能真正动手： |
| onboarding.cta_automation_desc | A weekly digest, a morning brief — pick a template, running in two minutes. | Review reminders, a mistake-log digest, a weekly plan — pick a template and it's running in two minutes. | 周报、晨间简报 —— 选个模板，两分钟跑起来。 | 复习提醒、错题周报、每周计划 —— 挑个模板，两分钟跑起来。 |
| onboarding.cta_work_desc | Open a session and just ask — analyze files, draft, research, build. | Open a session and just ask — explain a concept, set questions, grade your answers, summarise your notes. | 打开会话直接提问 —— 分析文件、起草、研究、构建。 | 打开会话直接提问 —— 讲知识点、出题、批改答案、整理笔记。 |
| onboarding.cta_work_title | Start working with Coworker | Start a session with a study partner | 开始与同事协作 | 开始与学习伙伴协作 |
| onboarding.model_intro | Pick a model provider to get started — OpenWorker runs on your own key, and your key and your data stay on this computer. | Pick a model provider to get started — Stealth Study runs on your own key, and your key and your data stay on this computer. | 选择一个模型 provider 开始 —— OpenWorker 使用你自己的密钥运行，密钥和数据都保留在本机。 | 选择一个模型 provider 开始 —— 偷偷学使用你自己的密钥运行，密钥和数据都保留在本机。 |
| onboarding.signin_band_desc | OpenWorker handles the OAuth for 20+ tools — no dev consoles, no pasted keys. Tokens stay on this computer. | Stealth Study handles the OAuth for 20+ tools — no dev consoles, no pasted keys. Tokens stay on this computer. | OpenWorker 代为处理 20+ 工具的 OAuth —— 无需开发者控制台、无需粘贴密钥。令牌保留在本机。 | 偷偷学代为处理 20+ 工具的 OAuth —— 无需开发者控制台、无需粘贴密钥。令牌保留在本机。 |
| onboarding.tool_github_detail | GitHub — review PRs, watch issues, reply to @mentions. | GitHub — review practice PRs, follow issues, reply to @mentions. | GitHub —— 评审 PR、跟踪 issue、回复 @提及。 | GitHub —— 回顾练习 PR、跟踪 issue、回复提及。 |
| onboarding.tool_notion_detail | Notion — search pages, query databases, draft docs. | Notion — search your notes, query a subject database, draft summaries. | Notion —— 搜索页面、查询数据库、起草文档。 | Notion —— 检索笔记、查询科目资料库、整理摘要。 |
| onboarding.tool_slack_detail | Slack — catch up, answer mentions, post updates. | Slack — catch up on the study channel, answer mentions, post progress. | Slack —— 补看消息、回复提及、发布更新。 | Slack —— 补看学习群消息、回复提及、发布进展。 |
| onboarding.two_ways | Two good ways to start: | Two good ways to start: | 两种好的开始方式： | 两种开始方式： |
| onboarding.welcome | Welcome to OpenWorker | Welcome to Stealth Study | 欢迎使用 OpenWorker | 欢迎使用偷偷学 |
| persona.connections_desc | Declared by the persona — wire {{name}} into these to unlock its full workflow. | Declared by this study partner — wire {{name}} into these to unlock its full workflow. | 由角色声明 —— 把 {{name}} 接入这些连接以解锁它的完整工作流。 | 由该学习伙伴声明 —— 把 {{name}} 接入这些连接，才能解锁它的完整学习流程。 |
| persona.enable_title | Enable this coworker | Enable this study partner | 启用此同事 | 启用此学习伙伴 |
| persona.load_error | Could not load this coworker. | Could not load this study partner. | 无法加载此同事。 | 无法加载此学习伙伴。 |
| persona.partner_label | （新增） | Study Partner | （新增） | 学习伙伴 |
| persona.partner_named | （新增） | {{name}} Partner | （新增） | {{name}} |
| persona.persona | Coworker | Study partner | 同事 | 学习伙伴 |
| personas.consent_enabled_note | ✓ Enabled — it's in your coworker picker. | ✓ Enabled — it's in your study partner picker. | ✓ 已启用 —— 已在你的同事选择器中。 | ✓ 已启用 —— 已在你的学习伙伴选择器中。 |
| personas.delete_failed | Couldn't delete — it may be in a session. | Couldn't delete — a study partner may be in use by a session. | 无法删除 —— 该角色可能正在会话中使用。 | 无法删除 —— 该学习伙伴可能正在会话中使用。 |
| personas.disable_coworker | Disable this coworker | Disable this study partner | 禁用此同事 | 禁用此学习伙伴 |
| personas.enable_coworker | Enable this coworker | Enable this study partner | 启用此同事 | 启用此学习伙伴 |
| personas.enable_intro | Enable a coworker, then choose whether it appears in the new-session picker. The starred persona is the default for new sessions. | Enable a study partner, then choose whether it appears in the new-session picker. The starred one is the default for new sessions. | 启用一位同事，然后选择是否显示在新会话选择器中。带星标的角色是新会话的默认角色。 | 启用一位学习伙伴，再选择它是否出现在新建会话的选择器中。带星标的默认用于新会话。 |
| personas.install_coworker | Install a coworker | Install a study partner | 安装同事 | 安装学习伙伴 |
| personas.install_shield_warning | Only enable coworkers from someone you trust. Nothing here runs third-party code — but its instructions will guide the coworker's behavior. | Only enable study partners from someone you trust. Nothing here runs third-party code — but its instructions will guide the study partner's behavior. | 只启用来自你信任之人的同事。这里不会运行第三方代码 —— 但其指令会引导同事的行为。 | 只启用来自你信任之人的学习伙伴。这里不会运行第三方代码 —— 但其指令会引导学习伙伴的行为。 |
| personas.install_trust_note | Only install coworkers from sources you trust and can hold accountable — a coworker runs with access to your system. Files are snapshotted into a managed area; no third-party code runs, but the instructions steer the coworker. Best used by teams whose lead builds and distributes coworkers through official channels. | Only install study partners from sources you trust and can hold accountable — a study partner runs with access to your system. Files are snapshotted into a managed area; no third-party code runs, but the instructions steer the study partner. Best used by teams whose lead builds and distributes study partners through official channels. | 只从你信任且可追责的来源安装同事 —— 同事运行时可以访问你的系统。文件会快照到托管区域；不会运行第三方代码，但其指令会引导同事的行为。最适合由团队负责人通过官方渠道构建和分发同事的团队。 | 只从你信任且可追责的来源安装学习伙伴 —— 学习伙伴运行时可以访问你的系统。文件会快照到托管区域；不会运行第三方代码，但其指令会引导学习伙伴的行为。最适合由团队负责人通过官方渠道构建和分发学习伙伴的团队。 |
| personas.installed_one | Installed {{count}} coworker — review and enable below. | Installed {{count}} study partner — review and enable below. | （新增） | （该语言无此复数形式） |
| personas.installed_other | Installed {{count}} coworkers — review and enable below. | Installed {{count}} study partners — review and enable below. | 已安装 {{count}} 位同事 —— 请在下方审核并启用。 | 已安装 {{count}} 位学习伙伴 —— 请在下方审核并启用。 |
| personas.placeholder_github | https://github.com/acme/ops-coworker | https://github.com/acme/cet-study-partner | https://github.com/acme/ops-coworker | https://github.com/acme/cet-study-partner |
| personas.unshipped_row_one | Not in this release · {{count}} coworker | Not in this release · {{count}} study partner | （新增） | （该语言无此复数形式） |
| personas.unshipped_row_other | Not in this release · {{count}} coworkers | Not in this release · {{count}} study partners | 未包含在本版本 · {{count}} 位同事 | 未包含在本版本 · {{count}} 位学习伙伴 |
| plan.feedback_placeholder | What should change about the plan? | What should change about the study plan? | 计划需要怎么改？ | 学习计划需要怎么改？ |
| plan.proposed | The agent proposed a plan | Your study partner proposed a plan | agent 提出了一个计划 | 学习伙伴提出了一个计划 |
| rail.artifacts_empty | No previewable files yet. | No previewable files from this session yet. | 还没有可预览的文件。 | 这次会话还没有可预览的文件。 |
| rail.artifacts_title | Artifacts | Artifacts | 产出文件 | 学习产出 |
| rail.empty_state | For longer multi-step tasks, progress will appear here while OpenWorker plans, uses tools, waits for approval, and produces artifacts. | For a longer task, progress shows up here while Stealth Study plans, uses tools, waits for approval and saves the files it produces. | 对于较长的多步任务，进度会显示在这里：OpenWorker 规划、调用工具、等待批准并产出文件。 | 较长的多步任务，进度会显示在这里：偷偷学规划步骤、调用工具、等待你的批准，并保存产出的文件。 |
| rail.working | Working... | Working... | 处理中… | 学习中… |
| rail.working_task | Working on this task. | Working on this study task. | 正在处理此任务。 | 正在推进这个学习任务。 |
| settings.files_help | Each conversation gets its own folder under this location. Existing conversations keep their current folder; you can grant access to more folders inside any conversation. | Each study session gets its own folder under this location. Existing sessions keep their current folder; you can grant access to more folders inside any session. | 每个会话都会在此位置下获得自己的文件夹。已有会话保留当前文件夹；你可以在任意会话中授予更多文件夹的访问权限。 | 每个学习会话都会在此位置下获得自己的文件夹。已有会话保留当前文件夹；你可以在任意会话中授予更多文件夹的访问权限。 |
| settings.gallery_open | Browse the Persona Gallery | Browse the Study Partner Gallery | 浏览角色画廊 | 浏览学习伙伴画廊 |
| settings.gallery_sub | Curated coworkers from the OpenWorker team — see what each can do before installing. | Curated study partners from the Stealth Study team — see what each can do before installing. | 来自 OpenWorker 团队的精选角色 —— 安装前了解各自能做什么。 | 来自偷偷学团队的精选学习伙伴 —— 安装前了解各自能做什么。 |
| settings.gallery_title | Persona Gallery | Study Partner Gallery | 角色画廊 | 学习伙伴画廊 |
| settings.general_sub | How OpenWorker looks and behaves on this machine. | How Stealth Study looks and behaves on this machine. | OpenWorker 在本机的外观与行为。 | 偷偷学在本机的外观与行为。 |
| settings.keep_awake_help | Prevent idle sleep so scheduled tasks fire on time. | Prevent idle sleep so your review plans and scheduled tasks fire on time. | 防止空闲休眠，确保定时任务按时执行。 | 防止空闲休眠，确保复习计划与定时任务按时执行。 |
| settings.open_at_login_help | Launch OpenWorker automatically when you sign in. | Launch Stealth Study automatically when you sign in. | 登录时自动启动 OpenWorker。 | 登录时自动启动偷偷学。 |
| settings.personas_desc | Coworkers are agents specialized for a particular role or task. They come equipped with the tools and skills to be successful in that role. Enabling a coworker lets you pick it when starting a conversation. | Study partners are agents specialised for a subject or a study task. They come equipped with the tools and skills to be good at it. Enabling one lets you pick it when you start a session. | 同事是专精于特定角色或任务的 agent，自带胜任该角色所需的工具与技能。启用同事后，即可在开始会话时选择它。 | 学习伙伴是专精于特定学科或学习任务的 agent，自带胜任该任务所需的工具与技能。启用后，即可在新建会话时选择它。 |
| settings.personas_intro | Manage your coworkers and add new ones. | Manage your study partners and add new ones. | 管理你的同事，并添加新同事。 | 管理你的学习伙伴，或添加新的。 |
| settings.run_setup_help | Replays the first-run setup: model, first automation, tips. | Replays the first-run setup: model, connectors, and study tips. | 重新播放首次引导：模型、首个自动化、提示。 | 重新播放首次引导：模型、连接工具与学习提示。 |
| settings.scratch_placeholder | ~/OpenWorker | e.g. ~/Stealth Study/scratch | ~/OpenWorker | 例如：~/偷偷学/scratch |
| settings.sidebar_card_help | How many sessions the sidebar peeks before showing. | How many study sessions the sidebar peeks before showing. | 侧栏在显示前预览的会话数。 | 侧栏在展开前预览的学习会话数。 |
| settings.sidebar_per_coworker | Sessions per coworker | Sessions per study partner | 每个角色的会话数 | 每个学习伙伴的会话数 |
| settings.tab.personas | Coworkers | Study partners | 同事 | 学习伙伴 |
| settings.theme_auto_help | Auto follows your Mac's appearance. | Auto follows your system's appearance. | 自动跟随你 Mac 的外观。 | 自动跟随系统外观。 |
| settings.update_downloading | Downloading — OpenWorker restarts by itself when it's ready. | Downloading — Stealth Study restarts by itself when it's ready. | 下载中 —— OpenWorker 准备好后会自动重启。 | 下载中 —— 偷偷学准备好后会自动重启。 |
| settings.voice_desktop_only | Voice Input setup is available in the OpenWorker desktop app. | Voice Input setup is available in the Stealth Study desktop app. | 语音输入设置仅在 OpenWorker 桌面版中可用。 | 语音输入设置仅在偷偷学桌面版中可用。 |
| setup.import_coworker | Import coworker… | Import study partner… | 导入同事… | 导入学习伙伴… |
| setup.manage_coworkers | Manage coworkers… | Manage study partners… | 管理同事… | 管理学习伙伴… |
| sidebar.choose_persona | Choose a persona | Choose a study partner | 选择角色 | 选择学习伙伴 |
| sidebar.cloud_suffix | OpenWorker Cloud | Stealth Study Cloud | OpenWorker Cloud | 偷偷学云 |
| sidebar.filter_coworker | Filter by coworker | Filter by study partner | 按同事筛选 | 按学习伙伴筛选 |
| sidebar.group_and_filter | Group and filter conversations | Group and filter study sessions | 分组与筛选会话 | 分组与筛选学习会话 |
| sidebar.group_and_filter_short | Group & filter conversations | Group & filter study sessions | 分组与筛选会话 | 分组与筛选学习会话 |
| sidebar.group_persona | Coworker | Study partner | 同事 | 学习伙伴 |
| sidebar.manage_personas | Manage personas… | Manage study partners… | 管理角色… | 管理学习伙伴… |
| sidebar.no_conversations | No conversations yet. | No study sessions yet. | 还没有会话。 | 还没有学习会话。 |
| sidebar.no_matching | No matching conversations. | No matching study sessions. | 无匹配的会话。 | 没有匹配的学习会话。 |
| sidebar.no_project_convos | No conversations in this project yet. | No study sessions in this project yet. | 此项目中还没有会话。 | 此项目中还没有学习会话。 |
| sidebar.not_signed_in | Not signed in — one-click connections need OpenWorker Cloud | Not signed in — one-click connections need Stealth Study Cloud | 未登录 —— 一键连接需要 OpenWorker Cloud | 未登录 —— 一键连接需要偷偷学云 |
| sidebar.sign_in | Sign in to OpenWorker | Sign in to Stealth Study | 登录 OpenWorker | 登录偷偷学 |
| sidebar.signed_in_tooltip | Signed in to OpenWorker Cloud | Signed in to Stealth Study Cloud | 已登录 OpenWorker Cloud | 已登录偷偷学云 |
| sidebar.start_session_as | Start a session as | Start a study session as | 以此身份开始会话 | 以此身份开始学习会话 |
| sidebar.start_with_persona | Start with a specific persona | Start with a specific study partner | 从特定角色开始 | 从指定学习伙伴开始 |
| sidebar.status_working | Working now | Active now | 进行中 | 学习中 |
| skills.confirmation | — the worker can now use it in every conversation. | — your study partner can now use it in every conversation. | —— 同事现在可以在每个会话中使用它。 | —— 学习伙伴现在可以在每个会话中使用它。 |
| skills.desc_placeholder | One line the worker uses to decide when this applies | One line your study partner uses to decide when this applies | 一句话，供同事判断何时适用 | 一句话，供学习伙伴判断何时适用 |
| skills.door_ai | Create with OpenWorker | Create with Stealth Study | 用 OpenWorker 创建 | 用偷偷学创建 |
| skills.door_ai_sub | Starts a conversation — the worker builds it and asks before adding it to your skills | Starts a conversation — your study partner builds it and asks before adding it to your skills | 开始一个会话 —— 同事完成后会先询问，再加入你的技能 | 开始一个会话 —— 学习伙伴做好后会先询问，再加入你的技能 |
| skills.empty | No skills yet — <b>Add skill</b> teaches your worker its first one, like “prepare my Monday status report”. | No skills yet — <b>Add skill</b> teaches your study partner its first one, like “summarise the questions I got wrong this week”. | 还没有技能 —— 点 <b>添加技能</b> 教同事第一个技能，比如“准备我的周一状态报告”。 | 还没有技能 —— 点 <b>添加技能</b> 教学习伙伴第一个技能，比如“把这周做错的题整理成复盘”。 |
| skills.instructions_placeholder | 1. Gather last week's updates / 2. Write the report, under 300 words | 1. Gather what I studied this week / 2. Write 10 self-test questions from it | 1. 收集上周的进展 / 2. 撰写报告，300 字以内 | 1. 汇总我这周学过的内容 / 2. 据此出 10 道自测题 |
| skills.review_sub | Read the instructions — installing a skill means the worker will follow them. | Read the instructions — installing a skill means your study partner will follow them. | 请阅读指令 —— 安装技能意味着同事会照着执行。 | 请阅读指令 —— 安装技能意味着学习伙伴会照着执行。 |
| skills.subtitle | Reusable instructions the worker can follow in every conversation. Off here means off everywhere. | Reusable instructions your study partner can follow in every conversation. Off here means off everywhere. | 可复用的指令，同事在每个会话中都能遵循。在这里关闭即处处关闭。 | 可复用的指令，学习伙伴在每个会话中都能遵循。在这里关闭即处处关闭。 |
| slack.hiw_cap_mention | Mention @OpenWorker in any channel it's invited to — a session opens here, and the answer lands back in Slack as a thread. | Mention @StealthStudy in any channel it's invited to — a session opens here, and the answer lands back in Slack as a thread. | 在任意它被邀请的频道里 @提及 OpenWorker —— 这里会开启一个会话，回答会作为话题回到 Slack。 | 在任意已邀请它的频道里 @StealthStudy —— 这里会开启一个会话，回答会作为话题回到 Slack。 |
| slack.hiw_coworker | Coworker | Study partner | 同事 | 学习伙伴 |
| slack.hiw_msg_kp | Message OpenWorker… | Message Stealth Study… | 给 OpenWorker 发消息… | 给偷偷学发消息… |
| slack.hiw_title | Getting started with Slack & OpenWorker | Getting started with Slack & Stealth Study | Slack 与 OpenWorker 入门 | Slack 与偷偷学入门 |
| team.chat_empty | No messages yet. Agents post here only when something needs a reply — @mention a coworker to reach it. | No messages yet. Agents post here only when something needs a reply — @mention a study partner to reach it. | 还没有消息。Agent 只在需要回复时才会在这里发言 —— @提及某位同事即可联系它。 | 还没有消息。Agent 只在需要回复时才会在这里发言 —— @提及某位学习伙伴即可联系它。 |
| team.chat_info | A group channel for questions and consensus — @mentions wake the mentioned coworker. Status stays on the board either way. | A group channel for questions and consensus — @mentions wake the mentioned study partner. Status stays on the board either way. | 用于问题与共识的群聊频道 —— @提及会唤醒被提及的同事。无论是否启用，状态都保留在看板上。 | 用于问题与共识的群聊频道 —— @提及会唤醒被提及的学习伙伴。无论是否启用，状态都保留在看板上。 |
| team.items_grant | Reply to edit the split; approval creates these on the board. | Reply to adjust the split; approval creates these on the board. | 回复可调整拆分；批准后将在看板上创建这些条目。 | 回复可调整拆分；批准后将在看板上创建这些学习任务。 |
| team.proposed_items | Proposed work items — {{count}} | Proposed study tasks — {{count}} | 提议的工作项 —— {{count}} | 提议的学习任务 —— {{count}} |
| team.proposed_one | Proposed team — {{count}} worker | Proposed study team — {{count}} partner | （新增） | （该语言无此复数形式） |
| team.proposed_other | Proposed team — {{count}} workers | Proposed study team — {{count}} partners | 提议团队 —— {{count}} 名成员 | 学习小组提议 —— {{count}} 位伙伴 |
| toolreq.installs | OpenWorker installs its own verified copy — or install it yourself and continue. | Stealth Study installs its own verified copy — or install it yourself and continue. | OpenWorker 会安装自己的已验证副本 —— 也可自行安装后继续。 | 偷偷学将安装其已验证副本 —— 也可自行安装后继续。 |
| toolreq.installs_with_source | OpenWorker installs its own verified copy from {{source}} — or install it yourself and continue. | Stealth Study installs its own verified copy from {{source}} — or install it yourself and continue. | OpenWorker 会从 {{source}} 安装自己的已验证副本 —— 也可自行安装后继续。 | 偷偷学将从 {{source}} 安装其已验证副本 —— 也可自行安装后继续。 |
| toolreq.needs | The coworker needs <code>{{tool}}</code> | The study partner needs <code>{{tool}}</code> | 同事需要 <code>{{tool}}</code> | 学习伙伴需要 <code>{{tool}}</code> |
| toolreq.no_build | OpenWorker has no verified build for this machine — install it yourself if you want this check, or continue and the coworker will note the gap. | Stealth Study has no verified build for this machine — install it yourself if you want this check, or continue and the study partner will note the gap. | OpenWorker 没有适用于本机的已验证构建 —— 需要此项检查请自行安装，或直接继续，同事会记录这一缺口。 | 偷偷学没有适用于本机的已验证构建 —— 需要此项检查请自行安装，或直接继续，学习伙伴会记录这一缺口。 |
| topbar.artifacts | Artifacts | Artifacts | 产出文件 | 学习产出 |
| topbar.show_artifacts | Show files this conversation produced | Show files this study session produced | 显示本次对话产出的文件 | 显示本次学习会话产出的文件 |
| transcript.approval.run_grant_title | you chose 'Allow for this request' earlier in this answer — this call ran without a card. Its full arguments are in this transcript and the audit log; the grant expired when the answer finished | you chose 'Allow for this request' earlier in this answer — this call ran without a card. Its full arguments are in this transcript and the audit log; the grant expired when the answer finished | 您在本次回答早些时候选择了“本次请求内允许”——此调用未显示审批卡片。完整参数保存在会话记录与审计日志中；回答结束后该授权已失效 | 你在本次回答早些时候选择了“本次请求内允许”——此调用未显示审批卡片。完整参数保存在会话记录与审计日志中；回答结束后该授权已失效 |
| transcript.approval.trusted_rule | allowed by your trust rule | allowed by your trust rule | 按您的信任规则放行 | 按你的信任规则放行 |
| transcript.approval.trusted_rule_title | you chose 'Always allow this tool' on an approval card — the card was waived; revoke the rule on this server's Connectors page. Mode gates, the reviewer, and the audit trail still applied | you chose 'Always allow this tool' on an approval card — the card was waived; revoke the rule on this server's Connectors page. Mode gates, the reviewer, and the audit trail still applied | 您曾在审批卡上选择“始终允许此工具”——已跳过审批卡片；可在该服务器的连接器页面撤销此规则。模式限制、审查器与审计记录仍然生效 | 你曾在审批卡上选择“始终允许此工具”——已跳过审批卡片；可在该服务器的连接器页面撤销此规则。模式限制、审查器与审计记录仍然生效 |
| transcript.reviewer.explain | The agent was told only that it was blocked — not why — so it can’t argue its way past this. If the action is actually fine, you can run it as proposed: | Your study partner was told only that it was blocked — not why — so it can’t argue its way past this. If the action is actually fine, you can run it as proposed: | agent 只被告知操作被拦截 —— 而非原因 —— 因此无法辩解绕过。如果该操作确实没问题，你可以按原样执行它： | 学习伙伴只被告知操作被拦截 —— 而非原因 —— 因此无法辩解绕过。如果该操作确实没问题，你可以按原样执行它： |
| transcript.reviewer.override_sent | Approved — the agent will retry this exact action. | Approved — your study partner will retry this exact action. | 已批准 —— agent 将原样重试该操作。 | 已批准 —— 学习伙伴将原样重试该操作。 |
| transcript.step.hidden_tip | Removed by your privacy filters before the agent saw the results — agents get no trace of these. | Removed by your privacy filters before your study partner saw the results — it gets no trace of these. | 在 agent 看到结果前已被你的隐私过滤器移除 —— agent 不会获知任何痕迹。 | 在学习伙伴看到结果前已被你的隐私过滤器移除 —— 它不会获知任何痕迹。 |
| transcript.who_assistant | assistant | study partner | 助手 | 学习伙伴 |
| update.ready | OpenWorker v{{version}} is ready to install. | Stealth Study v{{version}} is ready to install. | OpenWorker v{{version}} 已准备好安装。 | 偷偷学 v{{version}} 已准备好安装。 |
| workspace_trust.sub | This project asks OpenWorker to run the commands below without individual approval. Trust applies to future configuration changes at this exact folder until you revoke it in Settings. | This project asks Stealth Study to run the commands below without individual approval. Trust applies to future configuration changes at this exact folder until you revoke it in Settings. | 此项目请求 OpenWorker 无需逐条批准即可运行以下命令。信任仅对该文件夹（含其后续配置变更）生效，可随时在设置中撤销。 | 此项目请求偷偷学无需逐条批准即可运行以下命令。信任仅对该文件夹（含其后续配置变更）生效，可随时在设置中撤销。 |
