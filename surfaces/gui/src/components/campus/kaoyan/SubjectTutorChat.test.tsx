import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { GradeResult } from "../../../campus/types";

vi.mock("../../../campus/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../../campus/api")>();
  return { ...actual, submitGrading: vi.fn() };
});

import * as api from "../../../campus/api";
import { SubjectTutorChat } from "./SubjectTutorChat";

const apiMock = api as unknown as Record<string, ReturnType<typeof vi.fn>>;

afterEach(cleanup);

const result: GradeResult = {
  attempt_id: "a1",
  degrade_level: 0,
  rubric: "kaoyan-default",
  dimensions: [{ name: "Content", score: 8, max: 10, comment: "on topic" }],
  errors: [],
  model_answer_outline: "outline",
  model_used: "gpt-test",
  notice: null,
};

beforeEach(() => {
  apiMock.submitGrading.mockReset();
});

describe("SubjectTutorChat", () => {
  it("follows the subject-to-kind default mapping when switching subjects", () => {
    render(<SubjectTutorChat profileId="p1" />);

    const kind = screen.getByTestId("campus-tutor-kind") as HTMLSelectElement;
    expect(kind.value).toBe("essay_material");

    fireEvent.change(screen.getByTestId("campus-tutor-subject"), { target: { value: "english" } });
    expect(kind.value).toBe("essay");

    fireEvent.change(screen.getByTestId("campus-tutor-subject"), { target: { value: "math" } });
    expect(kind.value).toBe("short_answer");

    fireEvent.change(screen.getByTestId("campus-tutor-subject"), { target: { value: "major" } });
    expect(kind.value).toBe("short_answer");
  });

  it("offers exactly four grading kinds", () => {
    render(<SubjectTutorChat profileId="p1" />);
    const options = (screen.getByTestId("campus-tutor-kind") as HTMLSelectElement).options;
    expect(options.length).toBe(4);
  });

  it("keeps the submit disabled until there is an answer", () => {
    render(<SubjectTutorChat profileId="p1" />);
    expect((screen.getByTestId("campus-tutor-submit") as HTMLButtonElement).disabled).toBe(true);

    fireEvent.change(screen.getByTestId("campus-tutor-answer"), { target: { value: "my answer" } });
    expect((screen.getByTestId("campus-tutor-submit") as HTMLButtonElement).disabled).toBe(false);
  });

  it("submits grading without any stem field and renders the shared result card", async () => {
    apiMock.submitGrading.mockResolvedValue(result);
    render(<SubjectTutorChat profileId="p1" />);

    fireEvent.change(screen.getByTestId("campus-tutor-answer"), { target: { value: "my answer" } });
    fireEvent.click(screen.getByTestId("campus-tutor-submit"));

    await waitFor(() => expect(screen.getByTestId("campus-grading-result")).toBeTruthy());
    expect(apiMock.submitGrading).toHaveBeenCalledWith({
      profileId: "p1",
      kind: "essay_material",
      answer: "my answer",
    });
    const payload = apiMock.submitGrading.mock.calls[0][0] as Record<string, unknown>;
    expect("stem" in payload).toBe(false);
    expect("questionStem" in payload).toBe(false);
  });

  it("locks the submit while a request is in flight", async () => {
    let release: (value: GradeResult) => void = () => {};
    apiMock.submitGrading.mockReturnValue(
      new Promise<GradeResult>((resolve) => {
        release = resolve;
      }),
    );
    render(<SubjectTutorChat profileId="p1" />);

    fireEvent.change(screen.getByTestId("campus-tutor-answer"), { target: { value: "my answer" } });
    fireEvent.click(screen.getByTestId("campus-tutor-submit"));
    expect((screen.getByTestId("campus-tutor-submit") as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByTestId("campus-tutor-submit"));
    expect(apiMock.submitGrading).toHaveBeenCalledTimes(1);

    release(result);
    await waitFor(() =>
      expect((screen.getByTestId("campus-tutor-submit") as HTMLButtonElement).disabled).toBe(false),
    );
  });

  it("shows the grading error and no result card when the backend rejects", async () => {
    apiMock.submitGrading.mockRejectedValue(new Error("model not configured"));
    render(<SubjectTutorChat profileId="p1" />);

    fireEvent.change(screen.getByTestId("campus-tutor-answer"), { target: { value: "my answer" } });
    fireEvent.click(screen.getByTestId("campus-tutor-submit"));

    await waitFor(() => expect(screen.getByTestId("campus-tutor-error")).toBeTruthy());
    expect(screen.queryByTestId("campus-grading-result")).toBeNull();
  });
});
