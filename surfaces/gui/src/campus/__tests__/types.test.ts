import { describe, expect, it } from "vitest";
import * as types from "../types";

const EXPECTED: Record<string, string[]> = {
  CAMPUS_TRACKS: ["cet", "kaoyan", "cert"],
  PROFILE_TRACK_TYPES: ["cet", "kaoyan", "cert", "other"],
  CERT_TYPES: ["teaching", "ncre", "law", "cpa", "other"],
  CET_LEVELS: ["cet4", "cet6"],
  PROFILE_STATUSES: ["active", "archived", "finished"],
  DEGREE_TYPES: ["academic", "professional"],
  DOC_FILE_TYPES: ["pdf", "md", "txt"],
  PARSE_STATUSES: ["pending", "ready", "failed"],
  KNOWLEDGE_SOURCES: ["manual", "ai_generated", "imported"],
  MASTERY_LEVELS: ["unknown", "fuzzy", "mastered"],
  MASTERY_DIMENSIONS: ["concept", "listening", "reading", "writing", "translation"],
  SUBJECTS: [
    "listening",
    "reading",
    "writing",
    "translation",
    "vocab",
    "politics",
    "english",
    "math",
    "major",
  ],
  PLAN_TRACKS: ["overall", "politics", "english", "math", "major"],
  PLAN_STAGES: ["foundation", "intensive", "pastpaper", "sprint"],
  PLAN_SOURCES: ["ai_generated", "manual"],
  TASK_STATUSES: ["todo", "doing", "review", "done", "skipped"],
  EXAMPLE_SOURCES: ["past_paper", "ai"],
  QUESTION_TYPES: [
    "single",
    "multiple",
    "judge",
    "blank",
    "short_answer",
    "essay",
    "material",
    "lesson_plan",
    "practical",
  ],
  QUESTION_SOURCES: ["manual", "ai", "imported", "past_paper"],
  SESSION_TYPES: ["practice", "mock", "assessment", "grading"],
  ATTRIBUTIONS: [
    "concept_unclear",
    "misread",
    "calculation_or_operation",
    "out_of_scope",
    "time_short",
    "pending",
  ],
  REVIEW_ITEM_TYPES: ["mistake", "vocab", "knowledge_point"],
  REVIEW_STATUSES: ["pending", "done", "dropped"],
  MOCK_STAGES: ["writing", "listening", "reading_translation", "graded"],
  MOCK_STATUSES: ["ongoing", "submitted", "graded", "abandoned"],
  ASSESSMENT_STATUSES: ["draft", "finished"],
  DEADLINE_NODE_TYPES: [
    "registration_open",
    "registration_close",
    "payment_close",
    "admission_ticket",
    "exam",
    "score_query",
  ],
  REVIEW_INTENSITIES: ["light", "standard", "intense"],
  GRADING_KINDS: [
    "essay",
    "translation",
    "short_answer",
    "essay_material",
    "lesson_plan",
    "practical",
  ],
  CAMPUS_TASKS: ["grading", "question", "explain"],
};

describe("campus type contract", () => {
  it("exports every expected enum list", () => {
    const missing = Object.keys(EXPECTED).filter((k) => !(k in types));
    expect(missing).toEqual([]);
  });

  it("runtime enum lists mirror the backend column contract exactly", () => {
    for (const [name, expected] of Object.entries(EXPECTED)) {
      const actual = (types as unknown as Record<string, unknown>)[name];
      expect(Array.isArray(actual), `${name} must be an array`).toBe(true);
      expect(
        [...(actual as readonly string[])],
        `${name} drifted from the backend contract`,
      ).toEqual(expected);
    }
  });
});
