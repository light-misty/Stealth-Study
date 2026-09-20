<h1 align="center">偷偷学（StealthStudy）</h1>

<p align="center">
  <a href="README_en.md">English</a> · <strong>简体中文</strong>
</p>

<p align="center"><em>本地备考 AI 学习伙伴 —— 覆盖四六级、考研与证书备考。</em></p>

<p align="center">
  <img src="docs/assets/app-screenshot-newchat.png" alt="应用截图-新会话" width="800">
</p>
<p align="center">
  <img src="docs/assets/app-screenshot-workflow.png" alt="应用截图-工作流" width="800">
</p>

> **Beta** — 偷偷学正处于公开 beta 阶段：以下功能完全可用，我们正在积极打磨细节。欢迎提出 [Issues](https://github.com/light-misty/Stealth-Study/issues)。

**一款运行在你机器上的 AI 学习伙伴。** 偷偷学是开源、不绑定单一模型的学习 Agent 运行时。它不只是聊天：能把一道题、一个知识点讲到明白，能把考纲变成复习计划，能把你答题卡上的每道错题归因到根因，还能产出可直接打开和保存的学习材料（生词表、提纲、记忆卡片）。开箱即用覆盖三条备考线：**四六级**、**考研** 与 **证书备考**（教师资格 · NCRE 等）。

它完全运行在你的电脑上，不绑定任何特定模型：自带 OpenAI、Anthropic、Google Gemini、AWS Bedrock、Google Vertex AI、OpenAI Codex 或任何统一接口背后的提供商的 API Key 即可。你的数据始终留在本机——只通过你选择的模型和集成发出去。学习伙伴执行的每个操作都受到治理与审计——详见[设计即治理](#设计即治理)。

## 功能一览

- **讲解与练习** —— 把一道题或一个知识点拆成可消化的步骤，再针对性追问巩固，而不是直接倒答案。
- **真正跑起来的复习计划** —— 考研（政治/英语/数学/专业课）与证书考纲的「阶段级 + 日级」任务，附每周复盘报告，落后轨道会标红。
- **从错题到错题知识** —— 把每道错题归入五类原因（概念不清/审题失误/计算或操作失误/超纲或不熟/时间不够），把确认的薄弱点沉淀为长期记忆，后续会话直接复用。
- **模考监考** —— 限时模考，听力阶段结束即锁定答题卡，估分换算到官方 710 分制。
- **按官方评分档批改** —— 作文与翻译按官方档位判卷，含逐条错误清单与升格示范。
- **本地优先** —— 对话、记忆、定时任务与 API Key 全在本机；只用自己的模型 Key 也能完整离线使用。
- **受治理的自主性** —— 每次敏感操作（写入、发送、shell）都过审批关，并有回答「谁做了什么、为什么」的审计跟踪。

## 学习伙伴

每个学习伙伴都是一个带系统提示词、工具集与配套技能的人设。默认会话以**学习伙伴**身份打开；专精伙伴为每条备考线各配一位：

| 人设 | 职责 |
|---|---|
| 学习伙伴（默认） | 通用答疑、复习计划、错题整理与学习材料生成 |
| 四六级考官 | 定级测评、听力精讲、带监考流程的模考 |
| 四六级阅卷老师 | 按官方评分档批改作文与汉译英 |
| 考研规划师 | 四轨复习计划（政治/英语/数学/专业课）与周报复盘 |
| 考研分科导师 | 四科各有固定打法的分科答疑 |
| 证书教研员 | 从考纲抽知识点树 + 按评分点批改主观题 |
| 学习陪伴 | 错题归因、薄弱点记忆与「我今天该干什么」 |

## 设计即治理

治理是架构的一部分，而非外挂——伙伴无法为自己授予新权限，任何提示词也绕不过关卡。三个层级，均在本仓库中：

1. **硬底线。** 一组危险且不可逆的操作始终仅限人工执行。任何模式——包括完全自动审批——都不能降低这些底线；它们始终会升级到你的确认。
2. **渐进自主权阶梯。** 操作默认需要审批。一次性审批可以转为常驻规则，再转为配置白名单——每一步都是显式、可见、可撤销的。在自动审批模式下，reviewer 模型放行有把握的操作，把任何不确定的操作升级给你。
3. **回答「谁做了什么、为什么」的审计跟踪。** 每次工具调用都记录其审批来源——自动审批、用户审批或拒绝——连同 reviewer 的推理，与对话一起持久化。

无人值守运行永远不会自行审批：其请求会暂存在收件箱，直到人工响应。

## 自带模型

模型访问由你掌控：选择提供商、粘贴你的 Key、随时切换。开箱即用的提供商包括 **OpenAI**、**Anthropic Claude**、**Google Gemini**、**AWS Bedrock**、**Google Vertex AI** 与 **OpenAI Codex**，默认附带无需 Key 的 DuckDuckGo 联网搜索。

## 隐私

偷偷学让数据留在本机。一切都在本地运行：Agent 循环、你的对话、连接器令牌与模型密钥全部存放在应用本地密钥库。唯一的云端调用是发往你配置的模型提供商，使用你自己的 API Key。

## 从源码运行

前置要求：Python 3.10+、Node 20+，以及（用于桌面外壳）通过 [rustup](https://rustup.rs/) 安装的 Rust 工具链。

```shell
git clone https://github.com/light-misty/Stealth-Study.git
cd Stealth-Study

# 1. 一次性引导——创建 Python venv 到 .venv
#    （Windows 下请从 Git Bash 或 WSL 运行）
bash packaging/setup_dev_env.sh

# 2. 启动本地代理服务器
.venv/bin/stealthstudy-server --cwd ~/project --port 8765
#    （Windows: .venv\Scripts\stealthstudy-server.exe）

# 3. 在第二个终端中启动 UI
cd surfaces/gui
npm install
npm run dev        # 浏览器 UI 运行在 Vite 开发端口（1420）
```

每次启动时，独立服务器会在 `<state-dir>/sidecar-8765.token` 生成令牌；Vite 启动时读取该仅用户可访问的文件。直接调用 API 时请在 `X-StealthStudy-Token` 头部中发送该值。桌面应用使用内存中的启动令牌，从不写入磁盘。

要运行完整的桌面应用而非浏览器 UI，请把第 3 步换成 `npm run tauri dev`（在 `surfaces/gui/` 下运行）——Tauri 外壳会打开窗口并自行管理服务。

**测试：** `.venv/bin/pytest tests -q`（服务端）；在 `surfaces/gui` 中运行 `npm test` 与 `npm run e2e`（GUI 单元 + 端到端）。Windows 安装包通过 `packaging/build_windows.ps1` 构建；macOS DMG 构建当前已禁用（请从源码运行）。

## 仓库结构

| 目录 | 内容 |
|---|---|
| `stealth_study/` | Python 后端——Agent 引擎、模型提供商、连接器、MCP 客户端、记忆、自动化 |
| `stealth_study/personas/builtin/` | 学习伙伴人设——manifest 与其配套 `skills/` |
| `stealth_study/campus/` | 备考台域——批改引擎、错题本、复习队列、计划 |
| `surfaces/gui/` | 桌面应用——React UI + 承载服务器的 Tauri 外壳 |
| `surfaces/gui/src/campus/` | 备考台前端（四六级 / 考研 / 证书） |
| `stt/` | 语音转文本副进程 (Rust) |
| `tests/` | Python 测试套件 (pytest) |
| `docs/` | 产品需求与设计文档 |

## 文档

- [产品需求文档（偷偷学 PRD）](docs/PRD-StealthStudy.md)
- [设计文档](docs/dev/)
- [打包与发布说明](packaging/)
