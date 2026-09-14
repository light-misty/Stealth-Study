# T01 SPIKE-1 运行证据

由 `scripts/v0-spikes/spike_grading.py` 产出，全部为真实模型调用的原始记录，供 QA 复核分布表。

| 文件 | 内容 |
|---|---|
| `matrix.jsonl` | 主矩阵 80 格逐格记录：`degrade_level`、`band`、`schema_flags`、`degrade_trace`、`calls`、`transport_retries`、`elapsed_s`、各级原始输出（截断 4000 字符） |
| `matrix_summary.json` | 按 `{模型}×{条件}` 的降级分布、L0/L0+L1 成功率、调用预算校验、band 直方图、response_format 接受情况 |
| `consistency.jsonl` | 一致性复跑：10 篇 paired 样本 × 2 次批改的档位对比 |

## 实验配置

- 模型：`mimo-v2.5-pro`（推荐强模型）、`mimo-v2.5`（便宜模型对照），endpoint `https://api.xiaomimimo.com/v1`
- 条件：`l0_plain`（L0 裸 prompt）、`l0_response_format`（L0 + `response_format={"type":"json_object"}`）
- 样本：`corpus/cet_essays.json` 的 20 篇（10 paired + 10 solo），每格 20 样本
- 参数：`temperature=0`、单轮 `timeout=90s`、单次批改调用上限 5

## 复现

```bash
python scripts/v0-spikes/fetch_corpus.py
python scripts/v0-spikes/spike_grading.py run --concurrency 8
python scripts/v0-spikes/spike_grading.py report
python scripts/v0-spikes/spike_grading.py consistency --model mimo-v2.5-pro
```

`run` 支持 `--resume` 断点续跑（按 `essay_id|model|condition` 去重）；重跑前请先清空 `matrix.jsonl`，否则新记录会追加在旧记录之后。
