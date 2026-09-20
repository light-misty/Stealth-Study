"""E 组题库端点（03 §4.5 E1-E4、07 §4 T09 验收③）。

E1 的导入格式在 03 文档里只写了 `format: md|csv`，格式细节由本阶段定义并在此钉住：一个 MD
块 = 若干 `标签：值` 行，块间以空行分隔，`#` 开头为注释行；CSV 的首行表头使用同一套标签。
任何无法解析的行都以 `PARSE_ERROR` + 物理行号定位返回，不做静默丢弃。

E4/E5 的子资源读取走 `ProfileGuard.scoped_row`，因此本文件同时是 07 §4 T09 验收③
（每个端点带 `FORBIDDEN_PROFILE` 负例）在 E 组的落点：E3/E4 的 `point_id` 采用作用域读取，
跨档案引用一律 `POINT_NOT_FOUND`，不暴露他人资源的存续状态。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from stealth_study import secrets
from stealth_study.campus import models, routes, store

ACTIVE_ID = "profile-active"
OTHER_ID = "profile-other"
FINISHED_ID = "profile-finished"
FORGED_ID = "nonexistent-uuid"
POINT_ID = "point-1"
FOREIGN_POINT_ID = "point-foreign"
QUESTION_ID = "question-1"
FOREIGN_QUESTION_ID = "question-foreign"

MD_TEMPLATE = """# 第一章 词汇
题干：下列说法正确的是？
科目：reading
类型：single
选项：A.甲|B.乙|C.丙|D.丁
答案：A
分值：2
难度：2

题干：{stem2}
科目：reading
选项：A.甲|B.乙
答案：B
"""

CSV_SAMPLE = "题干,科目,类型,选项,答案\n题干一,reading,single,A.甲|B.乙,A\n题干二,vocab,blank,,abandon\n"


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
            {"id": profile_id, "track_type": models.TrackType.CERT.value, "title": title, "status": status},
        )
    for point_id, profile_id in ((POINT_ID, ACTIVE_ID), (FOREIGN_POINT_ID, OTHER_ID)):
        instance.insert("knowledge_point", {"id": point_id, "profile_id": profile_id, "title": point_id})
    for question_id, profile_id in ((QUESTION_ID, ACTIVE_ID), (FOREIGN_QUESTION_ID, OTHER_ID)):
        instance.insert(
            "question_bank_item",
            {
                "id": question_id,
                "profile_id": profile_id,
                "subject": models.Subject.READING.value,
                "stem": f"题干 {question_id}",
                "answer": "A",
            },
        )
    try:
        yield instance
    finally:
        instance.close()


@pytest.fixture()
def client(seeded_store: store.CampusStore) -> TestClient:
    app = FastAPI()
    app.include_router(routes.build_campus_router(object()))
    return TestClient(app)


def _detail(response) -> dict:
    return response.json()["detail"]


def _import(client: TestClient, content: str, fmt: str = "md", profile_id: str = ACTIVE_ID):
    return client.post(
        f"{routes.CAMPUS_PREFIX}/questions/import",
        json={"profile_id": profile_id, "format": fmt, "content": content},
    )


def _create(client: TestClient, **overrides) -> dict:
    payload = {"profile_id": ACTIVE_ID, "subject": "reading", "stem": "新建题干"}
    payload.update(overrides)
    return client.post(f"{routes.CAMPUS_PREFIX}/questions", json=payload).json()


# ---------------------------------------------------------------------------
# E1 POST /questions/import
# ---------------------------------------------------------------------------

def test_e1_imports_markdown_blocks(client: TestClient) -> None:
    response = _import(client, MD_TEMPLATE.format(stem2="第二题"))
    assert response.status_code == 200
    body = response.json()
    assert body["imported"] == 2
    assert body["skipped"] == 0
    assert [item["stem"] for item in body["items"]] == ["下列说法正确的是？", "第二题"]


def test_e1_applies_the_documented_defaults(client: TestClient) -> None:
    items = _import(client, MD_TEMPLATE.format(stem2="第二题")).json()["items"]
    first, second = items
    assert first["qtype"] == models.QuestionType.SINGLE.value
    assert first["max_score"] == 2
    assert first["difficulty"] == 2
    assert first["answer"] == "A"
    assert first["options"] == [
        {"key": "A", "text": "甲"},
        {"key": "B", "text": "乙"},
        {"key": "C", "text": "丙"},
        {"key": "D", "text": "丁"},
    ]
    assert second["qtype"] == models.QuestionType.SINGLE.value
    assert second["max_score"] == 1
    assert second["difficulty"] is None
    assert second["source"] == models.QuestionSource.MANUAL.value


def test_e1_imports_a_hundred_questions(client: TestClient) -> None:
    content = "\n".join(f"题干：第 {index} 题\n科目：reading\n答案：A\n" for index in range(100))
    body = _import(client, content).json()
    assert body["imported"] == 100
    listed = client.get(
        f"{routes.CAMPUS_PREFIX}/questions",
        params={"profile_id": ACTIVE_ID, "page_size": 100},
    ).json()
    assert listed["total"] == 101


def test_e1_skips_questions_that_are_already_imported(client: TestClient) -> None:
    content = MD_TEMPLATE.format(stem2="第二题")
    _import(client, content)
    body = _import(client, content).json()
    assert body["imported"] == 0
    assert body["skipped"] == 2
    assert body["items"] == []


def test_e1_counts_a_duplicate_inside_one_payload_as_skipped(client: TestClient) -> None:
    content = "题干：重复题\n科目：reading\n\n题干：重复题\n科目：reading\n"
    body = _import(client, content).json()
    assert body["imported"] == 1
    assert body["skipped"] == 1


def test_e1_accepts_the_english_label_aliases(client: TestClient) -> None:
    content = "stem: English stem\nsubject: reading\nqtype: blank\nanswer: abandon\n"
    items = _import(client, content).json()["items"]
    assert items[0]["stem"] == "English stem"
    assert items[0]["qtype"] == models.QuestionType.BLANK.value


def test_e1_imports_csv_rows(client: TestClient) -> None:
    response = _import(client, CSV_SAMPLE, fmt="csv")
    assert response.status_code == 200
    body = response.json()
    assert body["imported"] == 2
    assert body["items"][0]["options"] == [{"key": "A", "text": "甲"}, {"key": "B", "text": "乙"}]
    assert body["items"][1]["qtype"] == models.QuestionType.BLANK.value


def test_e1_reports_the_line_of_an_unparsable_markdown_line(client: TestClient) -> None:
    content = "题干：第一题\n科目：reading\n\n这是一行没有标签的文字\n"
    response = _import(client, content)
    assert response.status_code == 422
    assert _detail(response)["code"] == "PARSE_ERROR"
    assert _detail(response)["line"] == 4


def test_e1_reports_the_line_of_an_unknown_label(client: TestClient) -> None:
    response = _import(client, "题干：第一题\n科目：reading\n解析：略\n")
    assert response.status_code == 422
    assert _detail(response)["line"] == 3


def test_e1_reports_a_missing_required_label(client: TestClient) -> None:
    response = _import(client, "题干：没有科目的一题\n")
    assert response.status_code == 422
    assert _detail(response)["code"] == "PARSE_ERROR"
    assert _detail(response)["line"] == 1


def test_e1_imports_nothing_when_one_block_is_broken(client: TestClient, seeded_store) -> None:
    response = _import(client, "题干：好题\n科目：reading\n\n题干：坏题\n科目：reading\n分值：两分\n")
    assert response.status_code == 422
    assert seeded_store.count("question_bank_item", "profile_id = ?", (ACTIVE_ID,)) == 1


@pytest.mark.parametrize(
    "content",
    [
        "题干：题\n科目：reading\n类型：不存在的题型\n",
        "题干：题\n科目：reading\n分值：两分\n",
        "题干：题\n科目：reading\n难度：9\n",
        "题干：题\n科目：reading\n选项：甲|乙\n",
        "题干：题\n科目：reading\n选项：A.甲|\n",
    ],
)
def test_e1_rejects_out_of_range_values(client: TestClient, content: str) -> None:
    response = _import(client, content)
    assert response.status_code == 422
    assert _detail(response)["code"] == "PARSE_ERROR"
    assert isinstance(_detail(response)["line"], int)


@pytest.mark.parametrize("content", ["", "   \n\n", "# 只有注释\n"])
def test_e1_rejects_content_without_any_question(client: TestClient, content: str) -> None:
    response = _import(client, content)
    assert response.status_code == 422
    assert _detail(response)["code"] == "PARSE_ERROR"


def test_e1_rejects_an_unknown_format(client: TestClient) -> None:
    assert _import(client, MD_TEMPLATE.format(stem2="x"), fmt="xlsx").status_code == 422


def test_e1_rejects_a_csv_without_the_required_columns(client: TestClient) -> None:
    response = _import(client, "题干,类型\n题一,single\n", fmt="csv")
    assert response.status_code == 422
    assert _detail(response)["line"] == 1


def test_e1_rejects_a_ragged_csv_row(client: TestClient) -> None:
    response = _import(client, "题干,科目,答案\n题一,reading\n", fmt="csv")
    assert response.status_code == 422
    assert _detail(response)["line"] == 2


def test_e1_rejects_an_empty_csv_cell_that_is_required(client: TestClient) -> None:
    response = _import(client, "题干,科目\n,reading\n", fmt="csv")
    assert response.status_code == 422
    assert _detail(response)["line"] == 2


def test_e1_refuses_import_on_a_finished_profile(client: TestClient) -> None:
    response = _import(client, MD_TEMPLATE.format(stem2="x"), profile_id=FINISHED_ID)
    assert response.status_code == 409
    assert _detail(response)["code"] == "PROFILE_READ_ONLY"


def test_e1_requires_a_profile(client: TestClient) -> None:
    response = client.post(
        f"{routes.CAMPUS_PREFIX}/questions/import",
        json={"format": "md", "content": "题干：题\n科目：reading\n"},
    )
    assert response.status_code == 400
    assert _detail(response)["code"] == "PROFILE_REQUIRED"


# ---------------------------------------------------------------------------
# E2 GET /questions
# ---------------------------------------------------------------------------

def test_e2_returns_the_documented_page_envelope(client: TestClient) -> None:
    _create(client, stem="第一题")
    _create(client, stem="第二题")
    body = client.get(
        f"{routes.CAMPUS_PREFIX}/questions", params={"profile_id": ACTIVE_ID}
    ).json()
    assert body["total"] == 3
    assert body["page"] == 1
    assert body["page_size"] == 50
    assert len(body["items"]) == 3


def test_e2_pages_through_the_result(client: TestClient) -> None:
    _create(client, stem="第一题")
    _create(client, stem="第二题")
    first = client.get(
        f"{routes.CAMPUS_PREFIX}/questions",
        params={"profile_id": ACTIVE_ID, "page": 1, "page_size": 2},
    ).json()
    second = client.get(
        f"{routes.CAMPUS_PREFIX}/questions",
        params={"profile_id": ACTIVE_ID, "page": 2, "page_size": 2},
    ).json()
    assert first["total"] == 3 and len(first["items"]) == 2
    assert len(second["items"]) == 1
    assert {item["id"] for item in first["items"]}.isdisjoint(item["id"] for item in second["items"])


def test_e2_filters_by_qtype_subject_and_point(client: TestClient) -> None:
    _create(client, stem="选择题", qtype=models.QuestionType.SINGLE.value, point_id=POINT_ID)
    _create(client, stem="填空题", qtype=models.QuestionType.BLANK.value)
    by_type = client.get(
        f"{routes.CAMPUS_PREFIX}/questions",
        params={"profile_id": ACTIVE_ID, "qtype": models.QuestionType.BLANK.value},
    ).json()
    assert [item["stem"] for item in by_type["items"]] == ["填空题"]
    by_point = client.get(
        f"{routes.CAMPUS_PREFIX}/questions",
        params={"profile_id": ACTIVE_ID, "point_id": POINT_ID},
    ).json()
    assert [item["stem"] for item in by_point["items"]] == ["选择题"]
    by_subject = client.get(
        f"{routes.CAMPUS_PREFIX}/questions",
        params={"profile_id": ACTIVE_ID, "subject": "vocab"},
    ).json()
    assert by_subject["total"] == 0


def test_e2_never_leaks_another_profile_question(client: TestClient) -> None:
    body = client.get(
        f"{routes.CAMPUS_PREFIX}/questions", params={"profile_id": OTHER_ID}
    ).json()
    assert [item["id"] for item in body["items"]] == [FOREIGN_QUESTION_ID]


def test_e2_rejects_unknown_filters(client: TestClient) -> None:
    assert (
        client.get(
            f"{routes.CAMPUS_PREFIX}/questions",
            params={"profile_id": ACTIVE_ID, "qtype": "nope"},
        ).status_code
        == 422
    )
    assert (
        client.get(
            f"{routes.CAMPUS_PREFIX}/questions",
            params={"profile_id": ACTIVE_ID, "page_size": 0},
        ).status_code
        == 422
    )


# ---------------------------------------------------------------------------
# E3 POST /questions
# ---------------------------------------------------------------------------

def test_e3_creates_a_question_with_the_documented_defaults(client: TestClient) -> None:
    body = _create(client)
    assert body["qtype"] == models.QuestionType.SINGLE.value
    assert body["max_score"] == 1
    assert body["source"] == models.QuestionSource.MANUAL.value
    assert body["point_id"] is None
    assert body["options"] is None
    assert body["id"]


def test_e3_persists_options_and_answer_meta_as_json(client: TestClient) -> None:
    body = _create(
        client,
        options=[{"key": "A", "text": "甲"}, {"key": "B", "text": "乙"}],
        answer_meta={"scoring_points": ["甲"], "source_page": 12},
        max_score=2.5,
        difficulty=3,
        point_id=POINT_ID,
    )
    assert body["options"] == [{"key": "A", "text": "甲"}, {"key": "B", "text": "乙"}]
    assert body["answer_meta"] == {"scoring_points": ["甲"], "source_page": 12}
    assert body["max_score"] == 2.5
    assert body["difficulty"] == 3
    assert body["point_id"] == POINT_ID


def test_e3_returns_point_not_found_for_an_unknown_point(client: TestClient) -> None:
    response = client.post(
        f"{routes.CAMPUS_PREFIX}/questions",
        json={"profile_id": ACTIVE_ID, "subject": "reading", "stem": "题", "point_id": "no-such-point"},
    )
    assert response.status_code == 404
    assert _detail(response)["code"] == "POINT_NOT_FOUND"


def test_e3_does_not_leak_another_profile_point(client: TestClient) -> None:
    response = client.post(
        f"{routes.CAMPUS_PREFIX}/questions",
        json={"profile_id": ACTIVE_ID, "subject": "reading", "stem": "题", "point_id": FOREIGN_POINT_ID},
    )
    assert response.status_code == 404
    assert _detail(response)["code"] == "POINT_NOT_FOUND"


@pytest.mark.parametrize(
    "payload",
    [
        {"profile_id": ACTIVE_ID, "stem": "题"},
        {"profile_id": ACTIVE_ID, "subject": "reading", "stem": "  "},
        {"profile_id": ACTIVE_ID, "subject": "reading", "stem": "题", "qtype": "nope"},
        {"profile_id": ACTIVE_ID, "subject": "reading", "stem": "题", "difficulty": 9},
        {"profile_id": ACTIVE_ID, "subject": "reading", "stem": "题", "options": [{"text": "甲"}]},
    ],
)
def test_e3_rejects_malformed_bodies(client: TestClient, payload: dict) -> None:
    assert client.post(f"{routes.CAMPUS_PREFIX}/questions", json=payload).status_code == 422


def test_e3_refuses_a_finished_profile(client: TestClient) -> None:
    response = client.post(
        f"{routes.CAMPUS_PREFIX}/questions",
        json={"profile_id": FINISHED_ID, "subject": "reading", "stem": "题"},
    )
    assert response.status_code == 409
    assert _detail(response)["code"] == "PROFILE_READ_ONLY"


# ---------------------------------------------------------------------------
# E4 PATCH / DELETE /questions/{qid}
# ---------------------------------------------------------------------------

def test_e4_updates_the_supplied_fields(client: TestClient) -> None:
    body = client.patch(
        f"{routes.CAMPUS_PREFIX}/questions/{QUESTION_ID}",
        json={"profile_id": ACTIVE_ID, "stem": "改过的题干", "answer": "BC", "point_id": POINT_ID},
    ).json()
    assert body["stem"] == "改过的题干"
    assert body["answer"] == "BC"
    assert body["point_id"] == POINT_ID
    assert body["subject"] == models.Subject.READING.value


def test_e4_replaces_and_clears_options(client: TestClient) -> None:
    client.patch(
        f"{routes.CAMPUS_PREFIX}/questions/{QUESTION_ID}",
        json={"profile_id": ACTIVE_ID, "options": [{"key": "A", "text": "甲"}]},
    )
    cleared = client.patch(
        f"{routes.CAMPUS_PREFIX}/questions/{QUESTION_ID}",
        json={"profile_id": ACTIVE_ID, "options": None},
    ).json()
    assert cleared["options"] is None


def test_e4_validates_the_target_point(client: TestClient) -> None:
    response = client.patch(
        f"{routes.CAMPUS_PREFIX}/questions/{QUESTION_ID}",
        json={"profile_id": ACTIVE_ID, "point_id": FOREIGN_POINT_ID},
    )
    assert response.status_code == 404
    assert _detail(response)["code"] == "POINT_NOT_FOUND"


def test_e4_refuses_a_question_of_another_profile(client: TestClient) -> None:
    response = client.patch(
        f"{routes.CAMPUS_PREFIX}/questions/{FOREIGN_QUESTION_ID}",
        json={"profile_id": ACTIVE_ID, "stem": "偷改"},
    )
    assert response.status_code == 403
    assert _detail(response)["code"] == "FORBIDDEN_PROFILE"


def test_e4_returns_question_not_found_for_an_unknown_question(client: TestClient) -> None:
    response = client.patch(
        f"{routes.CAMPUS_PREFIX}/questions/no-such-question",
        json={"profile_id": ACTIVE_ID, "stem": "x"},
    )
    assert response.status_code == 404
    assert _detail(response)["code"] == "QUESTION_NOT_FOUND"


def test_e4_requires_the_profile_id_in_the_body(client: TestClient) -> None:
    response = client.patch(
        f"{routes.CAMPUS_PREFIX}/questions/{QUESTION_ID}", json={"stem": "x"}
    )
    assert response.status_code == 400
    assert _detail(response)["code"] == "PROFILE_REQUIRED"


def test_e4_deletes_a_question(client: TestClient) -> None:
    response = client.delete(
        f"{routes.CAMPUS_PREFIX}/questions/{QUESTION_ID}", params={"profile_id": ACTIVE_ID}
    )
    assert response.status_code == 200
    assert response.json() == {"deleted": True}
    listed = client.get(
        f"{routes.CAMPUS_PREFIX}/questions", params={"profile_id": ACTIVE_ID}
    ).json()
    assert QUESTION_ID not in {item["id"] for item in listed["items"]}


def test_e4_refuses_to_delete_another_profile_question(client: TestClient) -> None:
    response = client.delete(
        f"{routes.CAMPUS_PREFIX}/questions/{FOREIGN_QUESTION_ID}", params={"profile_id": ACTIVE_ID}
    )
    assert response.status_code == 403
    assert _detail(response)["code"] == "FORBIDDEN_PROFILE"


def test_e4_delete_returns_question_not_found_for_an_unknown_question(client: TestClient) -> None:
    response = client.delete(
        f"{routes.CAMPUS_PREFIX}/questions/no-such-question", params={"profile_id": ACTIVE_ID}
    )
    assert response.status_code == 404
    assert _detail(response)["code"] == "QUESTION_NOT_FOUND"


def test_e4_refuses_writes_on_a_finished_profile(client: TestClient) -> None:
    patched = client.patch(
        f"{routes.CAMPUS_PREFIX}/questions/{QUESTION_ID}",
        json={"profile_id": FINISHED_ID, "stem": "x"},
    )
    deleted = client.delete(
        f"{routes.CAMPUS_PREFIX}/questions/{QUESTION_ID}", params={"profile_id": FINISHED_ID}
    )
    assert patched.status_code == 409 and _detail(patched)["code"] == "PROFILE_READ_ONLY"
    assert deleted.status_code == 409 and _detail(deleted)["code"] == "PROFILE_READ_ONLY"


def test_e4_rejects_unknown_ids_and_fields(client: TestClient) -> None:
    assert (
        client.delete(f"{routes.CAMPUS_PREFIX}/questions/{QUESTION_ID}").status_code == 400
    )
    assert (
        client.patch(
            f"{routes.CAMPUS_PREFIX}/questions/{QUESTION_ID}",
            json={"profile_id": ACTIVE_ID, "unknown_field": 1},
        ).status_code
        == 422
    )


def test_e4_leaves_the_row_untouched_when_the_patch_is_rejected(
    client: TestClient, seeded_store: store.CampusStore
) -> None:
    rejected = client.patch(
        f"{routes.CAMPUS_PREFIX}/questions/{QUESTION_ID}",
        json={"profile_id": ACTIVE_ID, "stem": "偷改", "point_id": FOREIGN_POINT_ID},
    )
    assert rejected.status_code == 404
    row = seeded_store.get("question_bank_item", QUESTION_ID)
    assert row["stem"] == f"题干 {QUESTION_ID}"
    assert row["point_id"] is None


def test_imported_questions_carry_a_usable_id_and_json_columns(
    client: TestClient, seeded_store: store.CampusStore
) -> None:
    items = _import(client, MD_TEMPLATE.format(stem2="第二题")).json()["items"]
    row = seeded_store.get("question_bank_item", items[0]["id"])
    assert json.loads(row["options"])[0] == {"key": "A", "text": "甲"}
    assert row["profile_id"] == ACTIVE_ID
