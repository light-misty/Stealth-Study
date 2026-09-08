"""
## 任务规范

1. 重要：在每次任务开始前，你必须加载 superpowers skill，并严格遵守其规范。
2. 未经过我的允许，禁止执行 git 暂存、提交、推送。
3. git-commit 提交信息使用中文，遵循约定式提交信息。
4. 重要：严令禁止你将自己列为 GitHub 贡献者、共同创作者等。
5. 有关 git 的操作，请使用 git-commit skill、gh-cli skill。
6. 在任务过程中，你需要积极调用相关 skills，例如：执行代码智能暂存请调用 git-commit skill。
7. 你需要严格遵守数据诚实规则，不要不懂装懂，如果存在不确定的知识，请积极执行联网搜索。
8. 如果存在不确定的内容，请积极向我提问，不要擅作主张。
9. 严格遵守最小改动原则：优先编辑现有代码、不新建不必要文件、不添加多余注释。
10. 在任务过程中，如果发现有其它文件改动并且不在你的任务范围内，说明那是协作者正在进行的任务，你需要确认它是否会对你的任务造成影响，如果没有影响则不需要关注并跳过它。
11. 日志文件或其他文件可能通过 .gitignore 被排除在工作区之外，你需要通过命令来查看日志。
12. 保持对话语言为中文。
13. 在生成代码时**不要添加注释**。
14. 在任务过程中禁止使用 emoji。
15. 本机操作系统为 Windows 11。
16. 身份专属规则：如果你的名字是 CatPaw (AI)，请你在任务过程中优先使用 powershell 命令，尽量不要使用 bash 命令。

## Reasoning Effort

Absolute maximum with no shortcuts permitted.
You MUST be very thorough in your thinking and comprehensively decompose the problem to resolve the root cause, rigorously stress-testing your logic against all potential paths, edge cases, and adversarial scenarios.
Explicitly write out your entire deliberation process, documenting every intermediate step, considered alternative, and rejected hypothesis to ensure absolutely no assumption is left unchecked.
"""

# OpenWorker 项目指南

## 项目概述

OpenWorker 是一个开源的 AI 协作伙伴平台，运行在桌面端，支持多模型提供商（OpenAI、Anthropic、Google、Ollama 等），以本地优先的方式执行真实工作。项目代号为 `coworker`，基于 [aisuite](https://github.com/andrewyng/aisuite) 构建。

## 技术栈

### 后端 (Python)
- **语言**: Python 3.10+
- **Web 框架**: FastAPI + uvicorn
- **代理引擎**: aisuite (LLM 统一抽象层) + 自定义 `TurnEngine`
- **TUI 框架**: Textual
- **数据验证**: Pydantic v2
- **数据库**: SQLite (记忆存储)
- **MCP 客户端**: mcp >=1.28.1,<2
- **配置格式**: TOML (tomllib/tomli)

### 前端 (桌面应用)
- **UI 框架**: React 18 + TypeScript 5.5
- **桌面外壳**: Tauri 2 (Rust)
- **构建工具**: Vite 5
- **样式方案**: Tailwind CSS 3 + PostCSS + Autoprefixer
- **状态管理**: React Hooks (useState/useEffect/useCallback)
- **国际化**: i18next + react-i18next (en, zh)
- **Markdown 渲染**: react-markdown + remark-gfm
- **PDF 渲染**: pdfjs-dist
- **表格处理**: xlsx

### Rust 组件
- **桌面外壳**: Tauri 2 (crate: `openworker-desktop`)
- **语音转文本**: ocw-stt (基于 whisper-rs + cpal)

### 主要依赖项

#### Python 核心依赖
- `openai>=1.0` — OpenAI 提供商
- `anthropic>=0.40` — Anthropic Claude 原生 API
- `google-genai>=1.0` — Google Gemini 原生 API
- `google-auth>=2.23` — Vertex AI 认证
- `textual>=1.0` — TUI 框架
- `fastapi>=0.110`, `uvicorn[standard]>=0.27` — HTTP 服务器
- `aisuite` — 统一 LLM 访问层 (git pinned)
- `pydantic>=2` — 数据类验证
- `mcp>=1.28.1,<2` — MCP 客户端
- `httpx>=0.27` — HTTP 客户端
- `websockets>=13` — Slack relay 传输
- `ddgs>=9` — DuckDuckGo 无密钥搜索
- `croniter>=2` — cron 调度计算
- `pypdf>=5`, `pypdfium2>=4` — PDF 处理
- `pyyaml>=6` — Persona manifest 解析

#### Python 可选依赖
- `[dev]`: pytest>=8, pytest-asyncio, httpx — 开发测试
- `[messaging]`: python-telegram-bot>=21, slack-bolt>=1.18, aiohttp>=3.9 — 消息集成
- `[browser]`: playwright>=1.44 — 浏览器自动化
- `[bedrock]`: boto3>=1.34 — AWS Bedrock 提供商

## 项目结构

```
HIU-WorkSpace/
├── .claude/                    # Claude Code 启动配置
│   └── launch.json
├── .github/workflows/          # GitHub Actions CI/CD
│   ├── ci.yml                  # 持续集成
│   └── release.yml             # 发布流程
├── .venv/                      # Python 虚拟环境
├── assets/                     # 静态资源
├── coworker/                   # Python 后端核心包
│   ├── __init__.py
│   ├── cli.py                  # CLI 入口 (openworker TUI)
│   ├── config.py               # 配置管理 (分层 TOML)
│   ├── engine.py               # 代理引擎 (TurnEngine)
│   ├── permissions.py          # 权限引擎
│   ├── conversations.py        # 对话存储
│   ├── sessions.py             # 会话管理
│   ├── memory/                 # 记忆存储 (SQLite)
│   ├── providers/              # LLM 提供商实现
│   │   ├── base.py             # ProviderClient 抽象基类
│   │   ├── openai_provider.py
│   │   ├── anthropic_provider.py
│   │   ├── gemini_provider.py
│   │   ├── bedrock_provider.py
│   │   ├── vertex_provider.py
│   │   ├── codex_provider.py
│   │   └── registry.py / router.py
│   ├── connectors/             # 外部服务连接器
│   ├── tools/                  # 工具注册 (shell, files, git, search, 等.)
│   ├── skills/                 # 技能定义
│   ├── personas/               # 人设定义 (builtin + 自定义)
│   ├── mcp/                    # MCP 客户端
│   ├── automation/             # 定时自动化 (cron)
│   ├── teams/                  # Teams 功能 (board, journal, MCP server)
│   ├── tui/                    # 终端界面 (Textual)
│   ├── web/                    # Web 工具 (fetch, guard)
│   ├── testing/                # 测试辅助 (fake_slack)
│   └── server/                 # HTTP 服务器 (FastAPI)
│       ├── app.py
│       └── run.py              # 入口: openworker-server
├── surfaces/gui/               # 桌面 GUI 应用
│   ├── src/                    # React 前端源码
│   │   ├── App.tsx
│   │   ├── main.tsx
│   │   ├── api.ts              # REST/WebSocket API 封装
│   │   ├── components/         # React 组件
│   │   ├── connectors/         # 连接器 UI
│   │   ├── providers/          # 模型提供商设置 UI
│   │   ├── locales/            # i18n 翻译文件
│   │   └── types.ts
│   ├── src-tauri/              # Tauri Rust 代码
│   │   ├── Cargo.toml
│   │   ├── tauri.conf.json
│   │   └── src/lib.rs
│   ├── e2e/                    # Playwright 端到端测试
│   ├── package.json
│   ├── vite.config.ts
│   ├── tailwind.config.js
│   └── playwright.config.ts
├── stt/                        # Rust 语音转文本组件
│   ├── Cargo.toml
│   └── src/lib.rs
├── tests/                      # Python 测试套件
│   ├── conftest.py             # 共享 fixtures (isolated_state_dir, fake_slack)
│   └── test_*.py               # 测试文件 (~130 个)
├── packaging/                  # 打包与发布
│   ├── build_dmg.sh            # macOS DMG 构建
│   ├── build_windows.ps1       # Windows MSI/NSIS 构建
│   ├── setup_dev_env.sh        # 开发环境初始化
│   └── make_update_manifest.py
├── scripts/                    # 辅助脚本
├── docs/                       # 文档与规范
├── ui-mocks/                   # UI 设计稿
├── reports/                    # 评估报告
├── pyproject.toml              # Python 项目配置
├── LICENSE                     # MIT 协议
└── README.md
```

## 构建与测试命令

### 环境初始化
```powershell
# Windows 下从 Git Bash 或 WSL 运行
bash packaging/setup_dev_env.sh
```

### 后端 (Python)
```powershell
# 运行测试
.venv\Scripts\pytest tests -q

# 或直接使用 pytest
pytest tests -q

# 启动本地代理服务器
.venv\Scripts\openworker-server --cwd <项目路径> --port 8765

# 启动 TUI
.venv\Scripts\openworker
```

### 前端 (GUI)
```powershell
cd surfaces/gui

# 安装依赖
npm install

# 开发模式 (Vite dev server, 端口 1420)
npm run dev

# TypeScript 类型检查
npx tsc --noEmit

# 单元测试
npm test

# 端到端测试 (Playwright)
npm run e2e

# 带 UI 的 e2e 测试
npm run e2e:ui

# 生产构建
npm run build

# Tauri 桌面开发模式
npm run tauri dev

# Tauri 生产构建
npm run tauri build
```

### Rust STT 组件
```powershell
cd stt
cargo build --release
```

### 桌面安装包构建
```powershell
# macOS DMG (在 macOS 上运行)
bash packaging/build_dmg.sh

# Windows MSI + NSIS (在 Windows 上运行)
powershell packaging/build_windows.ps1
```

## 编码约定

### Python 代码风格
- 使用 `from __future__ import annotations` 启用PEP 604类型注解
- 使用绝对导入路径
- 引用类型时使用 `from typing import ...` (Optional, Any, 等.)
- 使用 `@dataclass` 定义数据类
- 模块级文档字符串 (`"""..."""`) 描述职责
- 使用枚举 (`class Foo(str, Enum)`) 定义常量集合
- 命名规范: `snake_case` (函数/变量/模块), `PascalCase` (类), `UPPER_SNAKE_CASE` (常量)
- 使用 `Optional[X]` 表示可空类型 (Python 3.10 不使用 `X | None` 语法)

### TypeScript/React 代码风格
- 函数式组件 + Hooks (不使用 class 组件)
- 使用 `import type` 分离类型导入
- 命名规范: `camelCase` (函数/变量), `PascalCase` (组件/类型)
- 文件名: 组件使用 PascalCase (如 `ApprovalCard.tsx`), 工具函数使用 camelCase
- 国际化通过 `useTranslation` hook 实现
- API 调用统一通过 `surfaces/gui/src/api.ts` 封装

### 架构模式

1. **提供商抽象层**: `coworker/providers/base.py` 定义 `ProviderClient` ABC，各提供商实现该接口
2. **代理引擎**: `TurnEngine` (engine.py) 驱动模型↔工具交互循环，使用 asyncio
3. **权限引擎**: 多级批准系统 (硬底线、渐进自主权、审计跟踪)
4. **工具注册**: 工具通过 `ToolRegistry` 注册，支持动态发现
5. **分层配置**: 默认值 → 全局 (<state-dir>/config.toml) → 工作区 (<workspace>/.coworker/config.toml)
6. **连接器**: 通过适配器模式集成外部服务 (Slack, GitHub, Gmail, 等.)
7. **自动化**: cron 驱动的定时任务，支持持久化调度
8. **MCP 集成**: 兼容 Model Context Protocol，接入外部工具服务器

### 测试约定
- 测试框架: pytest + pytest-asyncio
- 异步模式: `asyncio_mode = "auto"` (所有 async test 自动识别)
- Fixtures: 使用 `conftest.py` 共享 fixtures
- 状态隔离: 每个测试使用独立的状态目录 (`isolated_state_dir` autouse fixture)
- 外部服务: 使用 FakeSlack 等模拟真实服务，无网络依赖
- 参数化: 广泛使用 `@pytest.mark.parametrize`

## CI/CD 配置

### CI (`.github/workflows/ci.yml`)
触发条件: `push`, `pull_request`

 Jobs:
- **pytest**: Python 后端测试
  - 运行环境: ubuntu-latest, Python 3.12
  - 安装: `pip install -e ".[messaging,dev,bedrock]"`
  - 执行: `pytest tests -q`
- **gui-unit**: GUI 单元测试
  - 运行环境: ubuntu-latest, Node 20
  - 执行: `npm ci` → `npx tsc --noEmit` → `npm test`
- **gui-e2e**: GUI 端到端测试
  - 运行环境: ubuntu-latest, Node 20
  - 安装 Playwright Chromium
  - 执行: `npm run e2e`

### Release (`.github/workflows/release.yml`)
触发条件: tag push `v*` / `app-v*`, `workflow_dispatch`

 Jobs:
- **build**: 跨平台构建
  - macOS arm64 (Apple Silicon)
  - macOS x64 (Intel, macos-15-intel)
  - Windows (msi + NSIS exe)
  - 使用 PyInstaller 打包 Python sidecar
  - Tauri 构建应用外壳
  - 自动更新签名 (minisign, 可选)
- **release**: 发布
  - 创建 GitHub Draft Release
  - 生成自动更新 manifest (latest.json)
  - 验证 tag 版本与 tauri.conf.json 一致

## CLI 入口点

| 命令 | 入口 | 用途 |
|------|------|------|
| `openworker` | `coworker.cli:main` | TUI 启动 (默认 code skill) |
| `openworker-server` | `coworker.server.run:main` | HTTP 服务器启动 |
| `openworker-connectors` | `coworker.connectors.cli:main` | 连接器管理 CLI |
| `ocw` | `coworker.teams.cli:main` | Teams 功能 (board, journal, MCP) |

## 安全与治理

项目实现了三级治理架构:
1. **硬底线**: 危险操作始终需人工批准，不可绕过
2. **渐进自主权**: 单次批准 → 持久规则 → 配置白名单
3. **审计跟踪**: 所有工具调用记录完整来源

权限模式:
- `plan`: 仅规划，不执行
- `interactive`: 默认模式，敏感操作需批准
- `auto`: 批准模式，有审核模型
- `auto-approve`: 自动批准 (带 reviewer shadow)
- `bypass-approvals`: 绕过批准 (调试用)

## 注意事项

- 状态目录: 默认 `~/OpenWorker` (或 `%APPDATA%\coworker`)，可通过 `COWORKER_STATE_DIR` 环境变量覆盖
- 开发令牌: 本地开发通过 `X-OpenWorker-Token` 头部认证
- 端口配置: 后端 HTTP 默认 8765，前端 Vite 开发服务器固定 1420
- 国际化: 支持英文 (en) 和中文 (zh)，翻译文件在 `surfaces/gui/src/locales/`
- Python 版本下限 3.10；使用 `tomli` 后备 tomllib
- 测试使用独立状态目录，避免污染开发环境
