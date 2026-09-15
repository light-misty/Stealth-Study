"""T09 端点清单与端到端主链（07 §4 T09 的 16 个端点、08 §8 "端点契约抽查"）。

两个互补的证据：

* `test_route_inventory_matches_the_t09_contract` —— 把 03 §4 里属于 T09 的 16 个端点（A1-A10、
  E1-E5、G1）连同方法逐一钉死，任何端点的漏注册/方法写错/路径漂移都会红；
* `test_the_global_domain_story_runs_end_to_end` —— 用一条真实主线把 16 个端点串起来跑一遍
  （建档 → 设为当前 → 自检 → 导题 → 录题/改题/删题 → 客观题与主观题作答 → 今日任务 → 隐私面板
  → 删档 → 一键清除），证明它们在同一份 store/guard/service 上协同工作而不是各自孤立可跑。
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ss import secrets
from ss.campus import models, routes, store

CAMPUS = routes.CAMPUS_PREFIX

T09_ENDPOINTS: tuple[tuple[str, str], ...] = (
    ("GET", "/profiles"),
    ("POST", "/profiles"),
    ("GET", "/profiles/{pid}"),
    ("PATCH", "/profiles/{pid}"),
    ("DELETE", "/profiles/{pid}"),
    ("GET", "/app-state"),
    ("PATCH", "/app-state"),
    ("GET", "/capabilities"),
    ("GET", "/privacy"),
    ("DELETE", "/privacy/data"),
    ("POST", "/questions/import"),
    ("GET", "/questions"),
    ("POST", "/questions"),
    ("PATCH", "/questions/{qid}"),
    ("DELETE", "/questions/{qid}"),
    ("POST", "/attempts"),
    ("GET", "/tasks"),
)

T12_ENDPOINTS: tuple[tuple[str, str], ...] = (
    ("GET", "/knowledge-tree"),
    ("POST", "/knowledge-points"),
    ("PATCH", "/knowledge-points/{point_id}"),
    ("DELETE", "/knowledge-points/{point_id}"),
    ("POST", "/knowledge-tree/generate"),
    ("PATCH", "/mastery"),
    ("GET", "/mastery/coverage"),
)

TODAY = "2026-09-15"


def essay_payload() -> str:
    return json.dumps(
        {
            "band": 11,
            "dimension_scores": {"content": 4, "structure": 4, "language": 3},
            "errors": [{"fragment": "a", "suggestion": "b", "type": "拼写"}],
            "upgraded_demo": "demo",
            "model_answer_outline": "outline",
        }
    )


def scoring_payload() -> str:
    return json.dumps(
        {
            "scoring_points": [
                {"point": "答出德育原则", "status": "hit", "note": ""},
                {"point": "结合材料", "status": "miss", "note": ""},
            ],
            "overall_score": 6,
        }
    )


class FakeProvider:
    """Answers whichever schema the prompt asks for, so both kinds grade at L0."""

    def complete(self, *, model: str, messages: list[dict], **settings: Any):
        prompt = "\n".join(str(message.get("content", "")) for message in messages)
        return SimpleNamespace(text=scoring_payload() if "scoring_points" in prompt else essay_payload())


class FakeManager:
    def __init__(self, model: str = "fake:model") -> None:
        self.model = model
        self.provider = FakeProvider()

    def get_settings(self) -> dict[str, Any]:
        return {"model": self.model, "model_ready": True, "models": [self.model]}


def test_route_inventory_matches_the_t09_contract() -> None:
    router = routes.build_campus_router(object())
    declared = {
        (method, route.path.removeprefix(CAMPUS))
        for route in router.routes
        for method in route.methods
    }
    for method, path in (*T09_ENDPOINTS, *T12_ENDPOINTS):
        assert (method, path) in declared, f"{method} {path} is not registered"


def test_the_mounted_router_holds_no_endpoint_outside_the_contract() -> None:
    router = routes.build_campus_router(object())
    declared = {
        (method, route.path.removeprefix(CAMPUS))
        for route in router.routes
        for method in route.methods
    }
    allowed = {*T09_ENDPOINTS, *T12_ENDPOINTS, ("GET", "/health")}
    assert declared == allowed


def test_the_global_domain_story_runs_end_to_end(tmp_path: Path) -> None:
    app = FastAPI()
    app.include_router(routes.build_campus_router(FakeManager()))
    client = TestClient(app)
    campus_db = secrets.state_dir() / "campus.db"

    assert client.get(f"{CAMPUS}/profiles").json() == {"items": []}

    created = client.post(
        f"{CAMPUS}/profiles",
        json={
            "track_type": models.TrackType.CERT.value,
            "title": "教资高中语文",
            "cert_type": models.CertType.TEACHING.value,
            "exam_date": "2027-03-14",
            "subjects": ["综合素质"],
        },
    )
    assert created.status_code == 200
    profile_id = created.json()["id"]

    assert client.patch(
        f"{CAMPUS}/app-state", json={"active_profile_id": profile_id}
    ).json()["active_profile_id"] == profile_id
    assert client.get(f"{CAMPUS}/app-state").json()["active_profile_id"] == profile_id

    capabilities = client.get(f"{CAMPUS}/capabilities").json()
    assert capabilities["current_model"] == "fake:model"
    assert all(entry["supported"] for entry in capabilities["tasks"])

    imported = client.post(
        f"{CAMPUS}/questions/import",
        json={
            "profile_id": profile_id,
            "format": "md",
            "content": (
                "题干：德育原则有哪些？\n科目：综合素质\n类型：short_answer\n分值：8\n\n"
                "题干：下列说法正确的是？\n科目：综合素质\n选项：A.甲|B.乙\n答案：A\n"
            ),
        },
    ).json()
    assert imported["imported"] == 2

    subjective_id = imported["items"][0]["id"]
    objective_id = imported["items"][1]["id"]

    listed = client.get(
        f"{CAMPUS}/questions", params={"profile_id": profile_id, "page_size": 10}
    ).json()
    assert listed["total"] == 2

    manual = client.post(
        f"{CAMPUS}/questions",
        json={"profile_id": profile_id, "subject": "综合素质", "stem": "手动录入题", "answer": "A"},
    ).json()
    assert manual["qtype"] == models.QuestionType.SINGLE.value

    patched = client.patch(
        f"{CAMPUS}/questions/{manual['id']}",
        json={"profile_id": profile_id, "stem": "手动录入题（已修订）"},
    )
    assert patched.json()["stem"] == "手动录入题（已修订）"

    objective = client.post(
        f"{CAMPUS}/attempts",
        json={"profile_id": profile_id, "question_id": objective_id, "answer": "A"},
    ).json()
    assert objective["is_correct"] == 1 and objective["standard_answer"] == "A"

    seeded = store.CampusStore(campus_db)
    try:
        seeded.insert(
            "study_plan", {"id": "plan-story", "profile_id": profile_id, "track": None}
        )
        seeded.insert(
            "plan_task",
            {
                "id": "task-story",
                "plan_id": "plan-story",
                "profile_id": profile_id,
                "title": "背德育原则",
                "subject": "综合素质",
                "scheduled_date": TODAY,
                "priority": 1,
            },
        )
    finally:
        seeded.close()
    tasks = client.get(
        f"{CAMPUS}/tasks", params={"profile_id": profile_id, "date": TODAY}
    ).json()
    assert [task["id"] for task in tasks["items"]] == ["task-story"]

    subjective = client.post(
        f"{CAMPUS}/attempts",
        json={"profile_id": profile_id, "question_id": subjective_id, "answer": "德育原则……"},
    ).json()
    assert subjective["pending_grading"] is True
    assert subjective["grading_json"]["scoring_points"][0]["status"] == "hit"

    privacy = client.get(f"{CAMPUS}/privacy").json()
    assert privacy["data_dir"] == str(secrets.state_dir())
    assert privacy["model_endpoints"] == ["fake"]
    assert privacy["db_size_bytes"] > 0

    removed = client.delete(f"{CAMPUS}/questions/{manual['id']}", params={"profile_id": profile_id})
    assert removed.json() == {"deleted": True}

    deletion = client.delete(f"{CAMPUS}/profiles/{profile_id}").json()
    assert deletion["deleted"] is True
    cascade = deletion["cascade"]
    assert cascade["attempt"] == 2
    assert cascade["question_bank_item"] == 2
    assert cascade["plan_task"] == 1
    assert client.get(f"{CAMPUS}/profiles/{profile_id}").status_code == 404

    cleared = client.delete(f"{CAMPUS}/privacy/data").json()
    assert cleared["cleared"] is True
    assert client.get(f"{CAMPUS}/profiles").json() == {"items": []}
    assert client.get(f"{CAMPUS}/app-state").json()["active_profile_id"] is None
