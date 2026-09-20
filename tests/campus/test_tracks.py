"""Unit tests for `stealth_study.campus.tracks` — the declarative three-station config (01 §3.2)."""

from __future__ import annotations

import dataclasses

import pytest

from stealth_study.campus import models, tracks

EXPECTED_TRACK_IDS = ("cet", "kaoyan", "cert")


def test_tracks_declare_exactly_the_three_stations() -> None:
    assert tracks.TRACK_IDS == EXPECTED_TRACK_IDS
    assert tuple(tracks.TRACKS) == EXPECTED_TRACK_IDS


def test_track_ids_are_declared_track_types() -> None:
    for track_id in tracks.TRACKS:
        assert models.TrackType.from_value(track_id) is not None


@pytest.mark.parametrize("track_id", EXPECTED_TRACK_IDS)
def test_i18n_key_follows_the_campus_namespace(track_id: str) -> None:
    spec = tracks.TRACKS[track_id]
    assert spec.i18n_key == f"campus.track.{track_id}"
    assert spec.track == track_id


@pytest.mark.parametrize("track_id", EXPECTED_TRACK_IDS)
def test_specs_are_frozen_so_the_declaration_cannot_be_mutated(track_id: str) -> None:
    spec = tracks.TRACKS[track_id]
    assert dataclasses.is_dataclass(spec)
    with pytest.raises(dataclasses.FrozenInstanceError):
        spec.track = "other"


@pytest.mark.parametrize("track_id", EXPECTED_TRACK_IDS)
def test_modules_come_from_the_declared_vocabulary(track_id: str) -> None:
    spec = tracks.TRACKS[track_id]
    assert spec.modules
    assert len(set(spec.modules)) == len(spec.modules)
    assert set(spec.modules) <= tracks.MODULES


@pytest.mark.parametrize("track_id", EXPECTED_TRACK_IDS)
def test_default_personas_are_unique_and_not_empty(track_id: str) -> None:
    personas = tracks.TRACKS[track_id].default_personas
    assert personas
    assert len(set(personas)) == len(personas)
    assert all(persona.strip() == persona and persona for persona in personas)


@pytest.mark.parametrize("track_id", EXPECTED_TRACK_IDS)
def test_subject_skeleton_uses_declared_subject_codes(track_id: str) -> None:
    skeleton = tracks.TRACKS[track_id].subject_skeleton
    assert len(set(skeleton)) == len(skeleton)
    for code in skeleton:
        assert models.Subject.from_value(code)


def test_cert_skeleton_is_empty_because_the_tree_carries_it() -> None:
    assert tracks.TRACKS["cert"].subject_skeleton == ()


def test_each_station_declares_its_own_goal_function() -> None:
    assert {tracks.TRACKS[t].target_model for t in EXPECTED_TRACK_IDS} == {
        "score_breakdown",
        "stage_plan",
        "coverage",
    }


def test_cet_station_matches_the_document_example() -> None:
    spec = tracks.TRACKS["cet"]
    assert spec.modules == ("assessment", "vocab", "grading", "mock")
    assert spec.default_personas == ("cet-examiner", "cet-grader")
    assert spec.subject_skeleton == ("listening", "reading", "writing", "translation")


def test_kaoyan_station_covers_the_four_tracks() -> None:
    spec = tracks.TRACKS["kaoyan"]
    assert spec.subject_skeleton == ("politics", "english", "math", "major")
    assert spec.default_personas == ("kaoyan-planner", "kaoyan-subject-tutor")


def test_spec_for_returns_the_declared_spec() -> None:
    assert tracks.spec_for("kaoyan") is tracks.TRACKS["kaoyan"]


def test_spec_for_rejects_an_unknown_track() -> None:
    with pytest.raises(KeyError):
        tracks.spec_for("other")


def test_missing_goal_function_is_rejected_by_the_vocabulary() -> None:
    assert set(tracks.TARGET_MODELS) == {"score_breakdown", "stage_plan", "coverage"}
    for track_id in EXPECTED_TRACK_IDS:
        assert tracks.TRACKS[track_id].target_model in tracks.TARGET_MODELS
