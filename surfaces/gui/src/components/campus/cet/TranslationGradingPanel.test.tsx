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
import { TranslationGradingPanel } from "./TranslationGradingPanel";

const apiMock = api as unknown as Record<string, ReturnType<typeof vi.fn>>;

afterEach(cleanup);

describe("TranslationGradingPanel", () => {
  beforeEach(() => {
    for (const key of ["submitGrading", "listGradingHistory", "getAttempt", "getCommonErrors"]) {
      apiMock[key].mockReset();
    }
    apiMock.listGradingHistory.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 10 });
    apiMock.getCommonErrors.mockResolvedValue({ top3: [] });
    apiMock.submitGrading.mockResolvedValue({
      attempt_id: "at1",
      degrade_level: 0,
      rubric: "cet_translation",
      dimensions: [{ name: "fidelity", score: 10, max: 15, comment: "faithful" }],
      errors: [],
      model_answer_outline: "outline",
      model_used: "glm-4",
      notice: null,
    });
  });

  it("renders the translation title and grades with the translation kind", async () => {
    render(<TranslationGradingPanel profileId="p1" />);
    expect(screen.getByText("Translation grading")).toBeTruthy();

    fireEvent.change(screen.getByTestId("campus-cet-translation-grading-text"), {
      target: { value: "My translation." },
    });
    fireEvent.click(screen.getByTestId("campus-cet-translation-grading-submit"));
    await waitFor(() => expect(apiMock.submitGrading).toHaveBeenCalled());
    expect(apiMock.submitGrading).toHaveBeenCalledWith({
      profileId: "p1",
      kind: "translation",
      answer: "My translation.",
    });
    await waitFor(() =>
      expect(screen.getByTestId("campus-cet-translation-grading-result")).toBeTruthy(),
    );
  });
});
