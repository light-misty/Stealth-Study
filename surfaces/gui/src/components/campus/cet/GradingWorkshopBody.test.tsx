import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Attempt, GradeResult } from "../../../campus/types";

vi.mock("../../../campus/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../../campus/api")>();
  return {
    ...actual,
    submitGrading: vi.fn(),
    listGradingHistory: vi.fn(),
    getAttempt: vi.fn(),
    getCommonErrors: vi.fn(),
  };
});

import * as api from "../../../campus/api";
import { GradingWorkshopBody } from "./GradingWorkshopBody";

const apiMock = api as unknown as Record<string, ReturnType<typeof vi.fn>>;

afterEach(cleanup);

const gradeResult = (): GradeResult => ({
  attempt_id: "at1",
  degrade_level: 0,
  rubric: "cet_essay",
  dimensions: [
    { name: "content", score: 9, max: 15, comment: "clear" },
    { name: "language", score: 8, max: 15, comment: "ok" },
  ],
  errors: [{ original: "teached", suggestion: "taught", type: "tense", offset: 12 }],
  model_answer_outline: "State the trend, then reasons.",
  model_used: "glm-4",
  notice: null,
});

const historyAttempt = (id: string, overrides: Partial<Attempt> = {}): Attempt => ({
  id,
  profile_id: "p1",
  track_type: "cet",
  subject: "writing",
  user_answer: "The chart shows...",
  question_id: null,
  session_type: "grading",
  mock_exam_id: null,
  is_correct: null,
  score: 10,
  max_score: 15,
  grading_json: null,
  degrade_level: 0,
  model_used: "glm-4",
  created_at: "2026-09-16T08:00:00Z",
  ...overrides,
});

describe("GradingWorkshopBody", () => {
  beforeEach(() => {
    for (const key of ["submitGrading", "listGradingHistory", "getAttempt", "getCommonErrors"]) {
      apiMock[key].mockReset();
    }
    apiMock.listGradingHistory.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 10 });
    apiMock.getCommonErrors.mockResolvedValue({ top3: [] });
  });

  it("submits the text for grading and shows the four-part card", async () => {
    apiMock.submitGrading.mockResolvedValue(gradeResult());
    apiMock.getCommonErrors.mockResolvedValue({
      top3: [{ type: "tense", count: 4, samples: ["teached"] }],
    });
    render(<GradingWorkshopBody profileId="p1" kind="essay" title="作文批改" desc="分项得分与错误清单" />);

    fireEvent.change(screen.getByTestId("campus-cet-grading-text"), {
      target: { value: "Yesterday he teached us English." },
    });
    fireEvent.click(screen.getByTestId("campus-cet-grading-submit"));

    await waitFor(() => expect(screen.getByTestId("campus-cet-grading-result")).toBeTruthy());
    expect(apiMock.submitGrading).toHaveBeenCalledWith({
      profileId: "p1",
      kind: "essay",
      answer: "Yesterday he teached us English.",
    });
    expect(screen.getAllByTestId("campus-grading-dimension").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByTestId("campus-grading-error").getAttribute("data-offset")).toBe("12");
    expect(screen.getByTestId("campus-grading-outline").textContent).toContain(
      "State the trend",
    );
    expect(screen.getByTestId("campus-cet-common-error").getAttribute("data-type")).toBe("tense");
  });

  it("locates the error inside the submitted text", async () => {
    apiMock.submitGrading.mockResolvedValue(gradeResult());
    render(<GradingWorkshopBody profileId="p1" kind="essay" title="作文批改" desc="分项得分与错误清单" />);

    fireEvent.change(screen.getByTestId("campus-cet-grading-text"), {
      target: { value: "Yesterday he teached us English." },
    });
    fireEvent.click(screen.getByTestId("campus-cet-grading-submit"));
    await waitFor(() => expect(screen.getByTestId("campus-cet-grading-result")).toBeTruthy());
    fireEvent.click(screen.getByTestId("campus-grading-locate"));

    const textarea = screen.getByTestId("campus-cet-grading-text") as HTMLTextAreaElement;
    expect(textarea.selectionStart).toBe(12);
    expect(textarea.selectionEnd).toBe(19);
  });

  it("keeps the submit disabled until the text is non-empty", () => {
    render(<GradingWorkshopBody profileId="p1" kind="essay" title="作文批改" desc="分项得分与错误清单" />);
    expect(
      (screen.getByTestId("campus-cet-grading-submit") as HTMLButtonElement).disabled,
    ).toBe(true);
    fireEvent.change(screen.getByTestId("campus-cet-grading-text"), {
      target: { value: "Something." },
    });
    expect(
      (screen.getByTestId("campus-cet-grading-submit") as HTMLButtonElement).disabled,
    ).toBe(false);
  });

  it("disables the submit while a grading run is pending", async () => {
    let resolveGrading: (v: GradeResult) => void = () => {};
    apiMock.submitGrading.mockReturnValue(
      new Promise<GradeResult>((resolve) => {
        resolveGrading = resolve;
      }),
    );
    render(<GradingWorkshopBody profileId="p1" kind="essay" title="作文批改" desc="分项得分与错误清单" />);

    fireEvent.change(screen.getByTestId("campus-cet-grading-text"), {
      target: { value: "Something." },
    });
    fireEvent.click(screen.getByTestId("campus-cet-grading-submit"));
    await waitFor(() =>
      expect((screen.getByTestId("campus-cet-grading-submit") as HTMLButtonElement).disabled).toBe(
        true,
      ),
    );
    resolveGrading(gradeResult());
    await waitFor(() =>
      expect((screen.getByTestId("campus-cet-grading-submit") as HTMLButtonElement).disabled).toBe(
        false,
      ),
    );
  });

  it("reports grading failures and recovers through retry", async () => {
    apiMock.submitGrading.mockRejectedValueOnce(new Error("no model"));
    apiMock.submitGrading.mockResolvedValue(gradeResult());
    render(<GradingWorkshopBody profileId="p1" kind="essay" title="作文批改" desc="分项得分与错误清单" />);

    fireEvent.change(screen.getByTestId("campus-cet-grading-text"), {
      target: { value: "Something." },
    });
    fireEvent.click(screen.getByTestId("campus-cet-grading-submit"));
    await waitFor(() => expect(screen.getByTestId("campus-cet-grading-error")).toBeTruthy());

    fireEvent.click(screen.getByTestId("campus-cet-grading-retry"));
    await waitFor(() => expect(screen.getByTestId("campus-cet-grading-result")).toBeTruthy());
  });

  it("lists the grading history of the same kind", async () => {
    apiMock.listGradingHistory.mockResolvedValue({
      items: [historyAttempt("h1"), historyAttempt("h2")],
      total: 2,
      page: 1,
      page_size: 10,
    });
    render(<GradingWorkshopBody profileId="p1" kind="translation" title="翻译批改" desc="三档计分" />);

    await waitFor(() =>
      expect(screen.getAllByTestId("campus-cet-grading-history-item")).toHaveLength(2),
    );
    expect(apiMock.listGradingHistory).toHaveBeenCalledWith("p1", {
      kind: "translation",
      page: 1,
      pageSize: 10,
    });
  });

  it("shows the stored detail when a history entry is opened", async () => {
    apiMock.listGradingHistory.mockResolvedValue({
      items: [historyAttempt("h1")],
      total: 1,
      page: 1,
      page_size: 10,
    });
    apiMock.getAttempt.mockResolvedValue(historyAttempt("h1"));
    render(<GradingWorkshopBody profileId="p1" kind="essay" title="作文批改" desc="分项得分与错误清单" />);

    await waitFor(() =>
      expect(screen.getByTestId("campus-cet-grading-history-item")).toBeTruthy(),
    );
    fireEvent.click(screen.getByTestId("campus-cet-grading-history-item"));
    await waitFor(() =>
      expect(screen.getByTestId("campus-cet-grading-history-detail")).toBeTruthy(),
    );
    expect(apiMock.getAttempt).toHaveBeenCalledWith("p1", "h1");
    expect(screen.getByTestId("campus-cet-grading-history-detail").textContent).toContain(
      "The chart shows...",
    );
  });

  it("shows the empty history hint when nothing was graded yet", async () => {
    render(<GradingWorkshopBody profileId="p1" kind="essay" title="作文批改" desc="分项得分与错误清单" />);
    await waitFor(() => expect(screen.getByTestId("campus-cet-grading-history-empty")).toBeTruthy());
  });
});
