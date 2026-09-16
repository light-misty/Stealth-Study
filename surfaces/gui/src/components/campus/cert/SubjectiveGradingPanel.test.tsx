import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { CampusApiError } from "../../../campus/api";
import type { GradeResult } from "../../../campus/types";

vi.mock("../../../campus/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../../campus/api")>();
  return {
    ...actual,
    submitGrading: vi.fn(),
  };
});

import * as api from "../../../campus/api";
import { SubjectiveGradingPanel } from "./SubjectiveGradingPanel";

const apiMock = api as unknown as Record<string, ReturnType<typeof vi.fn>>;

afterEach(cleanup);

const result = (over: Partial<GradeResult> = {}): GradeResult => ({
  attempt_id: "a1",
  degrade_level: 0,
  rubric: "default",
  dimensions: [
    { name: "point-a", score: 1, max: 1, comment: "ok" },
    { name: "point-b", score: 0.5, max: 1, comment: "half" },
    { name: "point-c", score: 0, max: 1, comment: "no" },
  ],
  errors: [],
  model_answer_outline: "outline",
  model_used: "gpt",
  notice: null,
  ...over,
});

const fill = () => {
  fireEvent.change(screen.getByTestId("campus-cert-grading-answer"), {
    target: { value: "my answer" },
  });
};

const submit = () => fireEvent.click(screen.getByTestId("campus-cert-grading-submit"));

const kindOf = (kind: string) => {
  const el = screen
    .getAllByTestId("campus-cert-grading-kind")
    .find((k) => k.getAttribute("data-kind") === kind);
  if (!el) throw new Error(`kind ${kind} not found`);
  return el;
};

describe("SubjectiveGradingPanel", () => {
  beforeEach(() => {
    apiMock.submitGrading.mockReset();
  });

  it("offers the four scoring kinds and marks the chosen one", () => {
    render(<SubjectiveGradingPanel profileId="p1" />);
    expect(screen.getAllByTestId("campus-cert-grading-kind")).toHaveLength(4);

    expect(kindOf("short_answer").getAttribute("data-active")).toBe("true");
    fireEvent.click(kindOf("lesson_plan"));
    expect(kindOf("lesson_plan").getAttribute("data-active")).toBe("true");
    expect(kindOf("short_answer").getAttribute("data-active")).toBe("false");
  });

  it("submits the answer with kind and custom rubric through C1", async () => {
    apiMock.submitGrading.mockResolvedValue(result());
    render(<SubjectiveGradingPanel profileId="p1" />);
    fill();
    fireEvent.change(screen.getByTestId("campus-cert-grading-rubric"), {
      target: { value: "focus on structure" },
    });
    submit();

    await waitFor(() =>
      expect(apiMock.submitGrading).toHaveBeenCalledWith({
        profileId: "p1",
        kind: "short_answer",
        answer: "my answer",
        customRubric: "focus on structure",
      }),
    );
    await waitFor(() => expect(screen.getByTestId("campus-grading-result")).toBeTruthy());
  });

  it("renders the three scoring-point states from the dimensions", async () => {
    apiMock.submitGrading.mockResolvedValue(result());
    render(<SubjectiveGradingPanel profileId="p1" />);
    fill();
    submit();

    await waitFor(() => expect(screen.getAllByTestId("campus-cert-grading-state")).toHaveLength(3));
    const states = screen.getAllByTestId("campus-cert-grading-state");
    expect(states.map((s) => s.getAttribute("data-state"))).toEqual(["hit", "partial", "miss"]);
    expect(states.map((s) => s.getAttribute("data-name"))).toEqual(["point-a", "point-b", "point-c"]);
  });

  it("rejects a blank answer without calling C1", () => {
    render(<SubjectiveGradingPanel profileId="p1" />);
    submit();

    expect(apiMock.submitGrading).not.toHaveBeenCalled();
    expect(screen.getByTestId("campus-cert-grading-error")).toBeTruthy();
  });

  it("keeps the form and shows the error when C1 fails", async () => {
    apiMock.submitGrading.mockRejectedValue(new CampusApiError("ILLEGAL_TRANSITION", "nope", false, 409));
    render(<SubjectiveGradingPanel profileId="p1" />);
    fill();
    submit();

    await waitFor(() => expect(screen.getByTestId("campus-cert-grading-error")).toBeTruthy());
    expect(screen.queryByTestId("campus-grading-result")).toBeNull();
    expect(screen.queryByTestId("campus-cert-grading-retry")).toBeNull();
    expect((screen.getByTestId("campus-cert-grading-answer") as HTMLTextAreaElement).value).toBe("my answer");
  });

  it("offers a retry for a retryable failure and resubmits", async () => {
    apiMock.submitGrading
      .mockRejectedValueOnce(new CampusApiError("MODEL_TIMEOUT", "timed out", true, 504))
      .mockResolvedValueOnce(result());
    render(<SubjectiveGradingPanel profileId="p1" />);
    fill();
    submit();

    await waitFor(() => expect(screen.getByTestId("campus-cert-grading-retry")).toBeTruthy());
    fireEvent.click(screen.getByTestId("campus-cert-grading-retry"));

    await waitFor(() => expect(apiMock.submitGrading).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(screen.getByTestId("campus-grading-result")).toBeTruthy());
  });

  it("shows loading and disables the submit while grading", async () => {
    apiMock.submitGrading.mockImplementation(() => new Promise(() => undefined));
    render(<SubjectiveGradingPanel profileId="p1" />);
    fill();
    submit();

    await waitFor(() => expect(screen.getByTestId("campus-cert-grading-loading")).toBeTruthy());
    expect((screen.getByTestId("campus-cert-grading-submit") as HTMLButtonElement).disabled).toBe(true);
  });

  it("guards against double submission", async () => {
    const resolvers: ((value: GradeResult) => void)[] = [];
    apiMock.submitGrading.mockImplementation(
      () => new Promise<GradeResult>((resolve) => resolvers.push(resolve)),
    );
    render(<SubjectiveGradingPanel profileId="p1" />);
    fill();
    submit();
    submit();

    await waitFor(() => expect(apiMock.submitGrading).toHaveBeenCalledTimes(1));
    resolvers[0](result());
    await waitFor(() => expect(screen.getByTestId("campus-grading-result")).toBeTruthy());
  });

  it("switching the kind changes what C1 receives without a rubric", async () => {
    apiMock.submitGrading.mockResolvedValue(result());
    render(<SubjectiveGradingPanel profileId="p1" />);
    fireEvent.click(kindOf("essay_material"));
    fill();
    submit();

    await waitFor(() =>
      expect(apiMock.submitGrading).toHaveBeenCalledWith({
        profileId: "p1",
        kind: "essay_material",
        answer: "my answer",
        customRubric: undefined,
      }),
    );
  });
});
