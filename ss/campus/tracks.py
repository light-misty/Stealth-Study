"""Declarative per-station configuration for the three exam-prep stations.

01 §3.2 splits the application into four layers and keeps every station difference inside
this file: `service.py` must never branch on a track id, it reads a `TrackSpec` instead.
Adding a fourth station (the reserved `other` track) means adding one entry to `TRACKS`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

MODULES: frozenset[str] = frozenset(
    {
        "assessment",
        "vocab",
        "grading",
        "mock",
        "plan",
        "subject",
        "library",
        "report",
        "school",
        "knowledge_tree",
        "practice",
        "deadline",
    }
)

TARGET_MODELS: frozenset[str] = frozenset({"score_breakdown", "stage_plan", "coverage"})


@dataclass(frozen=True)
class TrackSpec:
    """One station's declaration: what it shows, who it talks to, how it measures itself."""

    track: str
    i18n_key: str
    modules: tuple[str, ...]
    default_personas: tuple[str, ...]
    subject_skeleton: tuple[str, ...]
    target_model: str


CET_SPEC = TrackSpec(
    track="cet",
    i18n_key="campus.track.cet",
    modules=("assessment", "vocab", "grading", "mock"),
    default_personas=("cet-examiner", "cet-grader"),
    subject_skeleton=("listening", "reading", "writing", "translation"),
    target_model="score_breakdown",
)

KAOYAN_SPEC = TrackSpec(
    track="kaoyan",
    i18n_key="campus.track.kaoyan",
    modules=("plan", "subject", "library", "report", "school", "grading"),
    default_personas=("kaoyan-planner", "kaoyan-subject-tutor"),
    subject_skeleton=("politics", "english", "math", "major"),
    target_model="stage_plan",
)

CERT_SPEC = TrackSpec(
    track="cert",
    i18n_key="campus.track.cert",
    modules=("knowledge_tree", "practice", "grading", "deadline"),
    default_personas=("cert-instructor", "study-companion"),
    subject_skeleton=(),
    target_model="coverage",
)

TRACKS: dict[str, TrackSpec] = {
    CET_SPEC.track: CET_SPEC,
    KAOYAN_SPEC.track: KAOYAN_SPEC,
    CERT_SPEC.track: CERT_SPEC,
}

TRACK_IDS: tuple[str, ...] = tuple(TRACKS)


def spec_for(track_id: str) -> TrackSpec:
    """Look up a station declaration, raising `KeyError` for an unknown track."""
    return TRACKS[track_id]


def default_persona(track_id: str) -> Optional[str]:
    """The persona a new session on this station starts with, if one is declared."""
    personas = spec_for(track_id).default_personas
    return personas[0] if personas else None
