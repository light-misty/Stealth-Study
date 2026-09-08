# 项目长期记忆

## 项目性质

HIU-WorkSpace（龙外工作台）是一个**正常的产品研发项目**（非课程作业），基于开源项目 OpenWorker（MIT，上游 `light-misty/HIU-WorkSpace`）二次开发。
**不代表黑龙江外国语学院官方立场**，无校内对接人，校内无 AI 使用管理办法。
**团队开发，使用 AI Coding Agent 工具快速开发。**

## 重要：不要引入作业语境

用户明确要求：**不要把它当作业看**。禁止在文档与讨论中出现"作业、课程、评分标准、截止日期、答辩、单人开发、每周工时、人日档位"等表述与推演。
例外（术语消歧已说明）：`coworker/agents/code.py` 的"solo 编码代理"（技术术语）、四六级/专四专八的"评分标准"（考试领域术语）。

## 已由用户拍板、不得推翻的前提

1. 首发形态：桌面端为主，沿用 Tauri + 本地 Python 服务，本地优先。
2. 不对接校方系统（教务/学工/一卡通/图书馆/统一身份认证），数据一律文件手动导入。
3. 模型资源：学生自带 API Key（严格 BYOK），沿用现有多提供商接入，学生自付费用。
4. 面向用户：**只有学生**这一单一角色，无教师端、无管理端。
5. 试点用户为任何普通学生，不限定院系种子名单。
6. 团队开发 + AI Coding Agent 辅助；排期用迭代（I1-I7）与相对规模 XS/S/M/L，不用绝对人日与工时档位。

## 仓库关键事实（已核实，易踩坑）

- `coworker/personas/builtin/` 下 16 个内置人设中 **13 个标了 `ships: false`**，默认不随发布版分发，需 `OPENWORKER_UNSHIPPED=1`。默认只分发 security / cloud-posture / dep-audit（均为安全向），与校园场景无关。
- 上述人设多为 `team: worker` 类型，系统提示要求「对 LEAD 说话、绝不使用 ask_user」，**不能用于学生单机会话**。
- 计算机类场景真正可复用的主资产是 `coworker/agents/code.py`（完整 solo 编码代理，含 code_files/git/search/shell/todo 能力，系统提示含探索优先、最小改动、改完必跑测试、不主动 commit、不记录密钥）。
- 代码库理解可复用 `coworker/tools/subagent.py` 的 `explore`（只读研究子 Agent，独立上下文）。
- `coworker/providers/registry.py` 已实现 deepseek / kimi / qwen / zai(GLM) / minimax / xai / mistral / ollama / ark 等，BYOK 无需新增适配。
- `stt/src/lib.rs` 默认模型 `ggml-base.en.bin` 为**英语专用**，多语种需换模型（口语陪练的前置改造项）。
- `coworker/personas/manifest.py` 的 `VALID_GROUPS` 仅 `{"general","security"}`；校园人设建议不改上游枚举，用 `hiu-student-*` / `hiu-teacher-*` 等 id 前缀区分，避免上游同步冲突。

## 主要交付物

- `docs/PRD-龙外工作台.md` —— 完整版 PRD，当前 **v2.0**（1571 行 / 11 张 Mermaid 图）。

## 文档写作约定

- 简体中文，**禁止 emoji**（AGENTS.md 明令）。
- 数据诚实：不编造校方数据，未核实的标注「（假设，待确认）」或列入待确认清单。
