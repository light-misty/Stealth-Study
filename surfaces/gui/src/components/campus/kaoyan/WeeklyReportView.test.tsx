import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { WeeklyReport } from "../../../campus/types";

vi.mock("../../../campus/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../../campus/api")>();
  return { ...actual, listWeeklyReports: vi.fn(), generateWeeklyReport: vi.fn() };
});

import * as api from "../../../campus/api";
import { WeeklyReportView } from "./WeeklyReportView";

const apiMock = api as unknown as Record<string, ReturnType<typeof vi.fn>>;

afterEach(cleanup);

const report = (id: string, weekStart: string, weekEnd: string, overall: number): WeeklyReport => ({
  id,
  profile_id: "p1",
  week_start: weekStart,
  week_end: weekEnd,
  completion_rate: { overall, politics: Math.round(overall / 2 * 100) / 100 },
  top_mistake_points: [{ point_id: "pt1", title: "Shaders", count: 3 }],
  suggestion: "Focus on Shaders next week.",
  content_md: "## Weekly digest\n- overall 25%",
  created_at: "2026-09-14T00:00:00Z",
});

describe("WeeklyReportView", () => {
  beforeEach(() => {
    apiMock.listWeeklyReports.mockReset();
    apiMock.generateWeeklyReport.mockReset();
  });

  it("lists reports newest first with their week range and overall rate", async () => {
    apiMock.listWeeklyReports.mockResolvedValue({
      items: [
        report("w2", "2026-09-14", "2026-09-20", 0.5),
        report("w1", "2026-09-07", "2026-09-13", 0.25),
      ],
    });

    render(<WeeklyReportView profileId="p1" />);

    await waitFor(() => expect(screen.getAllByTestId(/^campus-weekly-item-/)).toHaveLength(2));
    expect(screen.getByTestId("campus-weekly-item-w2").textContent).toContain("2026-09-14");
    expect(screen.getByTestId("campus-weekly-item-w2").textContent).toContain("50%");
    expect(screen.getByTestId("campus-weekly-item-w1").textContent).toContain("25%");
  });

  it("shows the empty hint when no report exists", async () => {
    apiMock.listWeeklyReports.mockResolvedValue({ items: [] });

    render(<WeeklyReportView profileId="p1" />);
    await waitFor(() => expect(screen.getByTestId("campus-weekly-empty")).toBeTruthy());
  });

  it("expands the picked report with rates, top mistakes, suggestion and markdown", async () => {
    apiMock.listWeeklyReports.mockResolvedValue({
      items: [report("w1", "2026-09-07", "2026-09-13", 0.25)],
    });

    render(<WeeklyReportView profileId="p1" />);
    fireEvent.click(await waitFor(() => screen.getByTestId("campus-weekly-item-w1")));

    const detail = await waitFor(() => screen.getByTestId("campus-weekly-detail-w1"));
    expect(detail.textContent).toContain("25%");
    expect(detail.textContent).toContain("13%");
    expect(detail.textContent).toContain("Shaders");
    expect(detail.textContent).toContain("3");
    expect(detail.textContent).toContain("Focus on Shaders next week.");
    expect(detail.textContent).toContain("Weekly digest");
  });

  it("prepends the generated report and reuses the hook upsert", async () => {
    const w1 = report("w1", "2026-09-07", "2026-09-13", 0.25);
    apiMock.listWeeklyReports.mockResolvedValue({ items: [w1] });
    const w2 = report("w2", "2026-09-14", "2026-09-20", 0.5);
    apiMock.generateWeeklyReport.mockResolvedValue(w2);

    render(<WeeklyReportView profileId="p1" />);
    fireEvent.click(await waitFor(() => screen.getByTestId("campus-weekly-generate")));

    await waitFor(() => expect(screen.getByTestId("campus-weekly-item-w2")).toBeTruthy());
    expect(apiMock.generateWeeklyReport).toHaveBeenCalledWith("p1");
    const items = screen.getAllByTestId(/^campus-weekly-item-/);
    expect(items[0].getAttribute("data-testid")).toBe("campus-weekly-item-w2");
  });

  it("keeps the list and shows the error when generation fails", async () => {
    apiMock.listWeeklyReports.mockResolvedValue({
      items: [report("w1", "2026-09-07", "2026-09-13", 0.25)],
    });
    apiMock.generateWeeklyReport.mockRejectedValue(new Error("no model"));

    render(<WeeklyReportView profileId="p1" />);
    await waitFor(() => expect(screen.getByTestId("campus-weekly-item-w1")).toBeTruthy());

    fireEvent.click(screen.getByTestId("campus-weekly-generate"));
    await waitFor(() => expect(screen.getByTestId("campus-weekly-gen-error")).toBeTruthy());
    expect(screen.getAllByTestId(/^campus-weekly-item-/)).toHaveLength(1);
  });
});
