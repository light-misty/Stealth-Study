"""T04 决策门证据一致性校验脚本。

交叉核对 T01/T03 机器证据与 T02 交付文档的量化结论，校验 v0.0-spike-report.md
的指标完整性。任一校验不通过时以非零码退出。

用法：
    python scripts/v0-spikes/verify_t04_gate.py
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = REPO_ROOT / "scripts" / "v0-spikes" / "results"
T02_DOC = REPO_ROOT / "docs" / "dev" / "交付文档" / "T02-交付文档.md"
T04_REPORT = REPO_ROOT / "docs" / "dev" / "v0.0-spike-report.md"

T03_EXPECTED_CHECKS = {
    "preflight_git_clean",
    "server_started",
    "campus_health_no_token_401",
    "campus_health_wrong_token_401",
    "campus_health_with_token_200",
    "existing_v1_sessions_200",
    "existing_v1_settings_200",
    "existing_v1_automations_200",
    "graceful_exit_no_traceback",
    "coworker_db_mtime_unchanged",
    "restore_git_diff_zero",
}

REPORT_REQUIRED_METRICS = [
    "L0 成功率",
    "98.75",
    "60%",
    "90%",
    "一致性",
    "response_format",
    "页级提取",
    "no_text_layer",
    "零切片",
    "L1 章节选择命中率",
    "80%",
    "top6",
    "70%",
    "标题抽取",
    "81.1",
    "可用率",
    "health 200",
    "mtime",
    "git diff",
]


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def verify_t01(results_dir: Path) -> list[str]:
    violations: list[str] = []
    summary_path = results_dir / "matrix_summary.json"
    consistency_path = results_dir / "consistency.jsonl"
    if not summary_path.is_file():
        return [f"T01 缺少证据文件: {summary_path.name}"]
    data = _read_json(summary_path)
    grid = data.get("grid", {})
    if data.get("total_cells") != 80:
        violations.append(f"T01 总格数 {data.get('total_cells')} != 80")
    if len(grid) != 4:
        violations.append(f"T01 矩阵列数 {len(grid)} != 4")
    l0_total = 0
    l0_l1_total = 0
    samples_total = 0
    for name, cell in grid.items():
        n = cell.get("samples", 0)
        if n < 20:
            violations.append(f"T01 格 {name} 样本数 {n} < 20")
        dist = cell.get("degrade_distribution", {})
        l0 = int(dist.get("0", 0))
        l1 = int(dist.get("1", 0))
        l0_total += l0
        l0_l1_total += l0 + l1
        samples_total += n
        if cell.get("fail_count", 0) != 0:
            violations.append(f"T01 格 {name} 存在 fail_count={cell.get('fail_count')}")
        if cell.get("l3_count", 0) != 0:
            violations.append(f"T01 格 {name} 存在 l3_count={cell.get('l3_count')}")
        if not cell.get("calls_budget_ok", False):
            violations.append(f"T01 格 {name} 调用预算超限")
        if cell.get("calls_max", 0) > 5:
            violations.append(f"T01 格 {name} 单格最大调用 {cell.get('calls_max')} > 5")
        if cell.get("calls_max", 0) > 5:
            violations.append(f"T01 格 {name} 单格最大调用 {cell.get('calls_max')} 次超过 5 次预算")
        if n:
            expected_rate = l0 / n
            if abs(cell.get("l0_success_rate", 0.0) - expected_rate) > 1e-9:
                violations.append(
                    f"T01 格 {name} l0_success_rate {cell.get('l0_success_rate')} 与分布不符（应为 {expected_rate:.4f}）"
                )
            if cell.get("l0_l1_success_rate", 0.0) + 1e-9 < (l0 + l1) / n:
                violations.append(f"T01 格 {name} l0_l1_success_rate 与分布不符")
        if name.endswith("|l0_response_format"):
            if cell.get("response_format_rejected", 0) != 0:
                violations.append(f"T01 格 {name} response_format 被拒 {cell.get('response_format_rejected')} 次")
            if cell.get("response_format_accepted") != n:
                violations.append(f"T01 格 {name} response_format 接受数 {cell.get('response_format_accepted')} != {n}")
    for name, pooled in data.get("pooled_by_model", {}).items():
        n = pooled.get("samples", 0)
        if n == 0:
            violations.append(f"T01 汇总 {name} 样本数为 0")
            continue
        l0_rate = pooled.get("l0_success_rate", 0.0)
        l0_l1_rate = pooled.get("l0_l1_success_rate", 0.0)
        if l0_rate < 0.60:
            violations.append(f"T01 汇总 {name} L0 成功率 {l0_rate:.4f} < 60% 门槛")
        if l0_l1_rate < 0.90:
            violations.append(f"T01 汇总 {name} L0+L1 成功率 {l0_l1_rate:.4f} < 90% 门槛")
    if samples_total:
        overall_l0 = l0_total / samples_total
        overall_l0_l1 = l0_l1_total / samples_total
        if overall_l0 < 0.60:
            violations.append(f"T01 整体 L0 成功率 {overall_l0:.4f} < 60% 门槛")
        if overall_l0_l1 < 0.90:
            violations.append(f"T01 整体 L0+L1 成功率 {overall_l0_l1:.4f} < 90% 门槛")
    else:
        violations.append("T01 矩阵样本总数为 0")
    if not consistency_path.is_file():
        violations.append(f"T01 缺少证据文件: {consistency_path.name}")
        return violations
    entries = []
    for line in consistency_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            entries.append(json.loads(line))
    if len(entries) < 10:
        violations.append(f"T01 一致性样本 {len(entries)} < 10")
    for i, entry in enumerate(entries):
        essay = entry.get("essay_id", f"#{i}")
        bands = entry.get("bands", [])
        if len(bands) != 2 or bands[0] != bands[1]:
            violations.append(f"T01 一致性样本 {essay} 档位不一致: {bands}")
        if entry.get("degrade_levels") != [0, 0]:
            violations.append(f"T01 一致性样本 {essay} 存在降级: {entry.get('degrade_levels')}")
        if entry.get("ok") != [True, True]:
            violations.append(f"T01 一致性样本 {essay} 存在失败: {entry.get('ok')}")
    return violations


def verify_t03(results_dir: Path) -> list[str]:
    violations: list[str] = []
    path = results_dir / "t03_mount_results.json"
    if not path.is_file():
        return [f"T03 缺少证据文件: {path.name}"]
    data = _read_json(path)
    if data.get("spike") != "T03-include-router-mount":
        violations.append(f"T03 spike 标识异常: {data.get('spike')}")
    if data.get("all_pass") is not True:
        violations.append("T03 all_pass 不为 true")
    checks = data.get("checks", {})
    missing = T03_EXPECTED_CHECKS - set(checks)
    extra = set(checks) - T03_EXPECTED_CHECKS
    for name in sorted(missing):
        violations.append(f"T03 缺少检查项: {name}")
    for name in sorted(extra):
        violations.append(f"T03 出现未登记检查项: {name}")
    for name, value in sorted(checks.items()):
        if value is not True:
            violations.append(f"T03 检查项 {name} 未通过")
    details = data.get("details", {})
    detail_expectations = {
        "campus_health_no_token_401": 401,
        "campus_health_wrong_token_401": 401,
        "campus_health_with_token_200": 200,
        "existing_v1_sessions_200": 200,
        "existing_v1_settings_200": 200,
        "existing_v1_automations_200": 200,
    }
    for name, expected in detail_expectations.items():
        if details.get(name) != expected:
            violations.append(f"T03 详情 {name}={details.get(name)} 期望 {expected}")
    mtime_detail = str(details.get("coworker_db_mtime_unchanged", ""))
    m = re.match(r"before=([0-9.]+) after=([0-9.]+)$", mtime_detail)
    if not m:
        violations.append(f"T03 mtime 详情格式异常: {mtime_detail!r}")
    elif m.group(1) != m.group(2):
        violations.append("T03 coworker.db mtime 发生变化")
    if "returncode=0" not in str(details.get("graceful_exit_no_traceback", "")):
        violations.append("T03 退出码非 0")
    return violations


def _section(text: str, start_marker: str, end_marker: str) -> str:
    start = text.find(start_marker)
    if start < 0:
        return ""
    end = text.find(end_marker, start)
    return text[start:end] if end > start else text[start:]


def verify_t02(doc_path: Path) -> list[str]:
    violations: list[str] = []
    if not doc_path.is_file():
        return [f"T02 缺少交付文档: {doc_path}"]
    text = doc_path.read_text(encoding="utf-8")
    if "no_text_layer" not in text:
        violations.append("T02 文档缺少扫描件 no_text_layer 结论")
    if "零切片" not in text:
        violations.append("T02 文档缺少扫描件零切片结论")
    section = _section(text, "## 5.", "## 6.")
    if not section:
        return violations + ["T02 文档缺少验收标准逐条比对章节"]
    rows = []
    for line in section.splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 5 and cells[0] in {"①", "②", "③", "④"}:
            rows.append(cells)
    if len(rows) < 5:
        violations.append(f"T02 验收表行数 {len(rows)} < 5")
    for cells in rows:
        row_id = cells[0]
        verdict = cells[-1]
        if "达标" not in verdict or "未达标" in verdict:
            violations.append(f"T02 验收行 {row_id}（{cells[1][:16]}）判定非达标: {verdict}")
            continue
        threshold_match = re.search(r"≥\s*(\d+(?:\.\d+)?)\s*%", cells[2])
        if not threshold_match:
            continue
        threshold = float(threshold_match.group(1))
        measured = _extract_measured(cells[3])
        if measured is None:
            violations.append(f"T02 验收行 {row_id} 实测值无法解析: {cells[3]}")
        elif measured < threshold:
            violations.append(
                f"T02 验收行 {row_id} 实测 {measured}% 低于门槛 {threshold}%: {cells[3]}"
            )
    return violations


def _extract_measured(measured_cell: str) -> float | None:
    pcts = [float(x) for x in re.findall(r"(\d+(?:\.\d+)?)\s*%", measured_cell)]
    if pcts:
        return min(pcts)
    decimals = [float(x) for x in re.findall(r"\d+\.\d+", measured_cell) if float(x) <= 1.0001]
    if decimals:
        return min(decimals) * 100
    return None


def verify_report(report_path: Path) -> list[str]:
    violations: list[str] = []
    if not report_path.is_file():
        return [f"缺少决策门报告: {report_path}"]
    text = report_path.read_text(encoding="utf-8")
    for marker in ("T01", "T02", "T03"):
        if marker not in text:
            violations.append(f"报告缺少 {marker} 量化结论")
    for metric in REPORT_REQUIRED_METRICS:
        if metric not in text:
            violations.append(f"报告缺少量化指标或结论要素: {metric}")
    if "GRADING_START_LEVEL" not in text:
        violations.append("报告缺少决策一（GRADING_START_LEVEL 取值）")
    if "分流" not in text:
        violations.append("报告缺少决策二（无书签 PDF 的 L1/L2 分流确认）")
    if "OCR" not in text or "V0.2" not in text:
        violations.append("报告缺少决策三（OCR 是否立项 V0.2）")
    if "缩减" not in text:
        violations.append("报告缺少 V0.1 范围缩减建议的落字判定")
    return violations


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="T04 决策门证据一致性校验")
    parser.add_argument("--results-dir", type=Path, default=RESULTS_DIR)
    parser.add_argument("--t02-doc", type=Path, default=T02_DOC)
    parser.add_argument("--report", type=Path, default=T04_REPORT)
    parser.add_argument("--skip-report", action="store_true", help="报告未落盘时跳过报告校验")
    args = parser.parse_args(argv)
    violations: list[str] = []
    violations += verify_t01(args.results_dir)
    violations += verify_t03(args.results_dir)
    violations += verify_t02(args.t02_doc)
    if args.skip_report and not args.report.is_file():
        print("report: SKIPPED (未落盘)")
    else:
        violations += verify_report(args.report)
    if violations:
        print(f"FAIL: {len(violations)} 项不一致")
        for v in violations:
            print(f"  - {v}")
        return 1
    print("PASS: T01/T02/T03 证据一致，决策门报告指标完整")
    return 0


if __name__ == "__main__":
    sys.exit(main())
