import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { AttemptFeedback, QuestionBankItem } from "../../../campus/types";

vi.mock("../../../campus/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../../campus/api")>();
  return {
    ...actual,
    listQuestions: vi.fn(),
    submitAttempt: vi.fn(),
  };
});

import * as api from "../../../campus/api";
import { ListeningDrill } from "./ListeningDrill";

const apiMock = api as unknown as Record<string, ReturnType<typeof vi.fn>>;

afterEach(cleanup);

const option = (key: string, text: string) => ({ key, text });

const question = (id: string, overrides: Partial<QuestionBankItem> = {}): QuestionBankItem => ({
  id,
  profile_id: "p1",
  subject: "listening",
  stem: `Stem ${id}`,
  qtype: "single",
  point_id: null,
  options: [option("A", "opt A"), option("B", "opt B")],
  answer: "A",
  answer_meta: null,
  max_score: 5,
  difficulty: null,
  source: "manual",
  doc_id: null,
  created_at: "2026-09-16T00:00:00Z",
  ...overrides,
});

const attempt = (qid: string, overrides: Partial<AttemptFeedback> = {}): AttemptFeedback => ({
  id: `at-${qid}`,
  profile_id: "p1",
  track_type: "cet",
  subject: "listening",
  user_answer: "A",
  question_id: qid,
  session_type: "practice",
  mock_exam_id: null,
  is_correct: 1,
  score: 5,
  max_score: 5,
  grading_json: null,
  degrade_level: null,
  model_used: null,
  created_at: "2026-09-16T00:00:00Z",
  pending_grading: false,
  standard_answer: "A",
  ...overrides,
});

describe("ListeningDrill", () => {
  beforeEach(() => {
    apiMock.listQuestions.mockReset();
    apiMock.submitAttempt.mockReset();
  });

  it("loads listening questions from the bank and shows the first one", async () => {
    apiMock.listQuestions.mockResolvedValue({
      items: [question("q1"), question("q2")],
      total: 2,
      page: 1,
      page_size: 50,
    });
    render(<ListeningDrill profileId="p1" />);

    await waitFor(() => expect(screen.getByTestId("campus-cet-listening-question")).toBeTruthy());
    expect(apiMock.listQuestions).toHaveBeenCalledWith("p1", { subject: "listening" });
    expect(screen.getByTestId("campus-cet-listening-question").textContent).toContain("Stem q1");
  });

  it("shows the empty state when the bank has no listening questions", async () => {
    apiMock.listQuestions.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 50 });
    render(<ListeningDrill profileId="p1" />);

    await waitFor(() => expect(screen.getByTestId("campus-cet-listening-empty")).toBeTruthy());
  });

  it("reports load failures and recovers through retry", async () => {
    apiMock.listQuestions.mockRejectedValueOnce(new Error("down"));
    apiMock.listQuestions.mockResolvedValue({
      items: [question("q1")],
      total: 1,
      page: 1,
      page_size: 50,
    });
    render(<ListeningDrill profileId="p1" />);

    await waitFor(() => expect(screen.getByTestId("campus-cet-listening-error")).toBeTruthy());
    fireEvent.click(screen.getByTestId("campus-cet-listening-retry"));
    await waitFor(() => expect(screen.getByTestId("campus-cet-listening-question")).toBeTruthy());
  });

  it("grades an objective answer instantly with the standard answer", async () => {
    apiMock.listQuestions.mockResolvedValue({
      items: [question("q1")],
      total: 1,
      page: 1,
      page_size: 50,
    });
    apiMock.submitAttempt.mockResolvedValue(attempt("q1", { is_correct: 0, score: 0 }));
    render(<ListeningDrill profileId="p1" />);

    await waitFor(() => expect(screen.getByTestId("campus-cet-listening-question")).toBeTruthy());
    fireEvent.click(screen.getAllByTestId("campus-cet-listening-option")[1]);
    fireEvent.click(screen.getByTestId("campus-cet-listening-submit"));

    await waitFor(() => expect(screen.getByTestId("campus-cet-listening-result")).toBeTruthy());
    expect(apiMock.submitAttempt).toHaveBeenCalledWith({
      profileId: "p1",
      questionId: "q1",
      sessionType: "practice",
      answer: "B",
    });
    expect(screen.getByTestId("campus-cet-listening-correct").getAttribute("data-correct")).toBe(
      "false",
    );
    expect(screen.getByTestId("campus-cet-listening-standard-answer").textContent).toContain("A");
  });

  it("shows the graded score for a subjective answer", async () => {
    apiMock.listQuestions.mockResolvedValue({
      items: [question("q1", { qtype: "short_answer", options: null, answer: null })],
      total: 1,
      page: 1,
      page_size: 50,
    });
    apiMock.submitAttempt.mockResolvedValue(
      attempt("q1", {
        is_correct: null,
        score: 3.5,
        pending_grading: true,
        standard_answer: undefined,
        user_answer: "I heard a rising tone.",
      }),
    );
    render(<ListeningDrill profileId="p1" />);

    await waitFor(() => expect(screen.getByTestId("campus-cet-listening-question")).toBeTruthy());
    fireEvent.change(screen.getByTestId("campus-cet-listening-text"), {
      target: { value: "I heard a rising tone." },
    });
    fireEvent.click(screen.getByTestId("campus-cet-listening-submit"));

    await waitFor(() => expect(screen.getByTestId("campus-cet-listening-result")).toBeTruthy());
    expect(screen.getByTestId("campus-cet-listening-score").textContent).toContain("3.5");
    expect(screen.getByTestId("campus-cet-listening-pending")).toBeTruthy();
  });

  it("reports submit failures and keeps the answer editable", async () => {
    apiMock.listQuestions.mockResolvedValue({
      items: [question("q1")],
      total: 1,
      page: 1,
      page_size: 50,
    });
    apiMock.submitAttempt.mockRejectedValue(new Error("timeout"));
    render(<ListeningDrill profileId="p1" />);

    await waitFor(() => expect(screen.getByTestId("campus-cet-listening-question")).toBeTruthy());
    fireEvent.click(screen.getAllByTestId("campus-cet-listening-option")[0]);
    fireEvent.click(screen.getByTestId("campus-cet-listening-submit"));
    await waitFor(() => expect(screen.getByTestId("campus-cet-listening-error")).toBeTruthy());
    expect(screen.getByTestId("campus-cet-listening-submit")).toBeTruthy();
  });

  it("moves to the next question without the previous feedback", async () => {
    apiMock.listQuestions.mockResolvedValue({
      items: [question("q1"), question("q2")],
      total: 2,
      page: 1,
      page_size: 50,
    });
    apiMock.submitAttempt.mockResolvedValue(attempt("q1"));
    render(<ListeningDrill profileId="p1" />);

    await waitFor(() => expect(screen.getByTestId("campus-cet-listening-question")).toBeTruthy());
    fireEvent.click(screen.getAllByTestId("campus-cet-listening-option")[0]);
    fireEvent.click(screen.getByTestId("campus-cet-listening-submit"));
    await waitFor(() => expect(screen.getByTestId("campus-cet-listening-result")).toBeTruthy());
    fireEvent.click(screen.getByTestId("campus-cet-listening-next"));

    expect(screen.getByTestId("campus-cet-listening-question").textContent).toContain("Stem q2");
    expect(screen.queryByTestId("campus-cet-listening-result")).toBeNull();
    expect(screen.getByTestId("campus-cet-listening-progress").textContent).toContain("2");
  });
});
