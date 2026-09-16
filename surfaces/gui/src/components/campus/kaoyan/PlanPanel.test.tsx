import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { PlanTask } from "../../../campus/types";

vi.mock("../../../campus/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../../campus/api")>();
  return {
    ...actual,
    listTasks: vi.fn(),
    getProgress: vi.fn(),
    generatePlan: vi.fn(),
    reschedulePlan: vi.fn(),
  };
});

import * as api from "../../../campus/api";
import { PlanPanel } from "./PlanPanel";

const apiMock = api as unknown as Record<string, ReturnType<typeof vi.fn>>;

afterEach(cleanup);

const progress = {
  by_track: { politics: { done: 1, total: 2, rate: 0.5 } },
  streak_days: 1,
  heatmap: [],
};

const task = (id: string, date: string, status: PlanTask["status"]): PlanTask => ({
  id,
  plan_id: "plan-1",
  profile_id: "p1",
  title: `task-${id}`,
  detail: "",
  subject: "politics",
  scheduled_date: date,
  est_minutes: 60,
  priority: 2,
  status,
  board_card_id: null,
  completed_at: status === "done" ? `${date}T10:00:00Z` : null,
  created_at: "2026-09-01T00:00:00Z",
  updated_at: "2026-09-01T00:00:00Z",
});

describe("PlanPanel", () => {
  beforeEach(() => {
    for (const key of ["listTasks", "getProgress", "generatePlan", "reschedulePlan"]) {
      apiMock[key].mockReset();
    }
  });

  it("loads tasks and progress once and renders editor plus board", async () => {
    apiMock.listTasks.mockResolvedValue({ items: [task("t1", "2026-09-07", "todo")] });
    apiMock.getProgress.mockResolvedValue(progress);

    render(<PlanPanel profileId="p1" />);

    await waitFor(() => expect(screen.getByTestId("campus-kaoyan-task-t1")).toBeTruthy());
    expect(apiMock.listTasks).toHaveBeenCalledWith("p1");
    expect(apiMock.getProgress).toHaveBeenCalledWith("p1");
    expect(screen.getByTestId("campus-plan-editor")).toBeTruthy();
    expect(screen.getAllByTestId("campus-kaoyan-week")).toHaveLength(1);
  });

  it("shows the load error with a working retry", async () => {
    apiMock.listTasks.mockRejectedValue(new Error("boom"));
    apiMock.getProgress.mockResolvedValue(progress);

    render(<PlanPanel profileId="p1" />);
    await waitFor(() => expect(screen.getByTestId("campus-kaoyan-plan-error")).toBeTruthy());

    apiMock.listTasks.mockResolvedValue({ items: [task("t1", "2026-09-07", "todo")] });
    fireEvent.click(screen.getByTestId("campus-kaoyan-plan-retry"));
    await waitFor(() => expect(screen.getByTestId("campus-kaoyan-task-t1")).toBeTruthy());
  });

  it("keeps completed tasks on their original dates after a reschedule refresh", async () => {
    const done = task("t-done", "2026-09-07", "done");
    const todo = task("t-todo", "2026-09-08", "todo");
    apiMock.listTasks
      .mockResolvedValueOnce({ items: [done, todo] })
      .mockResolvedValueOnce({
        items: [done, task("t-todo", "2026-09-15", "todo")],
      });
    apiMock.getProgress.mockResolvedValue(progress);
    apiMock.reschedulePlan.mockResolvedValue({ rescheduled: 1, preserved_done: 1 });

    render(<PlanPanel profileId="p1" />);
    await waitFor(() => expect(screen.getByTestId("campus-kaoyan-task-t-todo")).toBeTruthy());
    expect(screen.getByTestId("campus-kaoyan-task-t-todo").textContent).toContain("2026-09-08");

    fireEvent.click(screen.getByTestId("campus-plan-reschedule"));
    await waitFor(() => expect(apiMock.listTasks).toHaveBeenCalledTimes(2));
    await waitFor(() =>
      expect(screen.getByTestId("campus-kaoyan-task-t-todo").textContent).toContain("2026-09-15"),
    );
    expect(apiMock.reschedulePlan).toHaveBeenCalledWith("plan-1", undefined);
    expect(screen.getByTestId("campus-kaoyan-task-t-done").textContent).toContain("2026-09-07");
  });

  it("refreshes the board after a successful generation", async () => {
    apiMock.listTasks
      .mockResolvedValueOnce({ items: [] })
      .mockResolvedValueOnce({ items: [task("t-new", "2026-09-07", "todo")] });
    apiMock.getProgress.mockResolvedValue(progress);
    apiMock.generatePlan.mockResolvedValue({ plan_id: "plan-1", task_count: 1, first_date: "2026-09-07" });

    render(<PlanPanel profileId="p1" />);
    await waitFor(() => expect(screen.getByTestId("campus-kaoyan-board").textContent).toContain("No plan yet"));

    fireEvent.click(screen.getByTestId("campus-plan-generate"));
    await waitFor(() => expect(apiMock.listTasks).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(screen.getByTestId("campus-kaoyan-task-t-new")).toBeTruthy());
  });
});
