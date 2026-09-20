"""D4-D6 复习队列端点（03 §4.4 G-17/CET-05、T13 承接，02 §4.15 review_queue）。

四条契约要点：

* **入队**（D4）：`item_type` 限定 mistake/vocab/knowledge_point，素材必须存在且属于该
  档案（缺失 `ITEM_NOT_FOUND`、跨档案 `FORBIDDEN_PROFILE`）；同一素材重复入队不产生第二条
  pending（02 §4.15 部分唯一索引的 UPSERT 口径，保留既有进度不重置）；`done` 行存在时允许
  重新入队生成新 pending。
* **到期拉取**（D5）：`pending` 且 `due_at <= as_of`（缺省取服务器当前时刻），按到期时间
  升序；payload 内联错题/词卡/知识点内容，源行已不存在的悬空引用跳过不炸。
* **结果回写**（D6）：答对沿 1/2/4/7/15 阶梯推进 `streak_right`/`interval_days`，答错重置
  回 1 天；未知队列项 `RQ_NOT_FOUND`、跨档案 403。
* **横切**：全部走 ProfileGuard（缺 `profile_id` 400、结课档案写 409），错误体为 03 §1 的
  结构化 `{code, message, retryable}`。
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from stealth_study import secrets
from stealth_study.campus import models, routes, store

ACTIVE_ID = "profile-active"
OTHER_ID = "profile-other"
FINISHED_ID = "profile-finished"
VOCAB_ID = "vocab-1"
POINT_ID = "point-1"
ATTEMPT_ID = "attempt-1"
MISTAKE_ID = "mistake-1"
TOMORROW = (date.today() + timedelta(days=1)).strftime("%Y-%m-%dT00:00:00Z")


class FakeManager:
    def __init__(self, model: str = "fake:model", *, ready: bool = True) -> None:
        self.model = model
        self._ready = ready

    def get_settings(self) -> dict[str, Any]:
        return {"model": self.model, "model_ready": self._ready, "models": [self.model] if self.model else []}


@pytest.fixture()
def campus_db_path() -> Path:
    return secrets.state_dir() / "campus.db"


@pytest.fixture()
def seeded_store(campus_db_path: Path) -> store.CampusStore:
    instance = store.CampusStore(campus_db_path)
    for profile_id, status, title in (
        (ACTIVE_ID, models.ProfileStatus.ACTIVE.value, "六级 12 月"),
        (OTHER_ID, models.ProfileStatus.ACTIVE.value, "另一个档案"),
        (FINISHED_ID, models.ProfileStatus.FINISHED.value, "已结课"),
    ):
        instance.insert(
            "exam_profile",
            {"id": profile_id, "track_type": models.TrackType.CET.value, "title": title, "status": status},
        )
    instance.insert(
        "vocab_item",
        {"id": VOCAB_ID, "profile_id": ACTIVE_ID, "word": "abandon", "meaning": "放弃", "freq_rank": 1},
    )
    instance.insert(
        "knowledge_point",
        {"id": POINT_ID, "profile_id": ACTIVE_ID, "title": "定语从句"},
    )
    instance.insert(
        "attempt",
        {
            "id": ATTEMPT_ID,
            "profile_id": ACTIVE_ID,
            "track_type": models.TrackType.CET.value,
            "subject": models.Subject.READING.value,
            "user_answer": "A",
            "is_correct": 0,
        },
    )
    instance.insert(
        "mistake_book",
        {
            "id": MISTAKE_ID,
            "profile_id": ACTIVE_ID,
            "attempt_id": ATTEMPT_ID,
            "track_type": models.TrackType.CET.value,
            "subject": models.Subject.READING.value,
            "attribution": models.Attribution.MISREAD.value,
            "wrong_count": 2,
            "last_wrong_at": "2026-09-14T00:00:00Z",
        },
    )
    try:
        yield instance
    finally:
        instance.close()


@pytest.fixture()
def client(seeded_store: store.CampusStore) -> TestClient:
    app = FastAPI()
    app.include_router(routes.build_campus_router(FakeManager()))
    return TestClient(app)


def _detail(response) -> dict:
    return response.json()["detail"]


def _enqueue(client: TestClient, item_type: str, item_id: str, profile_id: str = ACTIVE_ID):
    return client.post(
        "/v1/campus/review/items",
        json={"profile_id": profile_id, "item_type": item_type, "item_id": item_id},
    )


def _seed_queue(
    campus_store: store.CampusStore,
    row_id: str,
    *,
    profile_id: str = ACTIVE_ID,
    item_type: str = models.ReviewItemType.VOCAB.value,
    item_id: str = VOCAB_ID,
    due_at: str = "2026-09-01T00:00:00Z",
    status: str = models.ReviewStatus.PENDING.value,
    streak_right: int = 0,
    interval_days: int = 1,
) -> None:
    campus_store.insert(
        "review_queue",
        {
            "id": row_id,
            "profile_id": profile_id,
            "item_type": item_type,
            "item_id": item_id,
            "due_at": due_at,
            "interval_days": interval_days,
            "streak_right": streak_right,
            "status": status,
        },
    )


# ---------- D4：入队 ----------


def test_d4_enqueue_vocab_returns_a_fresh_pending_item(client: TestClient) -> None:
    response = _enqueue(client, "vocab", VOCAB_ID)
    assert response.status_code == 200
    body = response.json()
    assert body["profile_id"] == ACTIVE_ID
    assert body["item_type"] == "vocab"
    assert body["item_id"] == VOCAB_ID
    assert body["interval_days"] == 1
    assert body["streak_right"] == 0
    assert body["ease"] == 2.5
    assert body["status"] == "pending"
    assert body["due_at"].startswith(TOMORROW[:10])


def test_d4_enqueue_is_idempotent_while_pending(client: TestClient, seeded_store: store.CampusStore) -> None:
    first = _enqueue(client, "vocab", VOCAB_ID).json()
    second = _enqueue(client, "vocab", VOCAB_ID).json()
    assert second["id"] == first["id"]
    assert second["streak_right"] == first["streak_right"]
    assert seeded_store.count("review_queue") == 1


def test_d4_requeues_after_a_done_history_row(client: TestClient, seeded_store: store.CampusStore) -> None:
    _seed_queue(seeded_store, "rq-old", status=models.ReviewStatus.DONE.value, streak_right=4)
    body = _enqueue(client, "vocab", VOCAB_ID).json()
    assert body["id"] != "rq-old"
    assert body["status"] == "pending" and body["streak_right"] == 0


def test_d4_enqueues_a_mistake_item(client: TestClient) -> None:
    body = _enqueue(client, "mistake", MISTAKE_ID).json()
    assert body["item_type"] == "mistake" and body["item_id"] == MISTAKE_ID


def test_d4_enqueues_a_knowledge_point(client: TestClient) -> None:
    body = _enqueue(client, "knowledge_point", POINT_ID).json()
    assert body["item_type"] == "knowledge_point" and body["item_id"] == POINT_ID


def test_d4_unknown_item_is_refused(client: TestClient) -> None:
    response = _enqueue(client, "vocab", "vocab-missing")
    assert response.status_code == 404
    assert _detail(response)["code"] == "ITEM_NOT_FOUND"


def test_d4_foreign_item_is_refused(client: TestClient) -> None:
    response = client.post(
        "/v1/campus/review/items",
        json={"profile_id": OTHER_ID, "item_type": "vocab", "item_id": VOCAB_ID},
    )
    assert response.status_code == 403
    assert _detail(response)["code"] == "FORBIDDEN_PROFILE"


def test_d4_rejects_an_unknown_item_type(client: TestClient) -> None:
    response = _enqueue(client, "sentence", VOCAB_ID)
    assert response.status_code == 422


def test_d4_refuses_a_finished_profile(client: TestClient) -> None:
    response = _enqueue(client, "vocab", VOCAB_ID, profile_id=FINISHED_ID)
    assert response.status_code == 409
    assert _detail(response)["code"] == "PROFILE_READ_ONLY"


def test_d4_requires_the_profile_parameter(client: TestClient) -> None:
    response = client.post(
        "/v1/campus/review/items",
        json={"item_type": "vocab", "item_id": VOCAB_ID},
    )
    assert response.status_code == 400
    assert _detail(response)["code"] == "PROFILE_REQUIRED"


# ---------- D5：到期拉取 ----------


def test_d5_empty_queue_lists_nothing(client: TestClient) -> None:
    assert client.get("/v1/campus/review/due", params={"profile_id": ACTIVE_ID}).json() == {"items": []}


def test_d5_inlines_the_vocab_payload(client: TestClient, seeded_store: store.CampusStore) -> None:
    _seed_queue(seeded_store, "rq-vocab")
    body = client.get("/v1/campus/review/due", params={"profile_id": ACTIVE_ID}).json()
    assert len(body["items"]) == 1
    entry = body["items"][0]
    assert entry["id"] == "rq-vocab"
    assert entry["payload"]["word"] == "abandon"
    assert entry["payload"]["meaning"] == "放弃"


def test_d5_inlines_mistake_and_knowledge_payloads(
    client: TestClient, seeded_store: store.CampusStore
) -> None:
    _seed_queue(seeded_store, "rq-mistake", item_type=models.ReviewItemType.MISTAKE.value, item_id=MISTAKE_ID)
    _seed_queue(seeded_store, "rq-point", item_type=models.ReviewItemType.KNOWLEDGE_POINT.value, item_id=POINT_ID)
    body = client.get("/v1/campus/review/due", params={"profile_id": ACTIVE_ID}).json()
    payloads = {entry["id"]: entry["payload"] for entry in body["items"]}
    assert payloads["rq-mistake"]["attribution"] == models.Attribution.MISREAD.value
    assert payloads["rq-point"]["title"] == "定语从句"


def test_d5_excludes_future_rows_until_as_of(client: TestClient, seeded_store: store.CampusStore) -> None:
    _seed_queue(seeded_store, "rq-future", due_at="2999-01-01T00:00:00Z")
    assert client.get("/v1/campus/review/due", params={"profile_id": ACTIVE_ID}).json()["items"] == []
    pulled = client.get(
        "/v1/campus/review/due",
        params={"profile_id": ACTIVE_ID, "as_of": "2999-01-02T00:00:00Z"},
    ).json()
    assert [entry["id"] for entry in pulled["items"]] == ["rq-future"]


def test_d5_orders_by_due_time(client: TestClient, seeded_store: store.CampusStore) -> None:
    seeded_store.insert(
        "vocab_item", {"id": "vocab-late", "profile_id": ACTIVE_ID, "word": "late"}
    )
    seeded_store.insert(
        "vocab_item", {"id": "vocab-early", "profile_id": ACTIVE_ID, "word": "early"}
    )
    _seed_queue(seeded_store, "rq-late", item_id="vocab-late", due_at="2026-09-05T00:00:00Z")
    _seed_queue(seeded_store, "rq-early", item_id="vocab-early", due_at="2026-09-02T00:00:00Z")
    body = client.get("/v1/campus/review/due", params={"profile_id": ACTIVE_ID}).json()
    assert [entry["id"] for entry in body["items"]] == ["rq-early", "rq-late"]


def test_d5_skips_dangling_sources(client: TestClient, seeded_store: store.CampusStore) -> None:
    _seed_queue(seeded_store, "rq-dangling", item_id="vocab-deleted")
    assert client.get("/v1/campus/review/due", params={"profile_id": ACTIVE_ID}).json() == {"items": []}


def test_d5_isolates_profiles(client: TestClient, seeded_store: store.CampusStore) -> None:
    _seed_queue(seeded_store, "rq-mine")
    _seed_queue(seeded_store, "rq-theirs", profile_id=OTHER_ID, item_id="vocab-other")
    seeded_store.insert(
        "vocab_item", {"id": "vocab-other", "profile_id": OTHER_ID, "word": "foreign"}
    )
    mine = client.get("/v1/campus/review/due", params={"profile_id": ACTIVE_ID}).json()
    theirs = client.get("/v1/campus/review/due", params={"profile_id": OTHER_ID}).json()
    assert [entry["id"] for entry in mine["items"]] == ["rq-mine"]
    assert [entry["id"] for entry in theirs["items"]] == ["rq-theirs"]


def test_d5_rejects_a_malformed_as_of(client: TestClient) -> None:
    response = client.get(
        "/v1/campus/review/due", params={"profile_id": ACTIVE_ID, "as_of": "yesterday"}
    )
    assert response.status_code == 422


def test_d5_requires_the_profile_parameter(client: TestClient) -> None:
    response = client.get("/v1/campus/review/due")
    assert response.status_code == 400
    assert _detail(response)["code"] == "PROFILE_REQUIRED"


# ---------- D6：结果回写 ----------


def test_d6_correct_answer_walks_the_ladder(client: TestClient, seeded_store: store.CampusStore) -> None:
    _seed_queue(seeded_store, "rq-1", streak_right=0, interval_days=1)
    body = client.post(
        "/v1/campus/review/rq-1/result", json={"profile_id": ACTIVE_ID, "correct": True}
    ).json()
    assert body["streak_right"] == 1
    assert body["interval_days"] == 1
    assert body["status"] == "pending"
    assert body["last_reviewed_at"] is not None
    assert body["due_at"] > "2026-09-15"


def test_d6_ladder_progression_to_the_fifteen_day_cap(
    client: TestClient, seeded_store: store.CampusStore
) -> None:
    _seed_queue(seeded_store, "rq-1", streak_right=4, interval_days=7)
    body = client.post(
        "/v1/campus/review/rq-1/result", json={"profile_id": ACTIVE_ID, "correct": True}
    ).json()
    assert body["streak_right"] == 5
    assert body["interval_days"] == 15


def test_d6_wrong_answer_resets_to_one_day(client: TestClient, seeded_store: store.CampusStore) -> None:
    _seed_queue(seeded_store, "rq-1", streak_right=4, interval_days=7)
    body = client.post(
        "/v1/campus/review/rq-1/result", json={"profile_id": ACTIVE_ID, "correct": False}
    ).json()
    assert body["streak_right"] == 0
    assert body["interval_days"] == 1
    assert body["status"] == "pending"


def test_d6_persists_the_new_schedule(client: TestClient, seeded_store: store.CampusStore) -> None:
    _seed_queue(seeded_store, "rq-1", streak_right=2, interval_days=2)
    client.post(
        "/v1/campus/review/rq-1/result", json={"profile_id": ACTIVE_ID, "correct": True}
    )
    row = seeded_store.get("review_queue", "rq-1")
    assert row["streak_right"] == 3 and row["interval_days"] == 4


def test_d6_unknown_queue_item_is_refused(client: TestClient) -> None:
    response = client.post(
        "/v1/campus/review/rq-missing/result", json={"profile_id": ACTIVE_ID, "correct": True}
    )
    assert response.status_code == 404
    assert _detail(response)["code"] == "RQ_NOT_FOUND"


def test_d6_foreign_queue_item_is_refused(client: TestClient, seeded_store: store.CampusStore) -> None:
    _seed_queue(seeded_store, "rq-theirs", profile_id=OTHER_ID, item_id="vocab-other")
    seeded_store.insert(
        "vocab_item", {"id": "vocab-other", "profile_id": OTHER_ID, "word": "foreign"}
    )
    response = client.post(
        "/v1/campus/review/rq-theirs/result", json={"profile_id": ACTIVE_ID, "correct": True}
    )
    assert response.status_code == 403
    assert _detail(response)["code"] == "FORBIDDEN_PROFILE"


def test_d6_refuses_a_finished_profile(client: TestClient, seeded_store: store.CampusStore) -> None:
    _seed_queue(seeded_store, "rq-done-profile")
    response = client.post(
        "/v1/campus/review/rq-done-profile/result",
        json={"profile_id": FINISHED_ID, "correct": True},
    )
    assert response.status_code == 409
    assert _detail(response)["code"] == "PROFILE_READ_ONLY"


def test_d6_validates_the_result_body(client: TestClient, seeded_store: store.CampusStore) -> None:
    _seed_queue(seeded_store, "rq-1")
    missing = client.post("/v1/campus/review/rq-1/result", json={"profile_id": ACTIVE_ID})
    assert missing.status_code == 422
    non_bool = client.post(
        "/v1/campus/review/rq-1/result", json={"profile_id": ACTIVE_ID, "correct": "yes"}
    )
    assert non_bool.status_code == 422


def test_d6_full_ladder_across_five_correct_reviews(
    client: TestClient, seeded_store: store.CampusStore
) -> None:
    """验收①的端到端版：从入队到连对五次，间隔依次 1/2/4/7/15 天。"""
    created = _enqueue(client, "vocab", VOCAB_ID).json()
    intervals = []
    current = created
    for _ in range(5):
        current = client.post(
            f"/v1/campus/review/{current['id']}/result",
            json={"profile_id": ACTIVE_ID, "correct": True},
        ).json()
        intervals.append(current["interval_days"])
    assert intervals == [1, 2, 4, 7, 15]
    assert current["streak_right"] == 5
