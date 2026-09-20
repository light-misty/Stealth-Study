"""G7/G8/G9 目标院校档案端点（03 §4.7、07 §4 T11 的 KY-14）。

三件事钉住：

* G7/G8 是"一档案一院校档案"（`UQ idx_school_profile`）的读与 UPSERT 写——未保存时
  G7 返回 `id=None` 的空壳（03 §4.7 未给 G7 登记任何错误码，读不该 404），首次 PATCH 建行；
* G8 的字段校验在 Pydantic 完成（`degree_type` 枚举、`recommend_ratio` 0-1、
  `past_scores` 的 {year, line} 形状），非法体一律 422，绝不静默丢字段；
* G9 简章抽取走 `_complete_json`（与 F5 同一条模型链路），只保留合法字段并按
  "抽到字段数 / 8" 计 `confidence`——模型输出坏掉降级为空 prefill 而非报错（03 §4.7
  未给 G9 登记 MODEL_OUTPUT_INVALID），未配模型仍按 MODEL_NOT_CONFIGURED 拒绝。
"""

from __future__ import annotations

import json
from typing import Any, Optional

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from stealth_study import secrets
from stealth_study.campus import models, routes, store

ACTIVE_ID = "profile-active"
FINISHED_ID = "profile-finished"

EXTRACT_JSON = json.dumps(
    {
        "school": "华东师范大学",
        "major": "教育学",
        "degree_type": "academic",
        "subjects": [{"name": "教育学统考", "code": "311"}, "英语一"],
        "enroll_count": 120,
        "recommend_ratio": 0.2,
        "past_scores": [{"year": 2025, "line": 351}, {"year": 2024, "line": "347"}],
        "books": ["《教育学基础》", ""],
    }
)


@pytest.fixture()
def campus_db_path() -> Any:
    return secrets.state_dir() / "campus.db"


@pytest.fixture()
def seeded_store(campus_db_path: Any) -> store.CampusStore:
    instance = store.CampusStore(campus_db_path)
    for profile_id, title, status in (
        (ACTIVE_ID, "2027 考研", models.ProfileStatus.ACTIVE.value),
        (FINISHED_ID, "已结课", models.ProfileStatus.FINISHED.value),
    ):
        instance.insert(
            "exam_profile",
            {
                "id": profile_id,
                "track_type": models.TrackType.KAOYAN.value,
                "title": title,
                "status": status,
            },
        )
    try:
        yield instance
    finally:
        instance.close()


class FakeManager:
    def __init__(self, text: str = "", error: Optional[Exception] = None) -> None:
        self.model = "stub:extractor"
        self.provider = self
        self._text = text
        self._error = error
        self.calls: list[dict[str, Any]] = []

    def get_settings(self) -> dict[str, Any]:
        return {"model": self.model, "model_ready": True, "models": [self.model]}

    def complete(self, *, model: str, messages: list[dict], **settings: Any) -> Any:
        from types import SimpleNamespace

        self.calls.append({"model": model, "messages": messages, "settings": settings})
        if self._error is not None:
            raise self._error
        return SimpleNamespace(text=self._text)


@pytest.fixture()
def client(seeded_store: store.CampusStore) -> TestClient:
    app = FastAPI()
    app.include_router(routes.build_campus_router(object()))
    return TestClient(app)


@pytest.fixture()
def extract_client(seeded_store: store.CampusStore) -> TestClient:
    app = FastAPI()
    app.include_router(routes.build_campus_router(FakeManager(text=EXTRACT_JSON)))
    return TestClient(app)


def _get(client: TestClient, profile_id: str = ACTIVE_ID) -> Any:
    return client.get(f"{routes.CAMPUS_PREFIX}/school-profile", params={"profile_id": profile_id})


def _patch(client: TestClient, payload: dict, profile_id: str = ACTIVE_ID) -> Any:
    return client.patch(
        f"{routes.CAMPUS_PREFIX}/school-profile",
        json=payload,
        params={"profile_id": profile_id},
    )


def _extract(client: TestClient, text: str, profile_id: str = ACTIVE_ID) -> Any:
    return client.post(
        f"{routes.CAMPUS_PREFIX}/school-profile/extract",
        json={"profile_id": profile_id, "text": text},
        params={"profile_id": profile_id},
    )


# ---------- G7：读院校档案 ----------


def test_g7_returns_an_empty_shell_before_the_first_save(client: TestClient) -> None:
    response = _get(client)
    assert response.status_code == 200
    body = response.json()
    assert body["id"] is None
    assert body["profile_id"] == ACTIVE_ID
    assert body["school"] == ""
    assert body["subjects"] == []
    assert body["past_scores"] == []
    assert body["books"] == []


def test_g7_returns_the_saved_card(client: TestClient) -> None:
    _patch(
        client,
        {
            "school": "北京师范大学",
            "major": "学前教育学",
            "subjects": ["教育学"],
        },
    )
    body = _get(client).json()
    assert body["id"]
    assert body["school"] == "北京师范大学"
    assert body["subjects"] == ["教育学"]


def test_g7_requires_a_profile(client: TestClient) -> None:
    response = client.get(f"{routes.CAMPUS_PREFIX}/school-profile")
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "PROFILE_REQUIRED"


def test_g7_refuses_a_forged_profile(client: TestClient) -> None:
    response = _get(client, "nonexistent-uuid")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "PROFILE_NOT_FOUND"


# ---------- G8：UPSERT 院校档案 ----------


def test_g8_creates_the_card_on_the_first_patch(client: TestClient) -> None:
    response = _patch(
        client,
        {
            "school": "北京师范大学",
            "major": "学前教育学",
            "degree_type": "academic",
            "subjects": ["教育学", "发展心理学"],
            "enroll_count": 45,
            "recommend_ratio": 0.3,
            "past_scores": [{"year": 2025, "line": 355}],
            "books": ["《教育学基础》"],
            "note": "统考 311",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["id"]
    assert body["degree_type"] == "academic"
    assert body["enroll_count"] == 45
    assert body["recommend_ratio"] == 0.3
    assert body["past_scores"] == [{"year": 2025, "line": 355}]
    assert body["note"] == "统考 311"
    assert body["created_at"] and body["updated_at"]


def test_g8_updates_the_same_row_in_place(client: TestClient) -> None:
    first = _patch(client, {"school": "北京师范大学"}).json()
    second = _patch(client, {"school": "华东师范大学", "enroll_count": 88}).json()
    assert second["id"] == first["id"]
    assert second["school"] == "华东师范大学"
    assert second["enroll_count"] == 88
    assert second["major"] is None or second["major"] in ("", None)


def test_g8_rejects_invalid_fields(client: TestClient) -> None:
    assert _patch(client, {"degree_type": "unknown"}).status_code == 422
    assert _patch(client, {"recommend_ratio": 1.5}).status_code == 422
    assert _patch(client, {"enroll_count": -1}).status_code == 422
    assert _patch(client, {"past_scores": [{"year": 2025}]}).status_code == 422
    assert _patch(client, {"books": "not-a-list"}).status_code == 422
    assert _patch(client, {"board_card_id": "x"}).status_code == 422


def test_g8_refuses_a_finished_profile(client: TestClient) -> None:
    response = _patch(client, {"school": "任意"}, profile_id=FINISHED_ID)
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "PROFILE_READ_ONLY"


def test_g8_requires_a_profile(client: TestClient) -> None:
    response = client.patch(f"{routes.CAMPUS_PREFIX}/school-profile", json={"school": "任意"})
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "PROFILE_REQUIRED"


# ---------- G9：简章抽取预填 ----------


def test_g9_requires_a_configured_model(client: TestClient) -> None:
    response = _extract(client, "华东师范大学 2026 年招收教育学硕士研究生 120 人")
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "MODEL_NOT_CONFIGURED"


def test_g9_extracts_at_least_three_fields(extract_client: TestClient) -> None:
    response = _extract(extract_client, "招生简章全文……")
    assert response.status_code == 200, response.text
    body = response.json()
    prefill = body["prefill"]
    assert len(prefill) >= 3
    assert prefill["school"] == "华东师范大学"
    assert prefill["degree_type"] == "academic"
    assert prefill["subjects"] == ["教育学统考", "英语一"]
    assert prefill["enroll_count"] == 120
    assert prefill["recommend_ratio"] == 0.2
    assert prefill["past_scores"] == [
        {"year": 2025, "line": 351.0},
        {"year": 2024, "line": 347.0},
    ]
    assert prefill["books"] == ["《教育学基础》"]
    assert body["confidence"] == 1.0


def test_g9_degrades_to_an_empty_prefill_on_garbage(seeded_store: store.CampusStore) -> None:
    app = FastAPI()
    app.include_router(routes.build_campus_router(FakeManager(text="完全不是结构化输出的内容")))
    client = TestClient(app)
    response = _extract(client, "招生简章全文……")
    assert response.status_code == 200
    assert response.json() == {"prefill": {}, "confidence": 0.0}


def test_g9_maps_model_failure_to_model_timeout(seeded_store: store.CampusStore) -> None:
    app = FastAPI()
    app.include_router(routes.build_campus_router(FakeManager(error=RuntimeError("ReadTimeout"))))
    client = TestClient(app)
    response = _extract(client, "招生简章全文……")
    assert response.status_code == 504
    assert response.json()["detail"]["code"] == "MODEL_TIMEOUT"


def test_g9_rejects_blank_text(client: TestClient) -> None:
    response = _extract(client, "   ")
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "PARSE_ERROR"


def test_g9_refuses_a_finished_profile(extract_client: TestClient) -> None:
    response = _extract(
        extract_client, "简章", profile_id=FINISHED_ID
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "PROFILE_READ_ONLY"


def test_g9_requires_a_profile(client: TestClient) -> None:
    response = client.post(
        f"{routes.CAMPUS_PREFIX}/school-profile/extract", json={"text": "简章"}
    )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "PROFILE_REQUIRED"


def test_g9_rejects_unknown_body_fields(client: TestClient) -> None:
    response = client.post(
        f"{routes.CAMPUS_PREFIX}/school-profile/extract",
        json={"profile_id": ACTIVE_ID, "text": "简章", "url": "https://example.com"},
    )
    assert response.status_code == 422
