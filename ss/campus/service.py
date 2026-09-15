"""campus orchestration layer — the business rules behind the campus endpoints.

`routes.py` owns HTTP (status codes, request shapes, the structured error body); this module
owns the decisions. It therefore never imports FastAPI: a failure leaves here as `CampusError`
carrying one of the codes of 03 §6, and the router is the only place that turns a code into a
response (T06 §7-2).

Three rules from 01 §2.1/§3 are structural here:

* Every profile-scoped read and write passes `profile_id` to the store, which is the
  data-layer half of the multi-profile isolation promise ("service 层所有查询强制
  `WHERE profile_id=?`"; the router half is `ProfileGuard`, T06).
* No method branches on a track id. Station differences are read from `tracks.py`
  (`TrackSpec`), never from a literal comparison (01 §3.2 forbids `if track == "cet"`).
* A `finished` profile refuses every write (02 §7.2). The router decorates every mutating
  endpoint with the guard's `get_writable_profile` (T06 §7-1), so this layer is only ever
  reached for a writable profile and never re-implements that rule.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping, Optional

from ..secrets import state_dir
from . import models
from .config import DEFAULT_DAILY_MINUTES
from .store import CampusStore

ACTIVE_PROFILE_KEY = "active_profile_id"
SETTINGS_KEY = "campus_settings"

CASCADE_TABLES: tuple[str, ...] = (
    "review_queue",
    "mistake_book",
    "attempt",
    "question_bank_item",
    "vocab_item",
    "mock_exam",
    "assessment",
    "weekly_report",
    "cert_deadline",
    "mastery",
    "plan_task",
    "study_plan",
    "doc_chunk",
    "source_doc",
    "school_profile",
    "knowledge_point",
)

PROFILE_MUTABLE_FIELDS: tuple[str, ...] = (
    "title",
    "cert_type",
    "level",
    "exam_date",
    "target_score",
    "current_estimate",
    "subjects",
    "daily_minutes",
    "status",
)

JSON_PROFILE_FIELDS: frozenset[str] = frozenset({"subjects"})


class CampusError(Exception):
    """A business failure carrying one documented code, its message and any extra detail.

    The code is validated by the router when it is translated (`ERROR_SPECS[code]` raises
    `KeyError` for a code that is not in 03 §6), so this layer cannot invent a status.
    """

    def __init__(self, code: str, message: Optional[str] = None, **extra: Any) -> None:
        super().__init__(message or code)
        self.code = code
        self.message = message
        self.extra = extra


def _decode(value: Any, default: Any) -> Any:
    """Read a JSON column, returning `default` for NULL, empty and unparsable values."""
    if value is None or value == "":
        return default
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return default


def _encode(value: Any) -> Optional[str]:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False)


def profile_payload(profile: models.ExamProfile) -> dict[str, Any]:
    """The documented resource body: every stored column, JSON columns decoded (03 §1)."""
    payload = asdict(profile)
    for name in JSON_PROFILE_FIELDS:
        payload[name] = _decode(payload.get(name), [])
    return payload


@dataclass(frozen=True)
class ModelInventory:
    """Which models this machine can actually call — the input to every AI decision.

    ADR-06 rules out a runtime capability probe (`providers/base.py` carries no structured
    output flag), so "supported" means "a usable model is reachable for this task", not "this
    model handles JSON well". The static recommendation list in `models.TASK_MODEL_CHOICES`
    stays the single source of per-task advice.
    """

    current: str = ""
    ready: bool = False
    selectable: tuple[str, ...] = ()
    endpoints: tuple[str, ...] = ()

    def usable(self, model: Optional[str]) -> bool:
        """Whether `model` can be called: declared selectable, or the active ready default."""
        if not model:
            return False
        if model in self.selectable:
            return True
        return bool(self.ready and model == self.current)

    @classmethod
    def from_manager(cls, manager: Any) -> "ModelInventory":
        """Read the sidecar's model state, degrading to "nothing configured".

        Only public surface is touched (`SessionManager.model` and `get_settings()`), and a
        manager that cannot answer — a stub in a unit test, or a sidecar still starting up —
        yields an empty inventory instead of raising. Denying AI calls is the safe default:
        G-04 requires an unconfigured model to be refused with a clear notice rather than
        attempted.
        """
        current = str(getattr(manager, "model", "") or "")
        settings: Mapping[str, Any] = {}
        getter = getattr(manager, "get_settings", None)
        if callable(getter):
            try:
                settings = getter() or {}
            except Exception:
                settings = {}
        if not isinstance(settings, Mapping):
            settings = {}
        selectable = tuple(str(m) for m in (settings.get("models") or ()) if m)
        endpoints = tuple(sorted({_provider_of(model) for model in selectable}))
        return cls(
            current=str(settings.get("model") or current),
            ready=bool(settings.get("model_ready")),
            selectable=selectable,
            endpoints=endpoints,
        )


def _provider_of(model: str) -> str:
    """The provider a model id routes to, following `SessionManager._model_provider`."""
    prefix, _, _rest = model.partition(":")
    return prefix if _rest else "openai"


class CampusService:
    """Global-domain orchestration (07 §4 T09).

    `store` is the single `campus.db` handle and `config` the resolved `[campus]` preferences;
    both are shared with the router that builds this service. `provider_host` is the sidecar
    object that owns the `ProviderClient` (campus only reads `.provider` off it), used by the
    AI endpoints of the E group.
    """

    def __init__(
        self,
        campus_store: CampusStore,
        config: Any,
        *,
        inventory: Optional[ModelInventory] = None,
        provider_host: Any = None,
    ) -> None:
        self._store = campus_store
        self._config = config
        self._inventory = inventory if inventory is not None else ModelInventory()
        self._provider_host = provider_host

    @property
    def inventory(self) -> ModelInventory:
        return self._inventory

    # -- A1-A5: profiles ---------------------------------------------------

    def list_profiles(
        self, *, track: Optional[str] = None, status: Optional[str] = None
    ) -> list[dict[str, Any]]:
        """Every profile, newest first, optionally narrowed by track and status (A1).

        Archived profiles stay listed: they are reversible (02 §7.2) and the switcher needs to
        show them to offer the restore action.
        """
        conditions: list[str] = []
        params: list[Any] = []
        if track:
            conditions.append('"track_type" = ?')
            params.append(track)
        if status:
            conditions.append('"status" = ?')
            params.append(status)
        rows = self._store.list_rows(
            "exam_profile",
            where=" AND ".join(conditions) or None,
            params=params,
            order_by="created_at DESC, id",
        )
        return [profile_payload(models.ExamProfile.from_row(row)) for row in rows]

    def create_profile(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        """Create a profile, refusing a title already in use (A2)."""
        title = str(payload["title"]).strip()
        self._assert_title_free(title)
        daily_minutes = payload.get("daily_minutes")
        values: dict[str, Any] = {
            "track_type": payload["track_type"],
            "title": title,
            "cert_type": payload.get("cert_type"),
            "level": payload.get("level"),
            "exam_date": payload.get("exam_date"),
            "target_score": payload.get("target_score"),
            "subjects": _encode(payload.get("subjects") or []),
            "daily_minutes": DEFAULT_DAILY_MINUTES if daily_minutes is None else daily_minutes,
            "status": models.ProfileStatus.ACTIVE.value,
        }
        profile_id = self._store.insert("exam_profile", values)
        return self.get_profile(profile_id)

    def get_profile(self, profile_id: str) -> dict[str, Any]:
        """The profile body, or `PROFILE_NOT_FOUND` (A3)."""
        row = self._store.get("exam_profile", profile_id)
        if row is None:
            raise CampusError("PROFILE_NOT_FOUND", f"档案不存在：{profile_id}")
        return profile_payload(models.ExamProfile.from_row(row))

    def update_profile(
        self, profile: models.ExamProfile, patch: Mapping[str, Any]
    ) -> dict[str, Any]:
        """Apply a partial update, refusing a rename onto another profile's title (A4).

        Only the fields of `PROFILE_MUTABLE_FIELDS` are honoured; `track_type` is deliberately
        not among them, because a profile's track decides the meaning of everything it owns.
        """
        values: dict[str, Any] = {}
        for name in PROFILE_MUTABLE_FIELDS:
            if name not in patch:
                continue
            value = patch[name]
            if name == "title":
                value = str(value).strip()
                if value != profile.title:
                    self._assert_title_free(value, exclude=profile.id)
            if name in JSON_PROFILE_FIELDS:
                value = _encode(value or [])
            values[name] = value
        if not values:
            return self.get_profile(profile.id)
        self._store.update("exam_profile", profile.id, values)
        return self.get_profile(profile.id)

    def delete_profile(self, profile: models.ExamProfile) -> dict[str, Any]:
        """Delete a profile with its whole subtree, reporting the rows removed (A5, 02 §7.3).

        The cascade runs in one transaction in leaf-first order, so an interrupted delete never
        leaves orphan rows; the library directory goes afterwards, because the database is the
        authority and a re-import can rebuild the files (02 §7.3).
        """
        cascade: dict[str, int] = {}
        with self._store.transaction():
            for table in CASCADE_TABLES:
                cascade[table] = self._store.delete_where(table, "profile_id = ?", (profile.id,))
            cascade["exam_profile"] = int(self._store.delete("exam_profile", profile.id))
        if self._store.get_state(ACTIVE_PROFILE_KEY) == profile.id:
            self._store.delete_state(ACTIVE_PROFILE_KEY)
        self._remove_library_dir(profile.id)
        return {"deleted": True, "cascade": {table: rows for table, rows in cascade.items() if rows}}

    # -- A6-A7: app state and campus preferences ---------------------------

    def app_state(self) -> dict[str, Any]:
        """The global app state: the active profile pointer and the resolved preferences (A6).

        The stored `campus_settings` holds only what the user explicitly chose, and wins over
        `config.toml` (02 §4.2 "运行时以 app_state 为准"); every absent key falls back to the
        config value. `task_models` always reports all three tasks, resolved through
        `CampusConfig.resolve_task_model`, so the settings panel never needs the static list.
        """
        stored = self._stored_settings()
        overrides = stored.get("task_models")
        overrides = overrides if isinstance(overrides, dict) else {}
        return {
            "active_profile_id": self._store.get_state(ACTIVE_PROFILE_KEY, None),
            "settings": {
                "daily_minutes": self._setting(
                    stored, "daily_minutes", self._config.daily_minutes
                ),
                "push_time": self._setting(stored, "push_time", self._config.push_time),
                "review_intensity": self._setting(
                    stored, "review_intensity", self._config.review_intensity
                ),
                "task_models": {
                    task.value: overrides.get(task.value)
                    or self._config.resolve_task_model(task.value)
                    for task in models.CampusTask
                },
            },
        }

    def update_app_state(self, patch: Mapping[str, Any]) -> dict[str, Any]:
        """Point `active_profile_id` at a real profile and/or merge preference changes (A7).

        An explicit `null` clears the key and falls back to the config file, which is how the
        settings panel offers "reset to default" without a second endpoint.
        """
        if "active_profile_id" in patch:
            value = patch["active_profile_id"]
            if value is None:
                self._store.delete_state(ACTIVE_PROFILE_KEY)
            else:
                if self._store.get("exam_profile", str(value)) is None:
                    raise CampusError("PROFILE_NOT_FOUND", f"档案不存在：{value}")
                self._store.set_state(ACTIVE_PROFILE_KEY, str(value))
        settings_patch = patch.get("settings")
        if isinstance(settings_patch, Mapping) and settings_patch:
            self._merge_settings(settings_patch)
        return self.app_state()

    # -- internals ---------------------------------------------------------

    def _stored_settings(self) -> dict[str, Any]:
        stored = self._store.get_state(SETTINGS_KEY, {})
        return dict(stored) if isinstance(stored, dict) else {}

    def _setting(self, stored: Mapping[str, Any], name: str, default: Any) -> Any:
        value = stored.get(name)
        return default if value is None else value

    def _merge_settings(self, patch: Mapping[str, Any]) -> None:
        stored = self._stored_settings()
        for name in ("daily_minutes", "push_time", "review_intensity"):
            if name not in patch:
                continue
            if patch[name] is None:
                stored.pop(name, None)
            else:
                stored[name] = patch[name]
        if "task_models" in patch:
            overrides = dict(stored.get("task_models") or {})
            for task, model in (patch["task_models"] or {}).items():
                if model:
                    overrides[str(task)] = str(model)
                else:
                    overrides.pop(str(task), None)
            if overrides:
                stored["task_models"] = overrides
            else:
                stored.pop("task_models", None)
        if stored:
            self._store.set_state(SETTINGS_KEY, stored)
        else:
            self._store.delete_state(SETTINGS_KEY)

    def _assert_title_free(self, title: str, *, exclude: Optional[str] = None) -> None:
        row = self._store.query_one('SELECT "id" FROM "exam_profile" WHERE "title" = ?', (title,))
        if row is not None and row["id"] != exclude:
            raise CampusError("DUPLICATE_TITLE", f"同名档案已存在：{title}")

    def _remove_library_dir(self, profile_id: str) -> None:
        """Drop `campus/library/<profile_id>/`, staying inside the state directory."""
        root = Path(state_dir())
        target = root / "campus" / "library" / profile_id
        if target.parent.name != "library" or root not in target.parents:
            return
        shutil.rmtree(target, ignore_errors=True)
