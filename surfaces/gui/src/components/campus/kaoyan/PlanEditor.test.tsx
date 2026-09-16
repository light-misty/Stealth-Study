import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { CampusApiError } from "../../../campus/api";
import type { PlanTask } from "../../../campus/types";

vi.mock("../../../campus/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../../campus/api")>();
  return { ...actual, generatePlan: vi.fn(), reschedulePlan: vi.fn() };
});

import * as api from "../../../campus/api";
import { PlanEditor } from "./PlanEditor";

const apiMock = api as unknown as Record<string, ReturnType<typeof vi.fn>>;

afterEach(cleanup);

const task = (id: string, planId = "plan-1"): PlanTask => ({
  id,
  plan_id: planId,
  profile_id: "p1",
  title: `task-${id}`,
  detail: "",
  subject: "politics",
  scheduled_date: "2026-09-07",
  est_minutes: 60,
  priority: 2,
  status: "todo",
  board_card_id: null,
  completed_at: null,
  created_at: "2026-09-01T00:00:00Z",
  updated_at: "2026-09-01T00:00:00Z",
});

describe("PlanEditor", () => {
  beforeEach(() => {
    apiMock.generatePlan.mockReset();
    apiMock.reschedulePlan.mockReset();
  });

  it("keeps reordering disabled until a plan id is known from the tasks", () => {
    render(<PlanEditor profileId="p1" tasks={[]} />);
    expect((screen.getByTestId("campus-plan-generate") as HTMLButtonElement).disabled).toBe(false);
    expect((screen.getByTestId("campus-plan-reschedule") as HTMLButtonElement).disabled).toBe(true);
  });

  it("enables reordering once the task list carries a plan id", () => {
    render(<PlanEditor profileId="p1" tasks={[task("t1")]} />);
    expect((screen.getByTestId("campus-plan-reschedule") as HTMLButtonElement).disabled).toBe(false);
  });

  it("generates a plan and reports the generation result", async () => {
    apiMock.generatePlan.mockResolvedValue({ plan_id: "plan-1", task_count: 117, first_date: "2026-09-07" });
    const onMutated = vi.fn();
    render(<PlanEditor profileId="p1" tasks={[]} onMutated={onMutated} />);

    fireEvent.click(screen.getByTestId("campus-plan-generate"));
    await waitFor(() => expect(screen.getByTestId("campus-plan-notice")).toBeTruthy());
    expect(apiMock.generatePlan).toHaveBeenCalledWith("p1");
    expect(screen.getByTestId("campus-plan-notice").textContent).toContain("117");
    expect(screen.getByTestId("campus-plan-notice").textContent).toContain("2026-09-07");
    expect(onMutated).toHaveBeenCalledTimes(1);
  });

  it("shows the backend error and skips the refresh when generation fails", async () => {
    apiMock.generatePlan.mockRejectedValue(
      new CampusApiError("EXAM_DATE_REQUIRED", "no exam date", false, 422),
    );
    const onMutated = vi.fn();
    render(<PlanEditor profileId="p1" tasks={[]} onMutated={onMutated} />);

    fireEvent.click(screen.getByTestId("campus-plan-generate"));
    await waitFor(() => expect(screen.getByTestId("campus-plan-error")).toBeTruthy());
    expect(screen.getByTestId("campus-plan-error").textContent).toContain("Set the exam date first");
    expect(onMutated).not.toHaveBeenCalled();
  });

  it("reschedules with the picked exam date", async () => {
    apiMock.reschedulePlan.mockResolvedValue({ rescheduled: 12, preserved_done: 3 });
    const onMutated = vi.fn();
    render(<PlanEditor profileId="p1" tasks={[task("t1")]} onMutated={onMutated} />);

    fireEvent.change(screen.getByTestId("campus-plan-date"), { target: { value: "2027-01-05" } });
    fireEvent.click(screen.getByTestId("campus-plan-reschedule"));
    await waitFor(() => expect(screen.getByTestId("campus-plan-notice")).toBeTruthy());
    expect(apiMock.reschedulePlan).toHaveBeenCalledWith("p1", "plan-1", "2027-01-05");
    expect(screen.getByTestId("campus-plan-notice").textContent).toContain("12");
    expect(screen.getByTestId("campus-plan-notice").textContent).toContain("3");
    expect(onMutated).toHaveBeenCalledTimes(1);
  });

  it("reschedules without a new date so the backend falls back to the profile", async () => {
    apiMock.reschedulePlan.mockResolvedValue({ rescheduled: 1, preserved_done: 0 });
    render(<PlanEditor profileId="p1" tasks={[task("t1")]} />);

    fireEvent.click(screen.getByTestId("campus-plan-reschedule"));
    await waitFor(() => expect(apiMock.reschedulePlan).toHaveBeenCalled());
    expect(apiMock.reschedulePlan).toHaveBeenCalledWith("p1", "plan-1", undefined);
  });

  it("locks both actions while a request is in flight", async () => {
    let release: (value: unknown) => void = () => {};
    apiMock.generatePlan.mockReturnValue(
      new Promise((resolve) => {
        release = resolve;
      }),
    );
    render(<PlanEditor profileId="p1" tasks={[task("t1")]} />);

    fireEvent.click(screen.getByTestId("campus-plan-generate"));
    expect((screen.getByTestId("campus-plan-generate") as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByTestId("campus-plan-reschedule") as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByTestId("campus-plan-generate"));
    expect(apiMock.generatePlan).toHaveBeenCalledTimes(1);

    release({ plan_id: "plan-1", task_count: 1, first_date: "2026-09-07" });
    await waitFor(() => expect((screen.getByTestId("campus-plan-generate") as HTMLButtonElement).disabled).toBe(false));
  });
});
