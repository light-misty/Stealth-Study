"""Unit tests for the campus error-body helper (03 §1 error shape, 03 §6 code table).

Every campus failure must come back as a structured body rather than a bare string:

    {"detail": {"code": "...", "message": "...", "retryable": false}}

These tests pin the code table to 03 §6 (plus the four codes 03 §4 uses but §6 omits) and
pin the helper that turns a code into that body.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from stealth_study.campus import routes

SECTION_6_CODES: dict[str, tuple[int, bool]] = {
    "PROFILE_REQUIRED": (400, False),
    "PROFILE_NOT_FOUND": (404, False),
    "PROFILE_READ_ONLY": (409, False),
    "DUPLICATE_TITLE": (409, False),
    "DUPLICATE_NODE": (409, False),
    "EXAM_DATE_REQUIRED": (400, False),
    "FILE_TOO_LARGE": (413, False),
    "UNSUPPORTED_TYPE": (415, False),
    "DISK_FULL": (507, False),
    "DOC_NOT_FOUND": (404, False),
    "DOC_NOT_READY": (409, True),
    "DOC_SCAN_EMPTY": (422, False),
    "PARSE_ERROR": (422, False),
    "QUESTION_NOT_FOUND": (404, False),
    "POINT_NOT_FOUND": (404, False),
    "ATTEMPT_NOT_FOUND": (404, False),
    "RQ_NOT_FOUND": (404, False),
    "MOCK_NOT_FOUND": (404, False),
    "INVALID_ATTRIBUTION": (400, False),
    "INVALID_LEVEL": (400, False),
    "ILLEGAL_TRANSITION": (409, False),
    "ILLEGAL_STAGE": (409, False),
    "STAGE_LOCKED": (409, False),
    "MOCK_SUBMITTED": (409, False),
    "PAUSE_EXCEEDED": (409, False),
    "ASSESSMENT_FINISHED": (409, False),
    "MODEL_NOT_CONFIGURED": (409, False),
    "MODEL_TIMEOUT": (504, True),
    "MODEL_OUTPUT_INVALID": (502, True),
    "RUBRIC_NOT_FOUND": (404, False),
    "AUTOMATION_UNAVAILABLE": (503, True),
    "EXPORT_NOT_FOUND": (404, False),
    "SCHEMA_VERSION_ERROR": (500, False),
}

ENDPOINT_TABLE_ONLY_CODES: dict[str, tuple[int, bool]] = {
    "FORBIDDEN_PROFILE": (403, False),
    "ASSESSMENT_NOT_FOUND": (404, False),
    "ITEM_NOT_FOUND": (404, False),
    "NO_TASK_DATA": (409, False),
    # T13 added: I3's unknown template id (03 §6 has no row for it yet — registered
    # in the T13 delivery doc as a contract addition).
    "TEMPLATE_NOT_FOUND": (404, False),
}

ALL_CODES = {**SECTION_6_CODES, **ENDPOINT_TABLE_ONLY_CODES}


def test_prefix_is_the_documented_campus_mount_point() -> None:
    assert routes.CAMPUS_PREFIX == "/v1/campus"


def test_code_table_matches_the_documented_contract() -> None:
    assert set(routes.ERROR_SPECS) == set(ALL_CODES)


@pytest.mark.parametrize("code", sorted(ALL_CODES))
def test_each_code_carries_the_documented_status_and_retryability(code: str) -> None:
    spec = routes.ERROR_SPECS[code]
    status, retryable = ALL_CODES[code]
    assert spec.status == status
    assert spec.retryable is retryable


@pytest.mark.parametrize("code", sorted(ALL_CODES))
def test_every_code_has_a_non_empty_fallback_message(code: str) -> None:
    assert routes.ERROR_SPECS[code].message.strip()


def test_retryable_codes_follow_the_five_xx_rule() -> None:
    retryable = {code for code, spec in routes.ERROR_SPECS.items() if spec.retryable}
    assert retryable == {
        "DOC_NOT_READY",
        "MODEL_TIMEOUT",
        "MODEL_OUTPUT_INVALID",
        "AUTOMATION_UNAVAILABLE",
    }


def test_campus_error_builds_the_documented_body() -> None:
    error = routes.campus_error("DOC_NOT_READY")
    assert isinstance(error, HTTPException)
    assert error.status_code == 409
    assert error.detail == {
        "code": "DOC_NOT_READY",
        "message": routes.ERROR_SPECS["DOC_NOT_READY"].message,
        "retryable": True,
    }


def test_campus_error_accepts_a_override_message() -> None:
    error = routes.campus_error("PROFILE_NOT_FOUND", "档案不存在：abc")
    assert error.status_code == 404
    assert error.detail["message"] == "档案不存在：abc"
    assert error.detail["code"] == "PROFILE_NOT_FOUND"
    assert error.detail["retryable"] is False


def test_campus_error_carries_extra_detail_fields() -> None:
    error = routes.campus_error("PARSE_ERROR", "第 3 行无法解析", line=3)
    assert error.detail["line"] == 3
    assert error.detail["code"] == "PARSE_ERROR"


def test_campus_error_status_can_be_overridden() -> None:
    error = routes.campus_error("FORBIDDEN_PROFILE", status=404)
    assert error.status_code == 404
    assert error.detail["code"] == "FORBIDDEN_PROFILE"


def test_raise_campus_error_raises_the_structured_exception() -> None:
    with pytest.raises(HTTPException) as caught:
        routes.raise_campus_error("PROFILE_REQUIRED")
    assert caught.value.status_code == 400
    assert caught.value.detail["code"] == "PROFILE_REQUIRED"
    assert caught.value.detail["retryable"] is False


def test_an_unknown_code_fails_loudly_instead_of_inventing_a_status() -> None:
    with pytest.raises(KeyError):
        routes.campus_error("NOT_A_REAL_CODE")
