<h1 align="center">偷偷学</h1>

<p align="center"><strong>偷偷学</strong> · <a href="#download">下载</a> · <a href="https://github.com/light-misty/HIU-WorkSpace/issues">Issues</a></p>


> **Beta** - 偷偷学正处于公开 beta 阶段：功能完全可用，支持自动更新，我们正在积极打磨细节。欢迎提交 [Issues](https://github.com/light-misty/HIU-WorkSpace/issues)。

**帮你搞定日常工作的 AI。** 偷偷学是一款开源 AI 协作伙伴，运行在桌面端，直接交付**成果**而不仅仅是对话：帮您审查代码漏洞并生成修复方案，生成精美文档，撰写附带数据的 Slack 回复，整理分类您的收件箱。平台优先推出**专业的安全协作代理**——攻击者已在利用 AI，防御者理应拥有同样的能力，且受到治理约束。

它运行在您的机器上，不绑定任何特定模型：您可以使用自己的 OpenAI、Anthropic、Google 或任意开放权重提供商的 API Key。您的数据始终留在本机——仅通过您选择的模型和集成发送出去。代理执行的每个操作都会受到治理和审计——详见[设计即治理](#设计即治理)。

![How 偷偷学 works](docs/assets/how-it-works.png)

## 下载

**⬇ macOS (Apple Silicon)**
<sub>macOS 12+ · 已签名并公证 · 支持自动更新</sub>

**⬇ Windows 10/11 (x64)**
<sub>安装包尚未进行代码签名，因此 SmartScreen 会弹出警告；签名工作正在进行中</sub>

打开应用，添加一个模型 Key，然后提出您的真实需求。

## 使用场景

选择一个协作代理，让它处理真实的工作，获得完成的交付物：

- **安全审查** - 扫描代码库及其依赖项中的真实风险。发现结果来自确定性扫描器（如 semgrep）加上模型推理；提出的修复方案在审批前会经过重新扫描和 diff 审查——修复者永远不会是唯一的检查者。
- **云态势审计** - 针对常见配置错误类别审计云配置，并起草修复计划。
- **事件分诊** - 处理安全或运维事件：跨工具收集上下文，起草时间线，准备报告。
- **日常工作** - 根据 CRM 和收件箱准备客户通话，将零散笔记整理为可执行的方案，生成文档和表格，让您的日历和 Slack 线程井井有条。
- **常驻自动化** - 早间简报、周报、频道监控——按计划执行，并附带完整记录。

专业协作代理开箱即用，已为特定工作配置好相应的工具、工作方式和检查机制。安全协作代理率先推出。

## 工作原理

1. 告诉 偷偷学您想要的结果——"准备客户简报"、"整理我的日历"、"起草报告"、"检查 Jira 和 GitHub 上的发布进度"。
2. 它将任务分解为步骤，跨您的桌面、文件和已连接应用进行工作。
3. 在执行任何重大事项之前——发送消息、修改日历、运行命令——它会与您确认，由您审批或调整方向。
4. 您拿到的是完成的交付物，而非待办清单。

底层架构：

```text
┌────────────────────────────────────────────────┐
│              偷偷学 桌面应用                    │  原生外壳 + GUI
├────────────────────────────────────────────────┤
│           本地代理服务器 (Python)               │  引擎 · 工具 · 连接器 - 基于 aisuite 构建
├───────────────┬────────────────┬───────────────┤
│  您的文件     │    您的工具    │   您的模型    │  一切都在您的机器上
│  和终端       │  25+ 连接器    │  任意提供商   │  使用您的 Key 运行
└───────────────┴────────────────┴───────────────┘
```

## 设计即治理

治理是架构的一部分，而非插件——代理无法为自己授予新权限，任何 prompt 也无法绕过关卡。三个层级，均在此仓库中：

1. **硬底线。** 一组危险且不可逆的操作始终仅限人工执行。没有任何模式——包括完全自动审批模式——可以降低这些底线；它们始终会升级至您确认。
2. **渐进自主权阶梯。** 操作默认需要审批。一次性审批可以转为常驻规则，再转为配置白名单——每一步都是显式的、可见的、可撤销的。在自动审批模式下，reviewer 模型放行不确定的操作并将任何不确定的操作升级给您；重复拒绝会触发断路器，暂停 reviewer 并将控制权交还给您。Reviewer 的判定是判断而非保证——底线和审计跟踪才是支撑它们的保障。
3. **回答"谁做了这件事，为什么？"的审计跟踪。** 每次工具调用都会记录其审批来源——自动审批、用户审批或拒绝——附带 reviewer 的推理过程——并与对话一起持久化。

无人值守运行永远不会自行审批：其请求会暂存于收件箱中，直到人工响应。发现漏洞？请查看 [SECURITY.md](SECURITY.md)。

## 功能一览

- **产出真实交付物** - 文档、表格、报告和网页，落地为可打开和分享的文件。
- **从 Slack 工作** - 在频道中提及 `@偷偷学`；会话在您桌面端打开，使用您的工具完成工作，结果以线程回复形式返回。
- **使用您的日常工具** - 25+ 集成，包括 GitHub、Slack、Jira、Notion、Linear、HubSpot、Outlook、monday.com、Gmail 和 Google Calendar，以及您的**终端和本地文件**。任何可通过 [MCP](https://modelcontextprotocol.io/) 访问的工具同样可以接入，且支持每个工具的独立控制。
- **按计划运行** - 用于重复性工作的自动化：早间简报、周报、常驻频道监控。运行结果在应用中展示，附带完整记录。
- **行动前先询问** - 写入、发送和 shell 命令均受审批门控，可选的自动审批模式仍会升级任何不确定的操作——详见[设计即治理](#设计即治理)。

## 自带模型

模型访问由您掌控：选择一个提供商，粘贴您的 Key，随时切换。开箱即用的支持列表：

**OpenAI · Anthropic · Google Gemini · BytePlus Ark · Volcengine Ark Agent Plan · Inkling (Thinking Machines) · GLM (Z.ai) · DeepSeek · Kimi (Moonshot) · Qwen · MiniMax · Mistral · Grok (xAI)**——以及通过 **Together** 和 **Fireworks** 接入的开放权重模型。

一份精选模型列表标注了我们已验证可用于 tool-calling 的模型。自行添加任何模型字符串请自担风险。

## 隐私

偷偷学让您的数据始终留在本机。一切都在本地运行：代理循环、您的对话、连接器令牌和模型密钥——全部存储在应用的本地机密存储中。唯一的云服务是一个为连接器代理 OAuth 握手的小型服务，而模型调用则通过您自己的 API Key 发送至您配置的提供商。您可以随时在不登录的情况下使用 App——通过手动创建的凭据/API Key 使用连接器。

## 从源码运行

前置要求：Python 3.10+、Node 20+，以及（用于桌面外壳）通过 [rustup](https://rustup.rs/) 安装的 Rust 工具链。

```shell
git clone https://github.com/light-misty/HIU-WorkSpace.git
cd HIU-WorkSpace

# 1. 一次性引导——创建 Python venv 在 .venv
#    （在 Windows 上，从 Git Bash 或 WSL 运行）
bash packaging/setup_dev_env.sh

# 2. 启动本地代理服务器
.venv/bin/openworker-server --cwd ~/some/project --port 8765
#    （Windows: .venv\Scripts\openworker-server.exe）

# 3. 在第二个终端中，启动 UI
cd surfaces/gui
npm install
npm run dev        # 浏览器 UI 运行在 Vite 开发端口上
```

每次启动时，独立服务器会在 `<state-dir>/sidecar-8765.token` 生成一个令牌；Vite 在启动时读取该仅用户可访问的文件。对于直接 API 调用，请在 `X-SS-Token` 头部中发送其值。桌面应用使用内存中的启动令牌，永远不会写入磁盘。

要运行完整的桌面应用而非浏览器 UI，将第 3 步替换为 `npm run tauri dev`（在 `surfaces/gui/` 下运行）——Tauri 外壳会启动窗口并自行管理服务。

测试：`.venv/bin/pytest`（服务端），`npm test` 和 `npm run e2e` 在 `surfaces/gui` 中（GUI 单元 + 端到端）。桌面安装包通过 `packaging/build_dmg.sh` / `packaging/build_windows.ps1` 构建。

## 仓库结构

| 目录 | 内容 |
|---|---|
| `ss/` | Python 后端——代理引擎、模型提供商、连接器、MCP 客户端、记忆、自动化 |
| `surfaces/gui/` | 桌面应用——React UI + 管理服务器的 Tauri 外壳 |
| `stt/` | 语音转文本副进程 (Rust)，用于语音输入 |
| `packaging/` | 安装包构建 (macOS DMG, Windows)、自动更新 manifest、开发引导 |
| `docs/` | 设计规范和决策记录 |
| `tests/` | 后端测试套件 |

## 基于 aisuite 构建

偷偷学的引擎基于 [**aisuite**](https://github.com/andrewyng/aisuite) 构建。

## 贡献

欢迎贡献和 bug 报告——请提交一个 [issue](https://github.com/light-misty/HIU-WorkSpace/issues) 或 pull request。应用支持自动更新，修复能快速到达所有安装。

对于任何 PR，请附上出现问题时的截图以及当前的修复效果。我们将很快推出您可以参与贡献的功能。

请注意，我们基于内部列表和目标积极开发，因此可能不会批准添加已在开发中或偏离我们愿景的功能的 PR。

## 许可证

MIT - 详见 [LICENSE](LICENSE)。
