"""T04 决策门证据一致性校验。

交叉核对 T01/T03 的机器证据（results/*.json|jsonl）与 T02 交付文档中的量化结论，
并校验 v0.0-spike-report.md 的指标完整性。量化口径见 08 文档 §3.1-§3.3。
"""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPIKE_DIR = ROOT / "scripts" / "v0-spikes"
RESULTS_DIR = SPIKE_DIR / "results"
T02_DOC = ROOT / "docs" / "dev" / "交付文档" / "T02-交付文档.md"
T04_REPORT = ROOT / "docs" / "dev" / "v0.0-spike-report.md"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


gate = _load("verify_t04_gate", SPIKE_DIR / "verify_t04_gate.py")


def _write(tmp_path: Path, name: str, obj) -> Path:
    p = tmp_path / name
    p.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
    return p


class TestT01Evidence:
    def test_real_matrix_summary_passes(self):
        assert gate.verify_t01(RESULTS_DIR) == []

    def test_grid_shape_and_thresholds(self):
        data = json.loads((RESULTS_DIR / "matrix_summary.json").read_text(encoding="utf-8"))
        assert data["total_cells"] == 80
        assert len(data["grid"]) == 4
        assert all(cell["samples"] >= 20 for cell in data["grid"].values())

    def test_fail_count_violation(self, tmp_path):
        data = json.loads((RESULTS_DIR / "matrix_summary.json").read_text(encoding="utf-8"))
        data["grid"]["mimo-v2.5|l0_plain"]["fail_count"] = 1
        p = _write(tmp_path, "matrix_summary.json", data)
        violations = gate.verify_t01(tmp_path)
        assert p.exists()
        assert any("fail_count" in v for v in violations)

    def test_l0_threshold_violation(self, tmp_path):
        data = json.loads((RESULTS_DIR / "matrix_summary.json").read_text(encoding="utf-8"))
        cell = data["grid"]["mimo-v2.5|l0_plain"]
        cell["degrade_distribution"]["0"] = 5
        cell["degrade_distribution"]["3"] = 15
        cell["l0_success_rate"] = 0.25
        cell["l0_l1_success_rate"] = 0.25
        _write(tmp_path, "matrix_summary.json", data)
        violations = gate.verify_t01(tmp_path)
        assert any("60%" in v or "90%" in v for v in violations)

    def test_budget_violation(self, tmp_path):
        data = json.loads((RESULTS_DIR / "matrix_summary.json").read_text(encoding="utf-8"))
        data["grid"]["mimo-v2.5-pro|l0_response_format"]["calls_max"] = 6
        _write(tmp_path, "matrix_summary.json", data)
        assert any("预算" in v or "calls" in v for v in gate.verify_t01(tmp_path))

    def test_missing_grid_cell(self, tmp_path):
        data = json.loads((RESULTS_DIR / "matrix_summary.json").read_text(encoding="utf-8"))
        data["grid"].pop("mimo-v2.5|l0_plain")
        _write(tmp_path, "matrix_summary.json", data)
        assert gate.verify_t01(tmp_path) != []

    def test_consistency_real_data_passes(self):
        assert gate.verify_t01(RESULTS_DIR) == []

    def test_consistency_band_mismatch(self, tmp_path):
        (tmp_path / "matrix_summary.json").write_text(
            (RESULTS_DIR / "matrix_summary.json").read_text(encoding="utf-8"), encoding="utf-8"
        )
        lines = (RESULTS_DIR / "consistency.jsonl").read_text(encoding="utf-8").splitlines()
        entry = json.loads(lines[0])
        entry["bands"] = [14, 11]
        lines[0] = json.dumps(entry, ensure_ascii=False)
        (tmp_path / "consistency.jsonl").write_text("\n".join(lines), encoding="utf-8")
        assert any("一致性" in v for v in gate.verify_t01(tmp_path))

    def test_consistency_degraded_entry(self, tmp_path):
        (tmp_path / "matrix_summary.json").write_text(
            (RESULTS_DIR / "matrix_summary.json").read_text(encoding="utf-8"), encoding="utf-8"
        )
        lines = (RESULTS_DIR / "consistency.jsonl").read_text(encoding="utf-8").splitlines()
        entry = json.loads(lines[0])
        entry["degrade_levels"] = [0, 2]
        lines[0] = json.dumps(entry, ensure_ascii=False)
        (tmp_path / "consistency.jsonl").write_text("\n".join(lines), encoding="utf-8")
        assert any("一致性" in v for v in gate.verify_t01(tmp_path))

    def test_missing_file(self, tmp_path):
        assert gate.verify_t01(tmp_path) != []


class TestT03Evidence:
    def test_real_mount_results_pass(self):
        assert gate.verify_t03(RESULTS_DIR) == []

    def test_all_pass_false(self, tmp_path):
        data = json.loads((RESULTS_DIR / "t03_mount_results.json").read_text(encoding="utf-8"))
        data["all_pass"] = False
        _write(tmp_path, "t03_mount_results.json", data)
        assert any("all_pass" in v for v in gate.verify_t03(tmp_path))

    def test_missing_check(self, tmp_path):
        data = json.loads((RESULTS_DIR / "t03_mount_results.json").read_text(encoding="utf-8"))
        data["checks"].pop("restore_git_diff_zero")
        _write(tmp_path, "t03_mount_results.json", data)
        assert any("restore_git_diff_zero" in v for v in gate.verify_t03(tmp_path))

    def test_flipped_check(self, tmp_path):
        data = json.loads((RESULTS_DIR / "t03_mount_results.json").read_text(encoding="utf-8"))
        data["checks"]["campus_health_with_token_200"] = False
        data["details"]["campus_health_with_token_200"] = 500
        _write(tmp_path, "t03_mount_results.json", data)
        violations = gate.verify_t03(tmp_path)
        assert any("campus_health_with_token_200" in v for v in violations)

    def test_mtime_changed(self, tmp_path):
        data = json.loads((RESULTS_DIR / "t03_mount_results.json").read_text(encoding="utf-8"))
        data["details"]["coworker_db_mtime_unchanged"] = "before=1 after=2"
        _write(tmp_path, "t03_mount_results.json", data)
        assert any("mtime" in v for v in gate.verify_t03(tmp_path))

    def test_wrong_spike_id(self, tmp_path):
        data = json.loads((RESULTS_DIR / "t03_mount_results.json").read_text(encoding="utf-8"))
        data["spike"] = "T99"
        _write(tmp_path, "t03_mount_results.json", data)
        assert gate.verify_t03(tmp_path) != []


class TestT02Doc:
    def test_real_doc_passes(self):
        assert gate.verify_t02(T02_DOC) == []

    def test_verdict_flipped(self, tmp_path):
        text = T02_DOC.read_text(encoding="utf-8")
        text = text.replace("| ③ | 无书签文档标题抽取成功率 | ≥60% | **81.1%**（spec）/ 100%（relaxed） | **达标**（分布不均衡，见 §7-1） |",
                            "| ③ | 无书签文档标题抽取成功率 | ≥60% | **50.0%**（spec）/ 100%（relaxed） | **未达标** |")
        p = tmp_path / "T02-交付文档.md"
        p.write_text(text, encoding="utf-8")
        violations = gate.verify_t02(p)
        assert any("未达标" in v for v in violations)
        assert any("③" in v for v in violations)

    def test_measured_below_threshold(self, tmp_path):
        text = T02_DOC.read_text(encoding="utf-8")
        text = text.replace("≥80% | **90%**", "≥80% | **75%**")
        p = tmp_path / "T02-交付文档.md"
        p.write_text(text, encoding="utf-8")
        assert gate.verify_t02(p) != []

    def test_missing_scan_conclusion(self, tmp_path):
        text = T02_DOC.read_text(encoding="utf-8")
        text = text.replace("no_text_layer", "n o _ t e x t")
        p = tmp_path / "T02-交付文档.md"
        p.write_text(text, encoding="utf-8")
        assert any("no_text_layer" in v for v in gate.verify_t02(p))

    def test_missing_doc(self, tmp_path):
        assert gate.verify_t02(tmp_path / "nope.md") != []


MINIMAL_REPORT = """# V0.0 Spike 决策门报告

## 1. T01 量化结论

L0 成功率 98.75%，L0+L1 98.75%，一致性 10/10，response_format 无增益。

## 2. T02 量化结论

页级提取成功率 99.6%，扫描件 no_text_layer 零切片；L1 章节选择命中率 90%（≥80%），
top6 召回包含率 85%（≥70%）；无书签文档标题抽取成功率 81.1%（≥60%）；20 问答案可用率 80%（≥70%）。

## 3. T03 量化结论

health 200，鉴权链路通过，mtime 不变，还原后 git diff 为零。

## 4. 决策

决策一：GRADING_START_LEVEL 保持默认 0。
决策二：无书签 PDF 的 L1/L2 分流——书签优先、文本行兜底，抽取失败自然分流 L2。
决策三：OCR V0.1 不立项，是否进 V0.2 由扫描件占比再议。

## 5. 缩减建议

三项决策均为达标，V0.1 范围缩减不触发。
"""


class TestT04Report:
    def test_minimal_report_passes(self, tmp_path):
        p = tmp_path / "v0.0-spike-report.md"
        p.write_text(MINIMAL_REPORT, encoding="utf-8")
        assert gate.verify_report(p) == []

    def test_missing_report(self, tmp_path):
        assert gate.verify_report(tmp_path / "nope.md") != []

    def test_missing_decision(self, tmp_path):
        text = MINIMAL_REPORT.replace("决策三：OCR V0.1 不立项，是否进 V0.2 由扫描件占比再议。\n", "")
        p = tmp_path / "v0.0-spike-report.md"
        p.write_text(text, encoding="utf-8")
        violations = gate.verify_report(p)
        assert any("OCR" in v for v in violations)

    def test_missing_shrink_verdict(self, tmp_path):
        text = MINIMAL_REPORT.replace("## 5. 缩减建议\n\n三项决策均为达标，V0.1 范围缩减不触发。\n", "")
        p = tmp_path / "v0.0-spike-report.md"
        p.write_text(text, encoding="utf-8")
        assert any("缩减" in v for v in gate.verify_report(p))

    def test_missing_grading_start_level(self, tmp_path):
        text = MINIMAL_REPORT.replace("GRADING_START_LEVEL 保持默认 0", "起点常量维持默认值")
        p = tmp_path / "v0.0-spike-report.md"
        p.write_text(text, encoding="utf-8")
        assert any("GRADING_START_LEVEL" in v for v in gate.verify_report(p))

    def test_missing_metric(self, tmp_path):
        text = MINIMAL_REPORT.replace("top6 召回包含率 85%（≥70%）；", "")
        p = tmp_path / "v0.0-spike-report.md"
        p.write_text(text, encoding="utf-8")
        assert any("top6" in v for v in gate.verify_report(p))

    @pytest.mark.skipif(not T04_REPORT.exists(), reason="报告在后续提交落盘")
    def test_real_report_passes(self):
        assert gate.verify_report(T04_REPORT) == []
