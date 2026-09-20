import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { CampusApiError } from "../../../campus/api";
import type { Assessment, AssessmentFinishResult } from "../../../campus/types";

vi.mock("../../../campus/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../../campus/api")>();
  return {
    ...actual,
    createAssessment: vi.fn(),
    getAssessment: vi.fn(),
    patchAssessment: vi.fn(),
    finishAssessment: vi.fn(),
  };
});

import * as api from "../../../campus/api";
import { AssessmentFlow } from "./AssessmentFlow";

const apiMock = api as unknown as Record<string, ReturnType<typeof vi.fn>>;

afterEach(cleanup);

const option = (key: string, text: string) => ({ key, text });

const draftAssessment = (): Assessment => ({
  id: "a1",
  profile_id: "p1",
  started_at: "2026-09-16T00:00:00Z",
  status: "draft",
  question_ids: ["q1", "q2", "q3"],
  answers: {},
  scores: null,
  finished_at: null,
  questions: [
    {
      id: "q1",
      subject: "listening",
      stem: "What does the woman mean?",
      qtype: "single",
      options: [option("A", "She agrees"), option("B", "She refuses")],
    },
    {
      id: "q2",
      subject: "vocab",
      stem: "The word ___ means abundant.",
      qtype: "blank",
      options: null,
    },
    {
      id: "q3",
      subject: "writing",
      stem: "Write one sentence about the chart.",
      qtype: "short_answer",
      options: null,
    },
  ],
});

const finishedAssessment = (): Assessment => ({
  ...draftAssessment(),
  status: "finished",
  answers: { q1: "A", q2: "plenty", q3: "The chart shows a rise." },
  scores: {
    listening: 100,
    reading: 90,
    writing_translation: 80,
    estimate_total: 540,
  },
  finished_at: "2026-09-16T01:00:00Z",
});

const finishResult = (): AssessmentFinishResult => ({
  scores: { listening: 96.4, reading: 106.5, writing_translation: 85.5, estimate_total: 288.4 },
  estimate_total: 288.4,
  gap_table: [
    { section: "listening", current: 96.4, target: 107.5, gap: 11.1 },
    { section: "reading", current: 106.5, target: 178.9, gap: 72.4 },
    { section: "writing_translation", current: 85.5, target: 138.6, gap: 53.1 },
  ],
});

const draftKey = "stealth_study.campus.cet.assessment.p1";

describe("AssessmentFlow", () => {
  beforeEach(() => {
    apiMock.createAssessment.mockReset();
    apiMock.getAssessment.mockReset();
    apiMock.patchAssessment.mockReset();
    apiMock.finishAssessment.mockReset();
    window.localStorage.clear();
  });

  it("offers the start action when no draft is remembered", () => {
    render(<AssessmentFlow profileId="p1" />);
    expect(screen.getByTestId("campus-cet-assessment-start")).toBeTruthy();
    expect(apiMock.getAssessment).not.toHaveBeenCalled();
  });

  it("creates the paper on start and renders every question with its shape", async () => {
    apiMock.createAssessment.mockResolvedValue(draftAssessment());
    render(<AssessmentFlow profileId="p1" />);

    fireEvent.click(screen.getByTestId("campus-cet-assessment-start"));
    await waitFor(() =>
      expect(screen.getAllByTestId("campus-cet-assessment-question")).toHaveLength(3),
    );
    expect(apiMock.createAssessment).toHaveBeenCalledWith("p1");
    expect(window.localStorage.getItem(draftKey)).toBe("a1");
    expect(screen.getAllByTestId("campus-cet-assessment-option")).toHaveLength(2);
    expect(screen.getByTestId("campus-cet-assessment-blank")).toBeTruthy();
    expect(screen.getByTestId("campus-cet-assessment-text")).toBeTruthy();
  });

  it("autosaves answers through the incremental patch", async () => {
    apiMock.getAssessment.mockResolvedValue(draftAssessment());
    apiMock.patchAssessment.mockResolvedValue(draftAssessment());
    window.localStorage.setItem(draftKey, "a1");
    render(<AssessmentFlow profileId="p1" />);

    await waitFor(() => expect(screen.getByTestId("campus-cet-assessment-paper")).toBeTruthy());
    fireEvent.click(screen.getAllByTestId("campus-cet-assessment-option")[0]);
    await waitFor(() =>
      expect(apiMock.patchAssessment).toHaveBeenCalledWith("a1", "p1", { q1: "A" }),
    );
  });

  it("resumes a remembered draft with prior answers filled in", async () => {
    const resumed = {
      ...draftAssessment(),
      answers: { q1: "A", q2: "plenty" },
    };
    apiMock.getAssessment.mockResolvedValue(resumed);
    window.localStorage.setItem(draftKey, "a1");
    render(<AssessmentFlow profileId="p1" />);

    await waitFor(() => expect(screen.getByTestId("campus-cet-assessment-paper")).toBeTruthy());
    const progress = screen.getByTestId("campus-cet-assessment-progress");
    expect(progress.getAttribute("data-answered")).toBe("2");
    expect(progress.getAttribute("data-total")).toBe("3");
    const targets = screen.getAllByTestId("campus-cet-assessment-question").filter(
      (el) => el.getAttribute("data-resume-target") === "true",
    );
    expect(targets).toHaveLength(1);
    expect(targets[0].getAttribute("data-qid")).toBe("q3");
    expect((screen.getByTestId("campus-cet-assessment-blank") as HTMLInputElement).value).toBe(
      "plenty",
    );
  });

  it("falls back to the start screen when the remembered draft is gone", async () => {
    apiMock.getAssessment.mockRejectedValue(
      new CampusApiError("ASSESSMENT_NOT_FOUND", "gone", false, 404),
    );
    window.localStorage.setItem(draftKey, "a1");
    render(<AssessmentFlow profileId="p1" />);

    await waitFor(() => expect(screen.getByTestId("campus-cet-assessment-start")).toBeTruthy());
    expect(window.localStorage.getItem(draftKey)).toBeNull();
  });

  it("finishes the paper and shows the folded scores and gap table", async () => {
    apiMock.getAssessment.mockResolvedValue(draftAssessment());
    apiMock.finishAssessment.mockResolvedValue(finishResult());
    window.localStorage.setItem(draftKey, "a1");
    render(<AssessmentFlow profileId="p1" />);

    await waitFor(() => expect(screen.getByTestId("campus-cet-assessment-finish")).toBeTruthy());
    fireEvent.click(screen.getByTestId("campus-cet-assessment-finish"));

    await waitFor(() => expect(screen.getByTestId("campus-cet-assessment-result")).toBeTruthy());
    expect(apiMock.finishAssessment).toHaveBeenCalledWith("p1", "a1");
    expect(screen.getByTestId("campus-cet-assessment-estimate").textContent).toContain("288.4");
    const gaps = screen.getAllByTestId("campus-cet-assessment-gap");
    expect(gaps).toHaveLength(3);
    expect(gaps[0].getAttribute("data-section")).toBe("listening");
    expect(gaps[0].getAttribute("data-gap")).toBe("11.1");
    expect(window.localStorage.getItem(draftKey)).toBeNull();
  });

  it("shows the stored scores when the loaded assessment is already finished", async () => {
    apiMock.getAssessment.mockResolvedValue(finishedAssessment());
    window.localStorage.setItem(draftKey, "a1");
    render(<AssessmentFlow profileId="p1" />);

    await waitFor(() => expect(screen.getByTestId("campus-cet-assessment-result")).toBeTruthy());
    expect(apiMock.finishAssessment).not.toHaveBeenCalled();
    expect(screen.getByTestId("campus-cet-assessment-estimate").textContent).toContain("540");
  });

  it("surfaces the model-required error when the start fails", async () => {
    apiMock.createAssessment.mockRejectedValue(
      new CampusApiError("MODEL_NOT_CONFIGURED", "no model", false, 409),
    );
    render(<AssessmentFlow profileId="p1" />);
    fireEvent.click(screen.getByTestId("campus-cet-assessment-start"));

    await waitFor(() => expect(screen.getByTestId("campus-cet-assessment-error")).toBeTruthy());
    expect(screen.queryByTestId("campus-cet-assessment-paper")).toBeNull();
  });

  it("keeps the paper usable when a question lost its payload", async () => {
    const partial = draftAssessment();
    const baseQuestions = partial.questions ?? [];
    partial.questions = [{ id: "q1" }, baseQuestions[1], baseQuestions[2]];
    apiMock.getAssessment.mockResolvedValue(partial);
    window.localStorage.setItem(draftKey, "a1");
    render(<AssessmentFlow profileId="p1" />);

    await waitFor(() => expect(screen.getByTestId("campus-cet-assessment-paper")).toBeTruthy());
    expect(screen.getByTestId("campus-cet-assessment-question-missing")).toBeTruthy();
    expect(screen.getAllByTestId("campus-cet-assessment-question")).toHaveLength(3);
  });

  it("reports the finish failure and lets the user retry", async () => {
    apiMock.getAssessment.mockResolvedValue(draftAssessment());
    apiMock.finishAssessment.mockRejectedValue(
      new CampusApiError("MODEL_TIMEOUT", "timeout", true, 504),
    );
    window.localStorage.setItem(draftKey, "a1");
    render(<AssessmentFlow profileId="p1" />);

    await waitFor(() => expect(screen.getByTestId("campus-cet-assessment-finish")).toBeTruthy());
    fireEvent.click(screen.getByTestId("campus-cet-assessment-finish"));
    await waitFor(() => expect(screen.getByTestId("campus-cet-assessment-error")).toBeTruthy());
    expect(screen.getByTestId("campus-cet-assessment-finish")).toBeTruthy();
  });
});
