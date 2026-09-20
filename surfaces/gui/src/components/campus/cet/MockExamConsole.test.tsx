import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { MockExamView, MockSubmitResult } from "../../../campus/types";

vi.mock("../../../campus/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../../campus/api")>();
  return {
    ...actual,
    createMockExam: vi.fn(),
    getMockExam: vi.fn(),
    advanceMockStage: vi.fn(),
    pauseMockExam: vi.fn(),
    submitMockExam: vi.fn(),
  };
});

import * as api from "../../../campus/api";
import { MockExamConsole } from "./MockExamConsole";

const apiMock = api as unknown as Record<string, ReturnType<typeof vi.fn>>;

afterEach(cleanup);

const draftKey = "stealth_study.campus.cet.mock.p1";

const mockView = (overrides: Partial<MockExamView> = {}): MockExamView => ({
  id: "m1",
  profile_id: "p1",
  paper_title: "CET mock paper",
  started_at: "2026-09-16T00:00:00Z",
  current_stage: "writing",
  stage_deadline: "2026-09-16T00:30:00Z",
  paused_seconds: 0,
  locked_stages: [],
  status: "ongoing",
  estimate_score: null,
  created_at: "2026-09-16T00:00:00Z",
  updated_at: "2026-09-16T00:00:00Z",
  remaining_seconds: 1500,
  stage_expired: false,
  server_now: "2026-09-16T00:01:00Z",
  ...overrides,
});

const submitResult = (): MockSubmitResult => ({
  estimate_score: 512.5,
  by_section: {
    listening: { earned: 96.5, max: 248.5, ratio: 0.39 },
    reading: { earned: 180, max: 355, ratio: 0.51 },
  },
  attempt_ids: ["at1", "at2"],
});

describe("MockExamConsole", () => {
  beforeEach(() => {
    for (const key of [
      "createMockExam",
      "getMockExam",
      "advanceMockStage",
      "pauseMockExam",
      "submitMockExam",
    ]) {
      apiMock[key].mockReset();
    }
    vi.restoreAllMocks();
    window.localStorage.clear();
  });

  it("starts a mock exam and opens the writing stage", async () => {
    apiMock.createMockExam.mockResolvedValue(mockView());
    apiMock.getMockExam.mockResolvedValue(mockView());
    render(<MockExamConsole profileId="p1" />);

    fireEvent.click(screen.getByTestId("campus-mock-start"));
    await waitFor(() => expect(screen.getByTestId("campus-mock-console")).toBeTruthy());
    expect(apiMock.createMockExam).toHaveBeenCalledWith("p1", "CET mock paper");
    expect(window.localStorage.getItem(draftKey)).toBe("m1");
    expect(screen.getByTestId("campus-mock-stage").getAttribute("data-stage")).toBe("writing");
    const essay = screen.getByTestId("campus-mock-essay") as HTMLTextAreaElement;
    expect(essay.disabled).toBe(false);
  });

  it("resumes the running exam with the server-derived remaining time", async () => {
    apiMock.getMockExam.mockResolvedValue(mockView());
    window.localStorage.setItem(draftKey, "m1");
    render(<MockExamConsole profileId="p1" />);

    await waitFor(() => expect(screen.getByTestId("campus-mock-console")).toBeTruthy());
    expect(screen.getByTestId("campus-mock-timer").getAttribute("data-remaining")).toBe("1500");
    expect(apiMock.createMockExam).not.toHaveBeenCalled();
  });

  it("reports the paused seconds when the clock resumes", async () => {
    const nowSpy = vi.spyOn(Date, "now").mockReturnValue(1_000_000);
    apiMock.getMockExam.mockResolvedValue(mockView());
    apiMock.pauseMockExam.mockResolvedValue(mockView());
    window.localStorage.setItem(draftKey, "m1");
    render(<MockExamConsole profileId="p1" />);

    await waitFor(() => expect(screen.getByTestId("campus-mock-console")).toBeTruthy());
    fireEvent.click(screen.getByTestId("campus-mock-pause"));
    nowSpy.mockReturnValue(1_006_000);
    fireEvent.click(screen.getByTestId("campus-mock-resume"));
    await waitFor(() =>
      expect(apiMock.pauseMockExam).toHaveBeenCalledWith("p1", "m1", 6),
    );
  });

  it("fast-forwards the stage clock and unlocks the advance action", async () => {
    apiMock.getMockExam.mockResolvedValue(mockView());
    window.localStorage.setItem(draftKey, "m1");
    render(<MockExamConsole profileId="p1" />);

    await waitFor(() => expect(screen.getByTestId("campus-mock-console")).toBeTruthy());
    expect(screen.queryByTestId("campus-mock-advance")).toBeNull();
    fireEvent.click(screen.getByTestId("fast-forward-hook"));
    expect(screen.getByTestId("campus-mock-timer").getAttribute("data-remaining")).toBe("0");
    expect(screen.getByTestId("campus-mock-advance")).toBeTruthy();
  });

  it("advances to listening and locks the writing answer", async () => {
    apiMock.getMockExam.mockResolvedValueOnce(mockView());
    apiMock.advanceMockStage.mockResolvedValue(mockView());
    apiMock.getMockExam.mockResolvedValueOnce(
      mockView({
        current_stage: "listening",
        locked_stages: ["writing"],
        remaining_seconds: 1400,
        stage_deadline: "2026-09-16T01:00:00Z",
      }),
    );
    window.localStorage.setItem(draftKey, "m1");
    render(<MockExamConsole profileId="p1" />);

    await waitFor(() => expect(screen.getByTestId("campus-mock-console")).toBeTruthy());
    fireEvent.click(screen.getByTestId("fast-forward-hook"));
    fireEvent.click(screen.getByTestId("campus-mock-advance"));

    await waitFor(() =>
      expect(screen.getByTestId("campus-mock-stage").getAttribute("data-stage")).toBe(
        "listening",
      ),
    );
    expect(apiMock.advanceMockStage).toHaveBeenCalledWith("p1", "m1", "listening");
    expect(
      (screen.getByTestId("campus-mock-essay") as HTMLTextAreaElement).disabled,
    ).toBe(true);
    expect(
      (screen.getByTestId("campus-mock-listening") as HTMLTextAreaElement).disabled,
    ).toBe(false);
  });

  it("submits the paper from the last stage and shows the estimate", async () => {
    apiMock.getMockExam.mockResolvedValueOnce(
      mockView({ current_stage: "reading_translation", locked_stages: ["writing", "listening"] }),
    );
    apiMock.submitMockExam.mockResolvedValue(submitResult());
    window.localStorage.setItem(draftKey, "m1");
    render(<MockExamConsole profileId="p1" />);

    await waitFor(() => expect(screen.getByTestId("campus-mock-console")).toBeTruthy());
    fireEvent.click(screen.getByTestId("fast-forward-hook"));
    fireEvent.click(screen.getByTestId("campus-mock-submit"));

    await waitFor(() => expect(screen.getByTestId("campus-mock-result")).toBeTruthy());
    expect(apiMock.submitMockExam).toHaveBeenCalledWith("p1", "m1");
    expect(screen.getByTestId("campus-mock-estimate").textContent).toContain("512.5");
    expect(window.localStorage.getItem(draftKey)).toBeNull();
    expect(
      (screen.getByTestId("campus-mock-essay") as HTMLTextAreaElement).disabled,
    ).toBe(true);
    expect(
      (screen.getByTestId("campus-mock-listening") as HTMLTextAreaElement).disabled,
    ).toBe(true);
  });

  it("shows the stored estimate when the exam is already submitted", async () => {
    apiMock.getMockExam.mockResolvedValue(
      mockView({
        status: "submitted",
        locked_stages: ["writing", "listening", "reading_translation"],
        estimate_score: 540,
      }),
    );
    window.localStorage.setItem(draftKey, "m1");
    render(<MockExamConsole profileId="p1" />);

    await waitFor(() => expect(screen.getByTestId("campus-mock-result")).toBeTruthy());
    expect(screen.getByTestId("campus-mock-estimate").textContent).toContain("540");
    expect(apiMock.submitMockExam).not.toHaveBeenCalled();
    expect(
      (screen.getByTestId("campus-mock-reading") as HTMLTextAreaElement).disabled,
    ).toBe(true);
  });

  it("persists the stage draft across reloads", async () => {
    apiMock.getMockExam.mockResolvedValue(mockView());
    window.localStorage.setItem(draftKey, "m1");
    const view = render(<MockExamConsole profileId="p1" />);
    await waitFor(() => expect(screen.getByTestId("campus-mock-console")).toBeTruthy());

    fireEvent.change(screen.getByTestId("campus-mock-essay"), {
      target: { value: "My writing draft." },
    });
    view.unmount();

    apiMock.getMockExam.mockResolvedValue(mockView());
    render(<MockExamConsole profileId="p1" />);
    await waitFor(() => expect(screen.getByTestId("campus-mock-console")).toBeTruthy());
    expect((screen.getByTestId("campus-mock-essay") as HTMLTextAreaElement).value).toBe(
      "My writing draft.",
    );
  });

  it("falls back to the start screen when the remembered exam is gone", async () => {
    apiMock.getMockExam.mockRejectedValue(new Error("gone"));
    window.localStorage.setItem(draftKey, "m1");
    render(<MockExamConsole profileId="p1" />);

    await waitFor(() => expect(screen.getByTestId("campus-mock-start")).toBeTruthy());
    expect(window.localStorage.getItem(draftKey)).toBeNull();
  });

  it("surfaces the start failure with the model-required error", async () => {
    apiMock.createMockExam.mockRejectedValue(new Error("no model"));
    render(<MockExamConsole profileId="p1" />);
    fireEvent.click(screen.getByTestId("campus-mock-start"));

    await waitFor(() => expect(screen.getByTestId("campus-mock-error")).toBeTruthy());
    expect(screen.queryByTestId("campus-mock-console")).toBeNull();
  });
});
