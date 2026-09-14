"""Unit tests for `ss.campus.config` — self-read TOML nested tables (ADR-04 / INF-08)."""

from __future__ import annotations

from pathlib import Path

import pytest

from ss.campus import config as campus_config


def write_toml(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "config.toml"
    path.write_text(body, encoding="utf-8")
    return path


def test_missing_file_yields_defaults_without_warnings(tmp_path: Path) -> None:
    cfg = campus_config.load_campus_config(tmp_path / "absent.toml")
    assert cfg == campus_config.CampusConfig()
    assert cfg.daily_minutes == 60
    assert cfg.push_time == "20:00"
    assert cfg.grading_start_level == 0
    assert cfg.warnings == ()


def test_campus_table_is_read_in_full(tmp_path: Path) -> None:
    path = write_toml(
        tmp_path,
        """
[campus]
daily_minutes = 120
push_time = "07:30"
review_intensity = "intense"
default_profile_id = "abc123"
grading_start_level = 1

[campus.models]
grading = "deepseek:deepseek-v4-pro"
question = "zai:glm-5.2"
""",
    )
    cfg = campus_config.load_campus_config(path)
    assert cfg.daily_minutes == 120
    assert cfg.push_time == "07:30"
    assert cfg.review_intensity == "intense"
    assert cfg.default_profile_id == "abc123"
    assert cfg.grading_start_level == 1
    assert dict(cfg.task_models) == {
        "grading": "deepseek:deepseek-v4-pro",
        "question": "zai:glm-5.2",
    }
    assert cfg.warnings == ()


def test_unrelated_tables_are_ignored(tmp_path: Path) -> None:
    path = write_toml(
        tmp_path,
        """
model = "gpt-5.6-sol"
port = 8765

[other]
daily_minutes = 999
""",
    )
    cfg = campus_config.load_campus_config(path)
    assert cfg == campus_config.CampusConfig()
    assert cfg.daily_minutes == 60


def test_default_campus_preferences_path_is_the_global_config(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("COWORKER_STATE_DIR", str(tmp_path / "state"))
    state_config = tmp_path / "state" / "config.toml"
    state_config.parent.mkdir(parents=True, exist_ok=True)
    state_config.write_text("[campus]\ndaily_minutes = 45\n", encoding="utf-8")
    cfg = campus_config.load_campus_config()
    assert cfg.daily_minutes == 45


def test_unreadable_toml_falls_back_to_defaults_with_a_warning(tmp_path: Path) -> None:
    path = write_toml(tmp_path, "[campus]\ndaily_minutes = = 60\n")
    cfg = campus_config.load_campus_config(path)
    assert cfg.daily_minutes == 60
    assert any("toml" in warning for warning in cfg.warnings)


def test_non_table_campus_section_is_rejected_with_a_warning(tmp_path: Path) -> None:
    path = write_toml(tmp_path, "campus = 5\n")
    cfg = campus_config.load_campus_config(path)
    assert cfg.daily_minutes == 60
    assert cfg.push_time == "20:00"
    assert cfg.grading_start_level == 0
    assert dict(cfg.task_models) == {}
    assert any("campus" in warning for warning in cfg.warnings)


@pytest.mark.parametrize("raw", ["0", "1441", "-5", "abc", "60.5", "true", "[60]"])
def test_daily_minutes_outside_one_day_falls_back(tmp_path: Path, raw: str) -> None:
    path = write_toml(tmp_path, f"[campus]\ndaily_minutes = {raw}\n")
    cfg = campus_config.load_campus_config(path)
    assert cfg.daily_minutes == 60
    assert any("daily_minutes" in warning for warning in cfg.warnings)


@pytest.mark.parametrize("raw", ["1", "60", "1440"])
def test_daily_minutes_accepts_the_whole_valid_range(tmp_path: Path, raw: str) -> None:
    path = write_toml(tmp_path, f"[campus]\ndaily_minutes = {raw}\n")
    cfg = campus_config.load_campus_config(path)
    assert cfg.daily_minutes == int(raw)
    assert cfg.warnings == ()


@pytest.mark.parametrize("value", ["00:00", "09:05", "20:00", "23:59"])
def test_push_time_accepts_24h_clock_values(tmp_path: Path, value: str) -> None:
    path = write_toml(tmp_path, f'[campus]\npush_time = "{value}"\n')
    cfg = campus_config.load_campus_config(path)
    assert cfg.push_time == value
    assert cfg.warnings == ()


@pytest.mark.parametrize("value", ["24:00", "8:00", "20:60", "8pm", "", "20", "abc"])
def test_push_time_rejects_anything_off_the_clock(tmp_path: Path, value: str) -> None:
    path = write_toml(tmp_path, f'[campus]\npush_time = "{value}"\n')
    cfg = campus_config.load_campus_config(path)
    assert cfg.push_time == "20:00"
    assert any("push_time" in warning for warning in cfg.warnings)


def test_review_intensity_rejects_an_unknown_level(tmp_path: Path) -> None:
    path = write_toml(tmp_path, '[campus]\nreview_intensity = "extreme"\n')
    cfg = campus_config.load_campus_config(path)
    assert cfg.review_intensity == "standard"
    assert any("review_intensity" in warning for warning in cfg.warnings)


@pytest.mark.parametrize("raw", ["-1", "4", "1.5", "one"])
def test_grading_start_level_outside_zero_to_three_falls_back(tmp_path: Path, raw: str) -> None:
    path = write_toml(tmp_path, f"[campus]\ngrading_start_level = {raw}\n")
    cfg = campus_config.load_campus_config(path)
    assert cfg.grading_start_level == 0
    assert any("grading_start_level" in warning for warning in cfg.warnings)


def test_task_model_overrides_drop_unknown_tasks_and_bad_values(tmp_path: Path) -> None:
    path = write_toml(
        tmp_path,
        """
[campus.models]
grading = "deepseek:deepseek-v4-pro"
nope = "gpt-5.6-sol"
explain = ""
""",
    )
    cfg = campus_config.load_campus_config(path)
    assert dict(cfg.task_models) == {"grading": "deepseek:deepseek-v4-pro"}
    assert any("nope" in warning for warning in cfg.warnings)
    assert any("explain" in warning for warning in cfg.warnings)


def test_task_models_must_be_a_table(tmp_path: Path) -> None:
    path = write_toml(tmp_path, '[campus]\nmodels = "gpt-5.6-sol"\n')
    cfg = campus_config.load_campus_config(path)
    assert dict(cfg.task_models) == {}
    assert any("models" in warning for warning in cfg.warnings)


def test_blank_default_profile_id_is_treated_as_unset(tmp_path: Path) -> None:
    path = write_toml(tmp_path, '[campus]\ndefault_profile_id = "   "\n')
    cfg = campus_config.load_campus_config(path)
    assert cfg.default_profile_id is None
    assert any("default_profile_id" in warning for warning in cfg.warnings)


def test_resolve_task_model_prefers_the_configured_override(tmp_path: Path) -> None:
    cfg = campus_config.CampusConfig(task_models={"grading": "deepseek:deepseek-v4-pro"})
    assert cfg.resolve_task_model("grading") == "deepseek:deepseek-v4-pro"


def test_resolve_task_model_falls_back_to_the_static_recommendation() -> None:
    cfg = campus_config.CampusConfig()
    assert cfg.resolve_task_model("grading") == "anthropic:claude-opus-4-8"
    assert cfg.resolve_task_model("question") == "gpt-5.6-sol"


def test_resolve_task_model_rejects_an_unknown_task() -> None:
    with pytest.raises(KeyError):
        campus_config.CampusConfig().resolve_task_model("nope")


def test_config_only_borrows_the_config_path_helper() -> None:
    source = Path(campus_config.__file__).read_text(encoding="utf-8")
    imports = [
        line.strip()
        for line in source.splitlines()
        if line.startswith(("from ", "import "))
    ]
    assert "from ..config import global_config_path" in imports
    assert all("load_config" not in line for line in imports)
