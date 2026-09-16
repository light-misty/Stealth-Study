import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

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
import { EssayGradingPanel } from "./EssayGradingPanel";

const apiMock = api as unknown as Record<string, ReturnType<typeof vi.fn>>;

afterEach(cleanup);

describe("EssayGradingPanel", () => {
  beforeEach(() => {
    for (const key of ["submitGrading", "listGradingHistory", "getAttempt", "getCommonErrors"]) {
      apiMock[key].mockReset();
    }
    apiMock.listGradingHistory.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 10 });
    apiMock.getCommonErrors.mockResolvedValue({ top3: [] });
    apiMock.submitGrading.mockResolvedValue({
      attempt_id: "at1",
      degrade_level: 0,
      rubric: "cet_essay",
      dimensions: [{ name: "content", score: 9, max: 15, comment: "clear" }],
      errors: [],
      model_answer_outline: "outline",
      model_used: "glm-4",
      notice: null,
    });
  });

  it("renders the essay title and grades with the essay kind", async () => {
    render(<EssayGradingPanel profileId="p1" />);
    expect(screen.getByText("Essay grading")).toBeTruthy();

    fireEvent.change(screen.getByTestId("campus-cet-grading-text"), {
      target: { value: "My essay." },
    });
    fireEvent.click(screen.getByTestId("campus-cet-grading-submit"));
    await waitFor(() => expect(apiMock.submitGrading).toHaveBeenCalled());
    expect(apiMock.submitGrading).toHaveBeenCalledWith({
      profileId: "p1",
      kind: "essay",
      answer: "My essay.",
    });
    await waitFor(() =>
      expect(screen.getByTestId("campus-cet-grading-result")).toBeTruthy(),
    );
  });
});
