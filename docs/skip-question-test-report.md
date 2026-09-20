# 跳过提问功能交付文档（OPE-153）

本文档覆盖功能说明、开发完成度评估、测试报告与使用指南。功能移植自远程分支
`issue/skip-question-card`（两个提交，作者 Devika Verma），适配当前 main 的 `stealth_study/`
包结构后在本分支 `feat/skip-question-card` 交付。

## 1. 功能说明

### 1.1 背景与动机

问题卡片是收件箱中唯一没有退出途径的交互类型：审批有"拒绝"、目录请求有"拒绝"、
计划有"驳回"、通知有"忽略"，而问题只能作答或搁置。当用户无法回答时——尤其在选项
穷尽且 `allow_text: false` 的卡片上——只能编造一个误导代理的答案，或放弃整个会话。
OPE-153 为问题卡片补上"跳过"这一退出途径。

### 1.2 功能行为

| 场景 | 控件 | 行为 |
|---|---|---|
| 单问题卡片 | 跳过 | 以哨兵值结算整卡，语义等同作答后收卡 |
| 分组卡片当前步 | 跳过此问题 | 跳过当前问题，步进器照常前进 |
| 分组卡片剩余步骤 | 全部跳过 | 跳过其余所有问题；已给出的回答保留 |

- 跳过入口始终存在，不受 `allow_text` 限制——禁用自由输入的卡片正是用户最可能
  被困住的地方。
- 代理侧收到跳过时：回答为 `null`（而非空串），附带 `skipped` 字段指明被跳过的
  问题，以及 `SKIP_NOTE` 提示文本。
- Slack 镜像：带选项的问题在选项按钮之后附加 Skip 按钮；分组问题刻意保持无按钮
  （保留 "(Open the app to respond.)" 纯文本回退，逐题跳过在应用内提供）。

### 1.3 数据契约

- 哨兵值 `SKIP_SENTINEL = "__ocw_skip__"`：GUI（InboxItemCard.tsx 的 `SKIP`）、
  Slack 按钮、文本型渠道共用，`answer_result()` 统一映射为 `null` 回答。
- `answer_result()` 返回形态：
  - 单问题跳过：`{"answer": null, "skipped": true, "note": SKIP_NOTE}`
  - 分组部分/整卡跳过：`{"answers": {…: null}, "skipped": [被跳过的键], "note": SKIP_NOTE}`
  - 未发生跳过的卡片不携带 `skipped`/`note` 键，不给代理的结果引入噪音。
- 引擎侧：全部跳过的卡片结算为 `denied` 而非 `ok`（answers 非空不再等同于
  "有人回答"）；`_note_ask_replies` 丢弃 `null` 值，避免把字面量 "None" 记为
  用户发言。
- `SKIP_NOTE` 措辞刻意不对称："不要把该问题再抛回给用户"为绝对指令（跳过存在的
  意义就是防循环保证）；"选择安全默认继续"为条件指令（不可撤消的决策不猜测）。

### 1.4 移植说明

上游分支基于重构前的 `coworker/` 包结构，与本分支合并基（main）相距 349 个提交。
移植以 cherry-pick 完成，保留原作者署名：

- `coworker/engine.py` → `stealth_study/engine.py`、`coworker/tools/ask.py` → `stealth_study/tools/ask.py`、
  `coworker/interactions.py` → `stealth_study/interactions.py`（包重命名适配）。
- InboxItemCard.tsx 与 main 新增的 `approvalItemFromParked` 同位插入冲突：两者均保留。
- tests/test_interactions.py 导入块冲突：保留 `stealth_study.*` 路径并新增 `SKIP_SENTINEL` 导入。
- e2e 规格注释中的旧包路径同步更正为 `stealth_study/tools/ask.py`。
- 哨兵语义、null 回答约定、按钮样式与测试断言全部保留上游原样。

## 2. 完成度评估

- 核心业务逻辑：完整。哨兵值编码/解码、null 回答映射、单步/整卡跳过、已答保留、
  引擎结算、审计记录（`_note_ask_replies`）、Slack 镜像路径全部就位且有测试覆盖。
- UI/UX：符合设计规范。按钮复用既有样式体系（新增 `BTN_SKIP`，安静风格、刻意不用
  "拒绝"的危险红）；i18n en/zh 全覆盖；`question-skip` testid 契约与 e2e 对齐。
- 错误处理与边界：覆盖。JSON null 防御（等价哨兵处理）、文本型渠道裸哨兵跳过整卡、
  空解析回退 `{"answer": ""}` 保持原语义、部分作答与部分跳过的混合结算、防重问
  绝对指令。

## 3. 测试环境

- OS：Windows 11
- Python 3.12.13（主仓 `.venv`；从工作树根以 `python -m pytest` 运行，确保 `import stealth_study`
  解析到工作树代码）
- Node v22.18.0、Playwright 1.61.1（Chromium，Desktop Chrome 档案）
- 测试对象：分支 `feat/skip-question-card` @ `6719bf6`（已合并 main `f59415a`）

## 4. 后端功能测试

### 4.1 功能定向用例

`pytest tests/test_ask_user_upgrades.py tests/test_interactions.py` — 23 passed。

跳过专项包括：单问题跳过得到 null 而非空串；分组跳过命名被跳过的问题；裸哨兵跳过
整张分组卡；完全作答的卡片不携带 skip 键；镜像 Skip 按钮编码哨兵值并映射回 null
回答；无选项（自由文本）问题不渲染任何按钮；既有 back-compat 断言（`answer_result`
空串语义等）保持不变。

### 4.2 侵入预算守卫

`pytest tests/campus/test_intrusion_budget.py tests/campus/test_mount.py` — 10 passed。
本功能的生产文件足迹已按 logging-system 分支的登记先例写入两个守卫的登记集。

### 4.3 全量回归

`pytest tests -q`（合并 main 后复跑）：3365 passed / 30 skipped / 1 failed。

唯一失败 `tests/test_secrets.py::test_secrets_file_is_restricted` 为 main 上的预存
环境缺陷（在 main `f59415a` 上复现）：中文 Windows 用户名使 `icacls` 输出按 utf-8
解码抛出 `UnicodeDecodeError`（字节 0xd2）， ACL 断言随之以 `TypeError` 失败。
与本功能无关，建议后续单独修复（按系统 locale 解码 `icacls` 输出）。

## 5. 前端功能测试

- 类型检查 `npx tsc --noEmit` — 通过（exit 0）。
- 单元测试 `npm test`（Vitest）— 84 个测试文件 / 581 用例全部通过。
- e2e（Playwright，网络层全 mock，无需 Python 后端）：
  - `ask-skip.spec.ts` 4/4 通过：
    1. 单问题可跳过，结算为 skipped 而非空白；
    2. 无自由输入转圜的卡片仍提供跳过（此时是唯一出路）；
    3. 分组卡片单步跳过后步进器照常前进、其余步骤可正常作答；
    4. 全部跳过结算剩余步骤且保留已给出的回答。
  - 全套 257 用例：254 通过、3 失败。3 例失败在 main（`f59415a`）上完全复现
    （`composer.spec.ts:5`、`composer.spec.ts:45`、`session-intro.spec.ts:38`），
    属 main 预存失败，与本功能无关。

## 6. 兼容性、性能与安全

- 兼容性：目标浏览器为 Chromium（与 CI 的 `npm run e2e` 一致）；旧数据兼容由
  back-compat 用例保障（纯字符串选项、旧持久化条目的 `{answer}/{answers}` 语义
  不变）；界面文案 en/zh 双语就位。
- 性能：跳过与作答走同一条 Inbox resolve 路径，不增加网络往返；后端为纯映射，
  无 I/O；渲染开销为每卡至多两个文本按钮。e2e 单场景耗时约 7.5s（含应用启动）。
  未做独立基准测试——改动不触及热路径。
- 安全：跳过不授予任何新权限——Slack 镜像中能点击选项的用户本就可以决定问题，
  跳过只是在其既有能力上增加"拒绝作答"这一更温和的选项；应用内跳过走既有
  Inbox resolve 接口与既有 `X-SS-Token` 鉴权；`SKIP_NOTE` 阻止代理在重大决策上
  凭空代答，降低误操作风险。

## 7. 已知限制与说明

1. `test_secrets_file_is_restricted` 预存失败（见 4.3），建议按系统 locale 解码
   `icacls` 输出后单独修复。
2. main 预存 e2e 失败 3 例（见 5），属 composer / session-intro 域，建议由相应
   负责方处理。
3. Slack 分组问题无逐题跳过（设计决定）：任何按钮都会把镜像从纯文本路径切到交互
   路径并失去 "(Open the app to respond.)" 回退。
4. 跳过后的代理行为依赖模型遵循 `SKIP_NOTE`：防重问为绝对指令；"选安全默认"为
   条件指令，重大或难以撤消的决策应停下说明所需信息。

## 8. 使用指南

### 8.1 应用内（收件箱与会话内嵌卡片）

- 单问题卡片：点击"跳过"。
- 分组卡片：当前步点"跳过此问题"（步进器前进，可回头补答）；或点"全部跳过"
  （已给出的回答保留，其余全部跳过）。
- 跳过即结算：卡片进入已解决状态，代理立即收到通知并继续工作。
- 中文界面文案：跳过 / 跳过此问题 / 全部跳过。

### 8.2 Slack 镜像（无人值守会话）

- 带选项的问题：点击选项按钮之后的 Skip。
- 分组问题与自由文本问题：按提示打开应用，在应用内作答或跳过。

### 8.3 代理侧（供模型与技能作者参考）

- 收到 skipped（null 回答）时：若可安全推进，选择合理默认、继续，并说明所选
  方向；若决策重大或难以撤消，不要猜测——说明需要什么信息，等用户回来处理。
- 绝不把被跳过的问题重新问一遍。

## 9. 交付物清单

| 提交 | 说明 |
|---|---|
| 94a9584 | feat(inbox): 问题卡片支持跳过提问 |
| 7c1abac | feat(inbox): Slack 镜像渠道的问题支持跳过 |
| 9f32bb5 | test(campus): 登记 skip-question-card 功能的生产文件足迹 |
| 6719bf6 | Merge branch 'main' into feat/skip-question-card |

分支 `feat/skip-question-card` 已发布至 Stealth-Study 远程；开发工作树位于
`../Stealth-Study-skip-question-card`。

## 10. 结论

功能自 `issue/skip-question-card` 完整移植至当前 main 结构，定向测试全部通过，
全量回归除 main 预存的 1 例后端环境失败与 3 例 e2e 失败（均在 main 上复现）外
全绿。功能达到可交付状态。
