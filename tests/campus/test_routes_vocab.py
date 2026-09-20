"""F6-F9 高频词端点（03 §4.6、PRD CET2）。

四条契约要点：

* **今日词表**（F6）：新词按真题词频（`freq_rank`，NULL 排最后）取，上限 30（PRD CET2 用户故事
  "每天只背 30 个词"）；已在复习队列里的词不再作为新词出现；复习项按到期时间给出并内联词条内容。
* **掌握标记**（F7）：03 的取值是 `known|fuzzy|unknown`，而 02 §4.11 的列取值是
  `unknown|fuzzy|mastered` —— 服务端接受两套写法、统一落库为列口径（05 的 `known` 视为 `mastered`）。
  标记"不认识"即入复习队列（次日到期）；队列推进与"连续答对三次后不再出现"属 T13 的 D6/`review_scheduler`。
* **自定义词表导入**（F8）：MD 一行一词、CSV 表头式，按 `(profile_id, word)` 唯一索引去重。
* **助记**（F9）：AI 生成后经既有 memory 链路写入（01 §4.2），用户关闭 Memory 时只回传不落库。
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
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
FOREIGN_VOCAB_ID = "vocab-foreign"
TOMORROW = (date.today() + timedelta(days=1)).isoformat()
NOW = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
PAST = "2026-01-01T00:00:00Z"


class FakeMemoryStore:
    def __init__(self) -> None:
        self.items: list[Any] = []

    def add(self, content: str, *, scope: Any = None, summary: Any = None, **kwargs: Any):
        item = SimpleNamespace(id=len(self.items) + 1, content=content, scope=scope, summary=summary)
        self.items.append(item)
        return item


class FakeMemorySettings:
    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled


class FakeProvider:
    def __init__(self, responses: dict[Any, Any] | None = None) -> None:
        self.responses = responses if responses is not None else {"default": "谐音：abandon = 我放弃"}
        self.seen: list[dict] = []

    def complete(self, *, model: str, messages: list[dict], **settings: Any):
        self.seen.append({"model": model, "messages": messages, "settings": settings})
        value = self.responses.get(len(self.seen), self.responses.get("default", ""))
        if isinstance(value, Exception):
            raise value
        return SimpleNamespace(text=value)


class FakeManager:
    def __init__(
        self,
        model: str = "fake:model",
        *,
        ready: bool = True,
        provider: Any = None,
        memory_enabled: bool = True,
    ) -> None:
        self.model = model
        self._ready = ready
        self.provider = provider if provider is not None else FakeProvider()
        self.memory_store = FakeMemoryStore()
        self.memory_settings = FakeMemorySettings(memory_enabled)

    def get_settings(self) -> dict[str, Any]:
        return {"model": self.model, "model_ready": self._ready, "models": [self.model] if self.model else []}


@pytest.fixture()
def campus_db_path() -> Path:
    return secrets.state_dir() / "campus.db"


@pytest.fixture()
def manager() -> FakeManager:
    return FakeManager()


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
        "vocab_item",
        {
            "id": FOREIGN_VOCAB_ID,
            "profile_id": OTHER_ID,
            "word": "foreign",
            "meaning": "外国的",
            "freq_rank": 2,
        },
    )
    try:
        yield instance
    finally:
        instance.close()


@pytest.fixture()
def client(manager: FakeManager, seeded_store: store.CampusStore) -> TestClient:
    app = FastAPI()
    app.include_router(routes.build_campus_router(manager))
    return TestClient(app)


def _detail(response) -> dict:
    return response.json()["detail"]


def _seed_words(campus_store: store.CampusStore, count: int) -> list[str]:
    ids = []
    for index in range(count):
        word_id = f"word-{index:03d}"
        campus_store.insert(
            "vocab_item",
            {
                "id": word_id,
                "profile_id": ACTIVE_ID,
                "word": f"word{index}",
                "meaning": "释义",
                "freq_rank": 100 + index,
            },
        )
        ids.append(word_id)
    return ids


# ---------------------------------------------------------------------------
# F6 GET /vocab/today
# ---------------------------------------------------------------------------

def test_f6_returns_a_new_word_list_capped_at_thirty(client: TestClient, seeded_store: store.CampusStore) -> None:
    _seed_words(seeded_store, 35)
    body = client.get(f"{routes.CAMPUS_PREFIX}/vocab/today", params={"profile_id": ACTIVE_ID}).json()
    assert len(body["new_items"]) == 30
    assert body["new_items"][0]["id"] == VOCAB_ID
    assert body["review_items"] == []


def test_f6_orders_the_new_words_by_exam_frequency(client: TestClient, seeded_store: store.CampusStore) -> None:
    _seed_words(seeded_store, 3)
    seeded_store.update("vocab_item", "word-000", {"freq_rank": 5})
    seeded_store.update("vocab_item", "word-001", {"freq_rank": None})
    body = client.get(f"{routes.CAMPUS_PREFIX}/vocab/today", params={"profile_id": ACTIVE_ID}).json()
    ranks = [item["freq_rank"] for item in body["new_items"]]
    assert ranks[:3] == [1, 5, 100 + 2]
    assert ranks[-1] is None


def test_f6_skips_words_that_are_already_mastered(client: TestClient, seeded_store: store.CampusStore) -> None:
    seeded_store.update("vocab_item", VOCAB_ID, {"mastery": models.MasteryLevel.MASTERED.value})
    body = client.get(f"{routes.CAMPUS_PREFIX}/vocab/today", params={"profile_id": ACTIVE_ID}).json()
    assert body["new_items"] == []


def test_f6_keeps_queued_words_out_of_the_new_list(client: TestClient, seeded_store: store.CampusStore) -> None:
    seeded_store.insert(
        "review_queue",
        {
            "id": "rq-1",
            "profile_id": ACTIVE_ID,
            "item_type": models.ReviewItemType.VOCAB.value,
            "item_id": VOCAB_ID,
            "due_at": TOMORROW,
        },
    )
    body = client.get(f"{routes.CAMPUS_PREFIX}/vocab/today", params={"profile_id": ACTIVE_ID}).json()
    assert body["new_items"] == []


def test_f6_lists_due_reviews_with_their_word(client: TestClient, seeded_store: store.CampusStore) -> None:
    seeded_store.insert(
        "review_queue",
        {
            "id": "rq-due",
            "profile_id": ACTIVE_ID,
            "item_type": models.ReviewItemType.VOCAB.value,
            "item_id": VOCAB_ID,
            "due_at": PAST,
        },
    )
    seeded_store.insert(
        "review_queue",
        {
            "id": "rq-later",
            "profile_id": ACTIVE_ID,
            "item_type": models.ReviewItemType.VOCAB.value,
            "item_id": FOREIGN_VOCAB_ID,
            "due_at": "2099-01-01T00:00:00Z",
        },
    )
    body = client.get(f"{routes.CAMPUS_PREFIX}/vocab/today", params={"profile_id": ACTIVE_ID}).json()
    assert [item["id"] for item in body["review_items"]] == ["rq-due"]
    assert body["review_items"][0]["payload"]["word"] == "abandon"


def test_f6_never_shows_another_profile_words(client: TestClient) -> None:
    body = client.get(f"{routes.CAMPUS_PREFIX}/vocab/today", params={"profile_id": OTHER_ID}).json()
    assert [item["id"] for item in body["new_items"]] == [FOREIGN_VOCAB_ID]


def test_f6_requires_a_profile(client: TestClient) -> None:
    response = client.get(f"{routes.CAMPUS_PREFIX}/vocab/today")
    assert response.status_code == 400
    assert _detail(response)["code"] == "PROFILE_REQUIRED"


def test_f6_reads_a_finished_profile(client: TestClient) -> None:
    assert client.get(
        f"{routes.CAMPUS_PREFIX}/vocab/today", params={"profile_id": FINISHED_ID}
    ).status_code == 200


# ---------------------------------------------------------------------------
# F7 PATCH /vocab/{id}
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "sent, stored",
    [
        ("known", models.MasteryLevel.MASTERED.value),
        ("mastered", models.MasteryLevel.MASTERED.value),
        ("fuzzy", models.MasteryLevel.FUZZY.value),
        ("unknown", models.MasteryLevel.UNKNOWN.value),
    ],
)
def test_f7_maps_the_documented_mastery_words(
    client: TestClient, seeded_store: store.CampusStore, sent: str, stored: str
) -> None:
    response = client.patch(
        f"{routes.CAMPUS_PREFIX}/vocab/{VOCAB_ID}", json={"profile_id": ACTIVE_ID, "mastery": sent}
    )
    assert response.status_code == 200
    assert response.json()["mastery"] == stored
    assert seeded_store.get("vocab_item", VOCAB_ID)["mastery"] == stored


def test_f7_enqueues_an_unknown_word_for_tomorrow(client: TestClient, seeded_store: store.CampusStore) -> None:
    response = client.patch(
        f"{routes.CAMPUS_PREFIX}/vocab/{VOCAB_ID}", json={"profile_id": ACTIVE_ID, "mastery": "unknown"}
    )
    assert response.status_code == 200
    rows = seeded_store.list_rows("review_queue", profile_id=ACTIVE_ID)
    assert len(rows) == 1
    assert rows[0]["item_type"] == models.ReviewItemType.VOCAB.value
    assert rows[0]["item_id"] == VOCAB_ID
    assert rows[0]["due_at"].startswith(TOMORROW)
    assert rows[0]["interval_days"] == 1
    assert rows[0]["streak_right"] == 0
    assert rows[0]["status"] == models.ReviewStatus.PENDING.value


def test_f7_does_not_enqueue_the_same_word_twice(client: TestClient, seeded_store: store.CampusStore) -> None:
    for _ in range(2):
        client.patch(
            f"{routes.CAMPUS_PREFIX}/vocab/{VOCAB_ID}", json={"profile_id": ACTIVE_ID, "mastery": "unknown"}
        )
    assert seeded_store.count("review_queue", "profile_id = ?", (ACTIVE_ID,)) == 1


def test_f7_keeps_known_words_out_of_the_queue(client: TestClient, seeded_store: store.CampusStore) -> None:
    client.patch(
        f"{routes.CAMPUS_PREFIX}/vocab/{VOCAB_ID}", json={"profile_id": ACTIVE_ID, "mastery": "known"}
    )
    assert seeded_store.count("review_queue", "profile_id = ?", (ACTIVE_ID,)) == 0


def test_f7_rejects_an_unknown_mastery_value(client: TestClient) -> None:
    response = client.patch(
        f"{routes.CAMPUS_PREFIX}/vocab/{VOCAB_ID}", json={"profile_id": ACTIVE_ID, "mastery": "nope"}
    )
    assert response.status_code == 422


def test_f7_returns_item_not_found_for_an_unknown_word(client: TestClient) -> None:
    response = client.patch(
        f"{routes.CAMPUS_PREFIX}/vocab/no-such-word", json={"profile_id": ACTIVE_ID, "mastery": "known"}
    )
    assert response.status_code == 404
    assert _detail(response)["code"] == "ITEM_NOT_FOUND"


def test_f7_refuses_another_profile_word(client: TestClient) -> None:
    response = client.patch(
        f"{routes.CAMPUS_PREFIX}/vocab/{FOREIGN_VOCAB_ID}",
        json={"profile_id": ACTIVE_ID, "mastery": "known"},
    )
    assert response.status_code == 403
    assert _detail(response)["code"] == "FORBIDDEN_PROFILE"


def test_f7_refuses_a_finished_profile(client: TestClient) -> None:
    response = client.patch(
        f"{routes.CAMPUS_PREFIX}/vocab/{VOCAB_ID}", json={"profile_id": FINISHED_ID, "mastery": "known"}
    )
    assert response.status_code == 409
    assert _detail(response)["code"] == "PROFILE_READ_ONLY"


# ---------------------------------------------------------------------------
# F8 POST /vocab/import
# ---------------------------------------------------------------------------

def _import(client: TestClient, content: str, fmt: str = "md", profile_id: str = ACTIVE_ID):
    return client.post(
        f"{routes.CAMPUS_PREFIX}/vocab/import",
        json={"profile_id": profile_id, "format": fmt, "content": content},
    )


def test_f8_imports_one_word_per_markdown_line(client: TestClient, seeded_store: store.CampusStore) -> None:
    body = _import(client, "abandon\nbenefit\ncrucial\n").json()
    assert body == {"imported": 2, "skipped": 1}
    assert seeded_store.count("vocab_item", "profile_id = ?", (ACTIVE_ID,)) == 3


def test_f8_imports_the_extended_markdown_form(client: TestClient, seeded_store: store.CampusStore) -> None:
    _import(client, "crucial|/ˈkruːʃl/|关键的|It is crucial to sleep.\n")
    row = seeded_store.query_one("SELECT * FROM vocab_item WHERE word = ?", ("crucial",))
    assert row["phonetic"] == "/ˈkruːʃl/"
    assert row["meaning"] == "关键的"
    assert row["example"] == "It is crucial to sleep."


def test_f8_imports_a_csv_with_a_header(client: TestClient, seeded_store: store.CampusStore) -> None:
    body = _import(client, "word,phonetic,meaning\nbenefit,,益处\ncrucial,,关键的\n", fmt="csv").json()
    assert body["imported"] == 2
    assert seeded_store.count("vocab_item", "profile_id = ?", (ACTIVE_ID,)) == 3


def test_f8_skips_words_that_are_already_stored(client: TestClient, seeded_store: store.CampusStore) -> None:
    body = _import(client, "abandon\nabandon\n").json()
    assert body == {"imported": 0, "skipped": 2}
    assert seeded_store.count("vocab_item", "profile_id = ?", (ACTIVE_ID,)) == 1


@pytest.mark.parametrize(
    "content, fmt, line",
    [
        ("word,meaning\n,缺失\n", "csv", 2),
        ("word\n", "csv", 1),
        ("word,meaning\nx,y,z\n", "csv", 2),
        ("word,,meaning\nx,y,z\n", "csv", 1),
    ],
)
def test_f8_reports_the_offending_line(client: TestClient, content: str, fmt: str, line: int) -> None:
    response = _import(client, content, fmt=fmt)
    assert response.status_code == 422
    assert _detail(response)["code"] == "PARSE_ERROR"
    assert _detail(response)["line"] == line


@pytest.mark.parametrize("content", ["", "   \n\n"])
def test_f8_rejects_empty_content(client: TestClient, content: str) -> None:
    response = _import(client, content)
    assert response.status_code == 422
    assert _detail(response)["code"] == "PARSE_ERROR"


def test_f8_rejects_an_unknown_format(client: TestClient) -> None:
    assert _import(client, "abandon", fmt="xlsx").status_code == 422


def test_f8_refuses_a_finished_profile(client: TestClient, seeded_store: store.CampusStore) -> None:
    response = _import(client, "newword\n", profile_id=FINISHED_ID)
    assert response.status_code == 409
    assert _detail(response)["code"] == "PROFILE_READ_ONLY"
    assert seeded_store.count("vocab_item", "profile_id = ?", (FINISHED_ID,)) == 0


def test_f8_requires_a_profile(client: TestClient) -> None:
    response = client.post(f"{routes.CAMPUS_PREFIX}/vocab/import", json={"format": "md", "content": "x"})
    assert response.status_code == 400
    assert _detail(response)["code"] == "PROFILE_REQUIRED"


# ---------------------------------------------------------------------------
# F9 POST /vocab/mnemonic
# ---------------------------------------------------------------------------

def test_f9_returns_a_mnemonic_and_writes_it_to_memory(client: TestClient, manager: FakeManager) -> None:
    body = client.post(f"{routes.CAMPUS_PREFIX}/vocab/mnemonic", json={"vocab_id": VOCAB_ID}, params={"profile_id": ACTIVE_ID}).json()
    assert body["mnemonic"] == "谐音：abandon = 我放弃"
    assert body["saved"] is True
    assert manager.memory_store.items
    assert "abandon" in manager.memory_store.items[0].content


def test_f9_asks_the_model_about_this_word(client: TestClient, manager: FakeManager) -> None:
    client.post(f"{routes.CAMPUS_PREFIX}/vocab/mnemonic", json={"vocab_id": VOCAB_ID}, params={"profile_id": ACTIVE_ID})
    prompt = "\n".join(str(message.get("content", "")) for message in manager.provider.seen[0]["messages"])
    assert "abandon" in prompt


def test_f9_keeps_working_when_memory_saving_is_off(seeded_store: store.CampusStore) -> None:
    app = FastAPI()
    app.include_router(routes.build_campus_router(FakeManager(memory_enabled=False)))
    client = TestClient(app)
    body = client.post(f"{routes.CAMPUS_PREFIX}/vocab/mnemonic", json={"vocab_id": VOCAB_ID}, params={"profile_id": ACTIVE_ID}).json()
    assert body["mnemonic"]
    assert body["saved"] is False


def test_f9_returns_item_not_found_for_an_unknown_word(client: TestClient) -> None:
    response = client.post(f"{routes.CAMPUS_PREFIX}/vocab/mnemonic", json={"vocab_id": "nope"}, params={"profile_id": ACTIVE_ID})
    assert response.status_code == 404
    assert _detail(response)["code"] == "ITEM_NOT_FOUND"


def test_f9_refuses_another_profile_word(client: TestClient) -> None:
    response = client.post(f"{routes.CAMPUS_PREFIX}/vocab/mnemonic", json={"vocab_id": FOREIGN_VOCAB_ID}, params={"profile_id": ACTIVE_ID})
    assert response.status_code == 403
    assert _detail(response)["code"] == "FORBIDDEN_PROFILE"


def test_f9_refuses_without_a_configured_model(seeded_store: store.CampusStore) -> None:
    app = FastAPI()
    app.include_router(routes.build_campus_router(FakeManager(model="", ready=False)))
    client = TestClient(app)
    response = client.post(f"{routes.CAMPUS_PREFIX}/vocab/mnemonic", json={"vocab_id": VOCAB_ID}, params={"profile_id": ACTIVE_ID})
    assert response.status_code == 409
    assert _detail(response)["code"] == "MODEL_NOT_CONFIGURED"


def test_f9_reports_a_timeout(seeded_store: store.CampusStore) -> None:
    app = FastAPI()
    app.include_router(
        routes.build_campus_router(FakeManager(provider=FakeProvider({"default": TimeoutError("slow")})))
    )
    client = TestClient(app)
    response = client.post(f"{routes.CAMPUS_PREFIX}/vocab/mnemonic", json={"vocab_id": VOCAB_ID}, params={"profile_id": ACTIVE_ID})
    assert response.status_code == 504
    assert _detail(response)["code"] == "MODEL_TIMEOUT"


def test_f9_requires_a_profile(client: TestClient) -> None:
    response = client.post(f"{routes.CAMPUS_PREFIX}/vocab/mnemonic", json={"vocab_id": VOCAB_ID})
    assert response.status_code == 400
    assert _detail(response)["code"] == "PROFILE_REQUIRED"
