# 登录功能删除计划文档 — G-06 登录去除（V0.1 · T20 子任务）

| 项 | 内容 |
|---|---|
| 文档编号 | dev/PLAN-remove-login |
| 阶段 | V0.1 · T20 子任务（G-06 / INF-07） |
| 版本 | v1.0 |
| 日期 | 2026-09-14 |
| 作者 | 徐名可 |
| 上游依据 | `PRD-StealthStudy.md` §3.3.1（减法决策）、§3.3.3（登录边界定义）、§4.9（不做清单）、§11.1 D6；`01-系统架构设计.md` §6 #8；`04-前端设计.md` §4.8；`07-开发任务分解.md` §5 T15/T20；`08-测试与验收方案.md` §5 F-2/F-3 |
| 分支与工作树 | 分支 `feat/remove-login`（已发布）；工作树 `D:\DeskTop\Stealth-Study-remove-login`（基线 `main` = `b1c5595`，已含 T01-T07 全部成果） |
| 本档定位 | G-06「登录去除」的必要性论证、实施范围、风险与验证方案、时间线与责任人分配 |
| 审批状态 | 待审批（见 §8） |

---

## 1. 前置文档审查结论

对仓库 `docs/` 全部文档（`PRD-StealthStudy.md`、`dev/01`~`dev/09`、`dev/v0.0-spike-report.md`、`dev/交付文档/T01`~`T07`）做了全量关键词审查（`登录`/`login`/`signin`/`sign-in`/`sign_in`/`认证`/`账号`/`account`）。

### 1.1 审查命中分布

| 文档 | 命中数 | 内容性质 |
|---|---|---|
| `PRD-StealthStudy.md` | 41 | **产品需求与决策**（非实施记录） |
| `dev/04-前端设计.md` | 16 | **设计规格**（侵入点 #8 的代码形态） |
| `dev/01-系统架构设计.md` | 4 | 侵入点登记表 #8 |
| `dev/07-开发任务分解.md` | 4 | T15 / T20 的任务边界 |
| `dev/08-测试与验收方案.md` | 2 | F-2 / F-3 验收项 |
| `dev/03-API接口设计.md` | 1 | 「G-05/06/07 无后端端点」说明 |
| `dev/交付文档/T01`~`T07` | **0** | 无任何登录相关记录 |
| `dev/v0.0-spike-report.md` | **0** | 无任何登录相关记录 |

### 1.2 审查结论（关键）

**不存在**「登录功能删除」的**实施记录**：T01-T07 全部交付文档与 v0.0 spike 报告对登录零命中，说明该功能从未被删除过。

**存在**一份已拍板的**处置决策**，且其结论是**不物理删除**：

- `PRD §3.3.1` 决策结论：**「统一策略：入口隐藏 + 能力禁用 + 代码保留（Feature Flag 屏蔽），不做物理删除。」**
- `PRD §11.1 D6`：**「Flag 屏蔽 + 代码保留，不物理删除（用户确认）」**，日期 2026-09-08。
- `PRD §3.3.2` 三条自洽论证：语义界定（铁律保护功能模块而非入口可见性）、效果等价（可观测层面隐藏 ≡ 删除）、风险与合规（物理删除成本远高于保留）。
- `PRD §4.9` 不做清单第 2 项：用户注册 / 登录 / 账号体系 / 云同步 / 多端同步。

### 1.3 对本次任务的处置

任务要求「若不存在此类内容，需立即制定删除计划并在获批后按文档执行」。因文档中**不存在物理删除计划**，本档即为该计划文档。

**计划口径按 PRD D6 已批准决策执行**：以 **Feature Flag 屏蔽实现「用户可感知层面的彻底登录去除」**，不做物理删除。理由见 §2。

---

## 2. 功能删除的必要性分析

### 2.1 开源项目二次开发背景

本项目基于开源 AI 协作伙伴平台（仓库代号 `ss`，上游为 aisuite 衍生实现）二次开发，产品化为「偷偷学 StealthStudy」——面向四六级 / 考研 / 证书备考的本地备考台。二次开发只做加法：campus 域 9 处侵入点 + 11 个后端文件全部 L0 新增。

### 2.2 原有登录功能在二次开发后已完全失效

四方面论证：

**（一）产品定位层面 —— 与核心卖点直接冲突。**
`PRD §1` 产品一句话定义：**「装在电脑里的本地备考作战室 —— 不登录、数据只存在自己硬盘、模型由你自配的云端 API Key 驱动」**。「不登录」是三条核心卖点之一（另两条：数据本地、模型自配）。

**（二）能力依赖层面 —— 零下游依赖。**
上游的云登录（OpenWorker Cloud Sign-In）服务于三件事：① 云端托管模型额度；② Cloud 连接器（Gmail / Slack / GitHub / Calendar）OAuth 中转；③ 云同步 / 多端同步。
本项目对这三件事的处置：
- ① **模型供给改为用户自配云端 API Key**（`PRD §11.1 D7`），Key 只存本机配置、不经过任何本产品服务器 —— 登录不再承担模型供给职能。
- ② 连接器降级为**纯可选增强**（G-07），**不授权也能 100% 使用学习功能**（`PRD §3.3.3` 边界定义）。
- ③ **云同步 / 多端同步明确不做**（`PRD §4.9` 不做清单第 2 项、§11.1 D7 相关）。

结论：登录功能在本产品中**不被任何学习链路依赖**，删除其用户可感知入口**不会导致任何既有能力失效**。

**（三）可观测行为层面 —— 登录路径已完全不可达。**
Flag 关闭后，全部入口与可见性被切断：
- Onboarding 流程无登录提示带、无「登录以启用一键配置」引导；
- Sidebar 账户菜单无「未登录」字样、无「登录」按钮、无「登出」项；
- 账户行仅显示本地状态，不出现 `?` 头像与云端状态点；
- 无任何登录/注册/授权页面、无浏览器外跳、无轮询。

按「可观测行为」判定，产品已**不需要也不提供**任何形式的注册 / 登录即可使用全部学习功能（`PRD §3.3.1` 产品承诺）。

**（四）资产完整性层面 —— 与「禁止删除」铁律不冲突。**
铁律保护的是**可复用的能力单元**（Persona / Skills / Automation / Memory / Providers / Tools / Teams / Reviewer / PDF / Compaction / Permissions / Audit）。「登录」属**入口型 / 账号型设施**，删除其可见性不造成任何能力资产损失；而**物理删除**才会造成不可逆损失（见 §4.1 风险 R2）。

### 2.3 必要性结论

登录功能在二次开发后的产品中**已功能性失效**：不承担模型供给、不被学习链路依赖、与核心卖点冲突、且其可观测入口必须彻底移除。
**处置方式必须是「入口隐藏 + 代码保留」，而非物理删除** —— 这既是已批准决策（D6），也是风险最低、完全可逆、唯一不违反铁律的实现路径。

---

## 3. 实施步骤

全部改动落在 3 处（复刻 G-05 语音关闭的已验证方案）。

### 3.1 步骤总览

| 步 | 内容 | 文件 | 提交信息 | 推送 |
|---|---|---|---|---|
| S1 | 追加登录开关 `showLogin()` | `surfaces/gui/src/flags.ts` | `feat(campus): flags.ts 追加 showLogin 登录入口开关（G-06）` | 是 |
| S2 | Sidebar 账户区登录短路 | `surfaces/gui/src/components/Sidebar.tsx` | `feat(campus): Sidebar 账户区按 showLogin 短路登录入口（G-06 侵入点 #8）` | 是 |
| S3 | Onboarding 登录带短路 | `surfaces/gui/src/components/Onboarding.tsx` | `feat(campus): Onboarding 登录提示带按 showLogin 短路（G-06 侵入点 #8）` | 是 |
| S4 | 回归验证 + 交付文档 | `tests/`、`docs/dev/交付文档/` | `test(campus): 补登录开关双态回归用例；docs: 新增 G-06 交付文档` | 是 |

**节奏约束**：每步一提交、每提交即推送；禁止合并为一次性提交；禁止推送到 `main`。侵入点 #8 的 S2/S3 必须**独立成笔**以便单点回滚（`07 §7` 交付节奏）。

### 3.2 S1 — `flags.ts` 追加 `showLogin()`

**位置**：`surfaces/gui/src/flags.ts` 文件末尾（紧随既有 `showPersonas()`）。
**形态**（`04 §4.8` 子改动 8.1）：

```ts
/** StealthStudy v1.1（PRD G-06）：登录入口开关。
 *  默认关闭 = 用户可感知层面无登录入口；代码与 i18n 文案全部保留，可逆。 */
export const showLogin = () => flag("ocw.flag.login", false);
```

**要点**：复用既有 `flag(key, fallback)`（`flags.ts:8-19`，localStorage），零新增依赖、不新建配置文件、不写 `config.toml`（`ADR-04`）、默认 false 写死、`localStorage.setItem("ocw.flag.login","1")` 可逆恢复。

### 3.3 S2 — `Sidebar.tsx` 账户区短路

**位置与形态**（`04 §4.8` 子改动 8.2 / 8.3）：

| 子项 | 原位置 | 改法 |
|---|---|---|
| 8.2 账户菜单未登录分支 | `:1174-1198` | 三元追加一档：`cloud?.signed_in ? (...) : showLogin() ? (未登录分支) : null`，使 flag 关闭时菜单不出现「未登录」提示行与「登录」按钮 |
| 8.3 账户行文案与登出项 | `:1255-1256` 及登出项 `cloud?.signed_in && (...)` | 账户行李文案三元追加一档：flag 关闭时不再渲染 `t("sidebar.not_signed_in_row")`；登出菜单项同时受 `showLogin()` 约束 |

**保留不动**：`api.ts` 的 `cloudLogin` / `cloudLogout` / `waitForCloudSignIn`、`connectors/CloudSignIn.tsx`、`AccessSection.tsx`、连接器 OAuth 逻辑（归 Integrations，`PRD §3.3.3`）。

### 3.4 S3 — `Onboarding.tsx` 登录带短路

**位置与形态**（`04 §4.8` 子改动 8.4）：
- `:240-280` 的登录提示带（`onboarding.signin_for_oneclick` 文案带 + `ob-cloud-signin` 按钮 + `ob-tools-signedin` 已登录态卡）**整块包** `{showLogin() && (...)}`。
- **保留**：step 1 的 provider 表单（仅 API Key）—— 那是模型配置不是登录（`PRD §3.3.3` 边界定义），G-06 验收的是「无登录 / 注册 / 授权页面」。
- **连带处理**：登录带包裹后，step 1 底部的「静默跳过 / 黑色下一步」双态 footer 需保持可用（原逻辑依赖 `cloud?.signed_in`），确保 flag 关闭时用户仍能正常进入 step 2。

### 3.5 明确不做（防止扩散）

- **不删文件**：`connectors/CloudSignIn.tsx`、`AccessSection.tsx`、`api.auth.test.ts` 等一律保留。
- **不删 i18n key**：`sidebar.not_signed_in`、`onboarding.sign_in` 等全部保留（仅无入口渲染）。
- **不改**：`api.ts`、`tauri.ts`、连接器目录下任何文件。
- **不改后端**：登录能力由上游 kernel 提供，本产品无后端登录端点（`03 §2`：「G-05/06/07 无后端端点，纯前端 flags 短路」）；`campus.db` 的 19 张表中**无任何登录 / 账号 / 会话表**，无需 DDL 变更。
- **不动** 其余命中 `login/signin` 关键词的 14 个前端文件。

---

## 4. 涉及的代码模块清单

### 4.1 改动清单（3 个既有文件，均为最小追加）

| # | 文件 | 改动形式 | 行数估计 | 需求 |
|---|---|---|---|---|
| 1 | `surfaces/gui/src/flags.ts` | 末尾追加 `showLogin()` 1 个导出函数 | +4 | G-06 |
| 2 | `surfaces/gui/src/components/Sidebar.tsx` | 账户菜单三元追加 1 档；账户行三元追加 1 档；登出项条件加 `showLogin()` | +6 / -2 | G-06 |
| 3 | `surfaces/gui/src/components/Onboarding.tsx` | 登录带整块包 `{showLogin() && ...}`；footer 双态兜底调整 | +3 / -1 | G-06 |

**侵入点编号**：全部归属 `01 §6` 登记表 **#8**（`flags.ts` 追加 + 登录区短路），不新增侵入点，全仓侵入点总数仍为 9 处。

### 4.2 保留资产清单（明确不删）

| 类别 | 对象 |
|---|---|
| 组件 | `components/connectors/CloudSignIn.tsx`、`components/AccessSection.tsx`、`components/connectors/AccountsDetail.tsx` |
| API | `api.ts`：`cloudLogin` / `cloudLogout` / `waitForCloudSignIn` / `announceCloudChanged` |
| 测试 | `api.auth.test.ts`、`e2e/cloud.spec.ts`、`e2e/cloud-signin-placement.spec.ts`、`e2e/onboarding.spec.ts` |
| i18n | `locales/zh.json` / `en.json` 全部登录相关 key |
| 后端 | 无（本产品无登录后端端点）；`campus.db` 无登录相关表 / 字段 |

### 4.3 数据库层确认

`campus.db` 19 张表（`02 §6`）全部为备考域表（profile / plan / doc / question / grading / mistake / review 等），**不含任何登录、账号、会话、token 表或字段**。`users` / `sessions` 一类结构属上游 kernel 的 `state_dir` 域，本项目未引入。
**结论：数据库层零改动，无 DDL 迁移、无字段删除、无 `schema_meta` 版本变更。**

---

## 5. 潜在风险评估及应对措施

| # | 风险 | 概率 | 影响 | 应对措施 |
|---|---|---|---|---|
| R1 | **短路不全导致登录入口残留**（漏改账户行 / 登出项 / Onboarding footer） | 中 | 中 | 按 `04 §4.8` 逐子项核对；S2/S3 各自补双态断言（flag 关 → 无 `account-sign-in` / `ob-cloud-signin` testid）；grep 复核全部登录入口点 |
| R2 | **误判为物理删除导致资产不可逆损失** | 低 | **高** | 本档 §2.3 与 §4.2 明确「代码保留」；S4 用 `git diff --name-status` 断言仅 3 个 `M`、无 `D` |
| R3 | 改动 `Sidebar.tsx` / `Onboarding.tsx` 影响既有非登录功能 | 中 | 中 | 严格最小追加（三元加一档，不重构）；`tsc --noEmit` 类型门禁；`e2e/onboarding.spec.ts` 回归 |
| R4 | 违反「只做加法」铁律 / 侵入点扩散 | 中 | 中 | 改动收敛至 #8 白名单内 3 个文件；S4 以 `test_mount` 同款「无表外 diff」断言守门 |
| R5 | i18n key 集合不等导致 `locales.test.ts` 红 | 低 | 中 | 本次**不增不删**任何 i18n key，仅减少渲染点，key 集合不变 |
| R6 | Flag 机制失效（localStorage 不可用） | 低 | 低 | 既有 `flag()` 已 try/catch 兜底返回 fallback=false（安全侧）；沿用既有已验证机制 |
| R7 | 上游合并冲突（kosovo 上游更新登录实现） | 中 | 低 | 改动集中在 3 个文件末尾/局部，冲突面小；本任务分支独立、可随时 rebase |

---

## 6. 测试验证方案

### 6.1 分层测试矩阵

| 层 | 项 | 命令 | 期望 |
|---|---|---|---|
| 类型门禁 | TypeScript 编译 | `cd surfaces/gui && npx tsc --noEmit` | exit 0，无错误 |
| 单元 | flag 双态 | `cd surfaces/gui && npm test`（Vitest） | 全绿；新增 `ocw.flag.login` 双态用例通过 |
| 单元 | 既有前端用例回归 | 同上 | 无新增失败 |
| 集成 | 后端全量回归 | `python -m pytest tests -q` | 失败集合与纯基线树 **逐条相同** |
| 系统 | e2e 冒烟 | `npm run e2e`（如环境允许） | Onboarding / 账户区主路径通过 |

### 6.2 验收项（对齐 `08 §5` F-2 / F-3 的登录部分）

- **F-2 登录入口关闭（默认）**：Onboarding 无登录提示带（`:240-280` 跳过）；Sidebar 账户菜单无云端登录项（`:1174-1198`）；账户行无「未登录」字样（`:1255-1256`）；菜单无「登出」项。
- **F-3 可逆性验证**：`localStorage.setItem("ocw.flag.login","1")` → 登录入口**恢复渲染**；移除 key 后刷新 → 再次隐藏。
- **G-06 验收标准**（`07 §5 T20`）：`showLogin()` 关闭态下账户区仅剩本地状态；`git diff` 汇总 = 9 处侵入点，无扩散。

### 6.3 回归判据（严格）

后端全量回归**不用失败条数**作结论（本机沙箱会拦子进程，`FileNotFoundError [WinError 2]` 条数随会话漂移）。判据为**纯基线树对照**：

```bash
git worktree add --detach ../Stealth-Study-remove-login-base b1c5595
# 两棵树分别：python -m pytest tests -q --tb=line > /tmp/out.txt
# 取 FAILED/ERROR 行，去消息排序后 diff，要求 IDENTICAL
git worktree remove --force ../Stealth-Study-remove-login-base
```

---

## 7. 进度时间线

| 阶段 | 内容 | 里程碑 | 预估 |
|---|---|---|---|
| P0 · 审查 | 全量文档审查 + 本计划文档 | 计划文档提交推送 | 0.5 人日 |
| P1 · 审批 | 计划评审与批准 | 审批通过（§8 签字） | 0.5 人日 |
| P2 · S1 | `flags.ts` 追加 `showLogin()` + 推送 | 提交 1 就绪 | 0.2 人日 |
| P3 · S2 | `Sidebar.tsx` 账户区短路 + 推送 | 提交 2 就绪 | 0.4 人日 |
| P4 · S3 | `Onboarding.tsx` 登录带短路 + 推送 | 提交 3 就绪 | 0.4 人日 |
| P5 · S4 | 双态用例 + 全量回归对照 + 交付文档 + 推送 | 提交 4 就绪 | 1.0 人日 |
| **合计** | | | **3.0 人日** |

依赖关系：P1 → P2 → P3 → P4 → P5 严格串行（每步独立提交，便于单点回滚）；P3 与 P4 同属侵入点 #8，不可合并成笔。

---

## 8. 责任人分配

| 角色 | 责任人 | 职责 |
|---|---|---|
| 主责工程师 | 徐名可 | S1-S3 三处改动、提交与推送、双态用例编写 |
| 测试验证 | 徐名可（兼） | S4 全量回归对照、`tsc` 与 Vitest 门禁、e2e 冒烟 |
| 方案审批 | 项目主理人 | 本计划文档评审与批准（§9 审批栏） |
| 归档 | 徐名可 | `docs/dev/交付文档/T20-登录去除-交付文档.md` 收口 |

> 角色沿用 `docs/小组人员角色分工表.xlsx` 的既有分工；本任务为 T20 的子集，不新增角色。

---

## 9. 审批与执行记录

| 项 | 内容 |
|---|---|
| 审批状态 | 待审批 |
| 审批人 | — |
| 审批日期 | — |
| 审批意见 | — |

**执行前的强制前置条件**：本档经审批人确认后，方可进入 P2。未获批不得执行任何代码改动。
