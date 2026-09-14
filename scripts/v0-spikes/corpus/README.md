# T01 SPIKE-1 语料说明（四六级作文批改 JSON 成功率）

本目录是 T01 spike 的固定输入，由 `scripts/v0-spikes/fetch_corpus.py` 从公开语料库抓取并归一化生成。

## 1. 产物

| 文件 | 说明 |
|---|---|
| `cet_essays.json` | 20 篇批改样本（10 篇 paired 带同话题参考范文对照 + 10 篇 solo） |
| `corpus_manifest.json` | 来源 URL、上游文件 sha256、分组统计、归一化策略、修复记录 |
| `.cache/` | 上游 PDF 原始缓存（不入库，见 `.gitignore`） |

## 2. 来源与许可

- 来源仓库：[ZhaoyuanLiu23/CET-Prompt-Hub](https://github.com/ZhaoyuanLiu23/CET-Prompt-Hub)（**MIT**）
- 具体文件：`essays/{topic}_{level}.pdf`，`topic ∈ {adversity, collaboration, courage, innovation, perseverance}`，`level ∈ {cet4, cet6}`
- 每份 PDF 含同话题 3 篇范文，共 5 × 2 × 3 = 30 篇
- MIT 许可允许再分发，版权与许可声明见 `corpus_manifest.json` 的 `source` 字段

## 3. 20 篇的选取规则

每个 `{topic}-{level}` 分组（共 10 组）取 2 篇：

| 角色 | 取第几篇 | 是否带对照范文 |
|---|---|---|
| `paired`（10 篇） | 第 1 篇 | 是，`reference` = 同组第 3 篇（同话题另一篇范文） |
| `solo`（10 篇） | 第 2 篇 | 否，`reference = null` |

因此「20 篇中 10 篇带参考范文对照」由 `paired` 组承载，对照关系是**同话题不同范文**，用于人工横向比对。

## 4. 归一化规则

1. 按 `第N篇：` 切分段落；CET-6 类 PDF 取 `英文全文` 与 `整体中文翻译` 之间的正文，CET-4 类 PDF 取标题行后至 `(总词数：N)` 之前的正文。
2. 剥离行内中文注释括号、Markdown 粗体标记、全角引号；折叠多余空白。
3. 行接续：行尾为连字符时直接拼接，否则以空格连接。
4. `prompt` 字段取上游话题声明原文（`话题：<topic>（<topic>-<level>）`），**不是官方考试 Directions**。

## 5. PDF 文字层断词修复（显式表，可审计）

上游 PDF 文字层存在 6 处「单词被空格劈开」的伪影。`fetch_corpus.py` 的 `ARTIFACT_REPAIRS` 以**上下文锚定**的方式逐条修复，并断言每条必须命中至少一次（不命中即报错，防止修复表随语料漂移而静默失效）：

| # | 修复前 | 修复后 | 所在样本 |
|---|---|---|---|
| 1 | `outcomes b ased on` | `outcomes based on` | E04 |
| 2 | `hardships a nd providing` | `hardships and providing` | E04 |
| 3 | `agreement o n every` | `agreement on every` | E08 |
| 4 | `costs for co llective benefit` | `costs for collective benefit` | E11 |
| 5 | `courage is paralyze d.` | `courage is paralyzed.` | E12 |
| 6 | `his bagless vacuum cleane r.` | `his bagless vacuum cleaner.` | E15 的对照范文 |

不使用启发式合并（如「短片段 + 长片段即拼接」）——启发式会误改正常短语，静默损坏语料的代价高于保留一处空格。

## 6. 完整性校验（`verify_corpus`，不通过即构建失败）

- 无 CJK 残留、无连续空格、以句末标点结束
- 无 `b-h/j-z` 单字母碎片（覆盖上述 4 处单字母类伪影）
- 词数落在 90–260、句子数 ≥ 5
- `paired` 必有 `reference`，`solo` 必无

## 7. 已知限制（T01 报告同步登记）

1. **词数分布 101–148**：低于 CET-6 150–200 词要求，部分 CET-4 样本低于 120 词。属上游语料特征，未做人工补写（补写即引入非公开来源数据）。
2. **无人工档位标注**：20 篇均为高分范文，无人工 15 分制档位，故 08 §3.1 的「人工评分相关性 Kendall tau」**无法计算**，报告中登记为不可用并给出后续动作。
3. **全部为高分范文**：T01 主指标是 JSON 合规率，与文本质量无关，故不影响 §3.1 门槛判定；但档位分布的代表性受限，不应用于推断真实考生分布。
4. **上游标称词数与朴素词数口径不同**（如标称 171 实测 148），以 `extracted_word_count` 为准。

## 8. 复现

```bash
python scripts/v0-spikes/fetch_corpus.py
```

脚本幂等：`.cache/` 命中即复用，输出 JSON 与 `corpus_manifest.json` 的 sha256 一一对应。
