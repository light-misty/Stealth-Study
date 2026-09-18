import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { PlanTask, ProgressReport, TaskStatus } from "../../../campus/types";

import { PlanBoard } from "./PlanBoard";

afterEach(cleanup);

const task = (
  id: string,
  date: string,
  status: TaskStatus = "todo",
  subject = "politics",
): PlanTask => ({
  id,
  plan_id: "plan-1",
  profile_id: "p1",
  title: `task-${id}`,
  detail: "",
  subject,
  scheduled_date: date,
  est_minutes: 60,
  priority: 2,
  status,
  board_card_id: null,
  completed_at: status === "done" ? `${date}T10:00:00Z` : null,
  created_at: "2026-09-01T00:00:00Z",
  updated_at: "2026-09-01T00:00:00Z",
});

const progress = (overrides: Record<string, { done: number; total: number; rate: number }> = {}): ProgressReport => ({
  by_track: {
    politics: { done: 1, total: 4, rate: 0.25 },
    english: { done: 2, total: 4, rate: 0.5 },
    math: { done: 0, total: 2, rate: 0 },
    major: { done: 3, total: 6, rate: 0.5 },
    ...overrides,
  },
  streak_days: 3,
  heatmap: [
    { date: "2026-09-07", count: 2 },
    { date: "2026-09-08", count: 1 },
    { date: "2026-09-10", count: 4 },
  ],
});

describe("PlanBoard", () => {
  it("groups tasks into ISO weeks ordered by their Monday", () => {
    render(
      <PlanBoard
        tasks={[
          task("t3", "2026-09-14", "todo", "math"),
          task("t1", "2026-09-07"),
          task("t2", "2026-09-08", "todo", "english"),
        ]}
        progress={null}
      />,
    );

    const weeks = screen.getAllByTestId("campus-kaoyan-week");
    expect(weeks).toHaveLength(2);
    expect(weeks[0].getAttribute("data-week")).toBe("2026-09-07");
    expect(weeks[1].getAttribute("data-week")).toBe("2026-09-14");
    expect(screen.getByTestId("campus-kaoyan-task-t1")).toBeTruthy();
    expect(screen.getByTestId("campus-kaoyan-task-t2")).toBeTruthy();
    expect(screen.getByTestId("campus-kaoyan-task-t3")).toBeTruthy();
  });

  it("keeps tasks of the same week together across month boundaries", () => {
    render(
      <PlanBoard
        tasks={[task("t1", "2026-09-30"), task("t2", "2026-10-01", "todo", "english")]}
        progress={null}
      />,
    );

    const weeks = screen.getAllByTestId("campus-kaoyan-week");
    expect(weeks).toHaveLength(1);
    expect(weeks[0].getAttribute("data-week")).toBe("2026-09-28");
  });

  it("renders one ring per track with done/total labels", () => {
    render(<PlanBoard tasks={[task("t1", "2026-09-07")]} progress={progress()} />);

    const rings = screen.getAllByTestId("campus-kaoyan-ring");
    expect(rings).toHaveLength(4);
    const tracks = rings.map((r) => r.getAttribute("data-track"));
    expect(tracks).toEqual(["politics", "english", "math", "major"]);
    expect(rings[0].textContent).toContain("1/4");
    expect(rings[1].textContent).toContain("2/4");
    expect(rings[2].textContent).toContain("0/2");
    expect(rings[3].textContent).toContain("3/6");
  });

  it("summarises overall completion beside the rings", () => {
    render(<PlanBoard tasks={[task("t1", "2026-09-07")]} progress={progress()} />);

    // 连续打卡与热图归右栏常驻，计划板只留四轨环 + 总体完成率
    expect(screen.queryByTestId("campus-kaoyan-streak")).toBeNull();
    expect(screen.queryByTestId("campus-kaoyan-heatmap")).toBeNull();
    expect(screen.getByTestId("campus-kaoyan-overall").textContent).toContain("6/16");
  });

  it("stays read-only: no buttons, inputs or drag handles anywhere", () => {
    const { container } = render(
      <PlanBoard
        tasks={[
          task("t1", "2026-09-07", "done"),
          task("t2", "2026-09-08", "doing", "english"),
          task("t3", "2026-09-09", "todo", "math"),
        ]}
        progress={progress()}
      />,
    );

    expect(container.querySelector("button, input, select, textarea, [draggable='true']")).toBeNull();
  });

  it("shows the empty hint when there is no plan and no progress", () => {
    render(<PlanBoard tasks={[]} progress={null} />);

    expect(screen.getByTestId("campus-kaoyan-board").textContent).toContain("No plan yet");
  });
});
