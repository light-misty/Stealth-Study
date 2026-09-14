"""campus preference reading — the `[campus]` table of the global `config.toml`.

ADR-04 explains why this file exists instead of an entry in `ss/config.py`: `load_config()`
only knows 18 flat top-level keys, so a `[campus]` section written there would be silently
ignored. This module therefore parses the same file itself through
`ss.config.global_config_path()` and touches nothing in `ss/config.py`.

The runtime values live in `campus.db`'s `app_state` table (02 §4.2: "运行时以 app_state 为准");
what is read here is the on-disk default that a fresh install starts from.

Every rejected value is recorded in `CampusConfig.warnings` rather than raising, so a typo in
a user's config cannot stop the application from starting — but it is never silent either.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Optional

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib  # type: ignore[no-redef]

from ..config import global_config_path
from .models import CampusTask, ReviewIntensity, pick_for_task

DEFAULT_DAILY_MINUTES = 60
DEFAULT_PUSH_TIME = "20:00"
DEFAULT_REVIEW_INTENSITY = ReviewIntensity.STANDARD.value
DEFAULT_GRADING_START_LEVEL = 0
DEFAULT_LOGIN_ENABLED = False
MIN_DAILY_MINUTES = 1
MAX_DAILY_MINUTES = 1440
MAX_GRADING_START_LEVEL = 3

_PUSH_TIME = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


@dataclass
class CampusConfig:
    """Resolved campus preferences.

    `task_models` maps a `CampusTask` value to a user-chosen model id; an absent task means
    "use the static recommendation" (ADR-06).
    """

    daily_minutes: int = DEFAULT_DAILY_MINUTES
    push_time: str = DEFAULT_PUSH_TIME
    review_intensity: str = DEFAULT_REVIEW_INTENSITY
    default_profile_id: Optional[str] = None
    grading_start_level: int = DEFAULT_GRADING_START_LEVEL
    login_enabled: bool = DEFAULT_LOGIN_ENABLED
    task_models: Mapping[str, str] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()

    def resolve_task_model(self, task: str) -> str:
        """The model id for `task`: the user's override, else the static recommendation.

        Raises `KeyError` when `task` is not one of `CampusTask`.
        """
        override = self.task_models.get(task)
        if override:
            return override
        return pick_for_task(task)[0]


def _read_toml(path: Path) -> tuple[dict[str, Any], list[str]]:
    if not path.is_file():
        return {}, []
    try:
        with open(path, "rb") as handle:
            data = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        return {}, [f"cannot parse {path} as toml: {exc}"]
    if not isinstance(data, dict):
        return {}, [f"cannot parse {path} as toml: top level is not a table"]
    return data, []


def _read_table(section: Any, name: str, warnings: list[str]) -> dict[str, Any]:
    if section is None:
        return {}
    if not isinstance(section, dict):
        warnings.append(f"campus.{name}: expected a table, got {type(section).__name__}")
        return {}
    return section


def _daily_minutes(value: Any, warnings: list[str]) -> int:
    if not _is_int(value) or not MIN_DAILY_MINUTES <= value <= MAX_DAILY_MINUTES:
        warnings.append(
            f"campus.daily_minutes: expected an integer in "
            f"[{MIN_DAILY_MINUTES}, {MAX_DAILY_MINUTES}], got {value!r}"
        )
        return DEFAULT_DAILY_MINUTES
    return value


def _push_time(value: Any, warnings: list[str]) -> str:
    if not isinstance(value, str) or not _PUSH_TIME.match(value):
        warnings.append(f"campus.push_time: expected 24h HH:MM, got {value!r}")
        return DEFAULT_PUSH_TIME
    return value


def _review_intensity(value: Any, warnings: list[str]) -> str:
    if not isinstance(value, str) or value not in {level.value for level in ReviewIntensity}:
        warnings.append(
            f"campus.review_intensity: expected one of "
            f"{sorted(level.value for level in ReviewIntensity)}, got {value!r}"
        )
        return DEFAULT_REVIEW_INTENSITY
    return value


def _grading_start_level(value: Any, warnings: list[str]) -> int:
    if not _is_int(value) or not 0 <= value <= MAX_GRADING_START_LEVEL:
        warnings.append(
            f"campus.grading_start_level: expected an integer in "
            f"[0, {MAX_GRADING_START_LEVEL}], got {value!r}"
        )
        return DEFAULT_GRADING_START_LEVEL
    return value


def _default_profile_id(value: Any, warnings: list[str]) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        warnings.append(
            f"campus.default_profile_id: expected a non-empty string, got {value!r}"
        )
        return None
    return value.strip()


def _login_enabled(value: Any, warnings: list[str]) -> bool:
    """G-06: cloud sign-in is off by default; this is the single server-side escape hatch.

    Only a real TOML boolean turns it back on — strings avoid the `"false"`-is-truthy trap.
    """
    if not isinstance(value, bool):
        warnings.append(f"campus.login_enabled: expected a boolean, got {value!r}")
        return DEFAULT_LOGIN_ENABLED
    return value


def _task_models(value: Any, warnings: list[str]) -> dict[str, str]:
    table = _read_table(value, "models", warnings)
    tasks = {task.value for task in CampusTask}
    resolved: dict[str, str] = {}
    for name, model in table.items():
        if name not in tasks:
            warnings.append(f"campus.models.{name}: unknown task, expected one of {sorted(tasks)}")
            continue
        if not isinstance(model, str) or not model.strip():
            warnings.append(f"campus.models.{name}: expected a non-empty string, got {model!r}")
            continue
        resolved[name] = model.strip()
    return resolved


def _pick(table: dict[str, Any], key: str, validator, default: Any, warnings: list[str]) -> Any:
    """Validate `table[key]` when the key is present; keep `default` when it is absent.

    A missing key is not a mistake — only a value that is present and out of range is
    reported.
    """
    if key not in table:
        return default
    return validator(table[key], warnings)


def load_campus_config(path: Optional[Path] = None) -> CampusConfig:
    """Read `[campus]` (and its nested `[campus.models]`) from a TOML file.

    Defaults to the global `config.toml`. Anything unreadable or out of range is replaced
    by its default and reported through `CampusConfig.warnings`.
    """
    target = Path(path) if path is not None else global_config_path()
    data, warnings = _read_toml(target)
    campus = _read_table(data.get("campus"), "campus", warnings)
    return CampusConfig(
        daily_minutes=_pick(
            campus, "daily_minutes", _daily_minutes, DEFAULT_DAILY_MINUTES, warnings
        ),
        push_time=_pick(campus, "push_time", _push_time, DEFAULT_PUSH_TIME, warnings),
        review_intensity=_pick(
            campus, "review_intensity", _review_intensity, DEFAULT_REVIEW_INTENSITY, warnings
        ),
        default_profile_id=_pick(
            campus, "default_profile_id", _default_profile_id, None, warnings
        ),
        grading_start_level=_pick(
            campus,
            "grading_start_level",
            _grading_start_level,
            DEFAULT_GRADING_START_LEVEL,
            warnings,
        ),
        login_enabled=_pick(
            campus, "login_enabled", _login_enabled, DEFAULT_LOGIN_ENABLED, warnings
        ),
        task_models=_pick(campus, "models", _task_models, {}, warnings),
        warnings=tuple(warnings),
    )
