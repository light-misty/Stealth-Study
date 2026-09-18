import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ExamProfile } from "../../campus/types";
import { ArchivedProfilesDialog } from "./ArchivedProfilesDialog";

afterEach(cleanup);

const archived = (
  id: string,
  title: string,
  createdAt: string,
  archivedAt: string | null,
): ExamProfile => ({
  id,
  track_type: "cet",
  title,
  cert_type: null,
  level: "cet4",
  exam_date: "2026-12-19",
  target_score: 500,
  current_estimate: 420,
  subjects: ["reading", "listening"],
  daily_minutes: 90,
  status: "archived",
  created_at: createdAt,
  updated_at: archivedAt ?? createdAt,
  archived_at: archivedAt,
});

const daysAgo = (days: number): string =>
  new Date(Date.now() - days * 24 * 60 * 60 * 1000).toISOString();

const recent = archived("a1", "四级冲刺", daysAgo(200), daysAgo(2));
const older = archived("a2", "六级冲关", daysAgo(120), daysAgo(90));
const legacy = archived("a3", "历史归档", daysAgo(40), null);

const dayText = (value: string | null): string => (value ?? "").slice(0, 10);

describe("ArchivedProfilesDialog", () => {
  it("lists the archived profiles with their create and archive dates", () => {
    render(
      <ArchivedProfilesDialog profiles={[recent, older, legacy]} onRestore={vi.fn()} onRename={vi.fn()} onClose={vi.fn()} />,
    );

    expect(screen.getByTestId("campus-archived-row-a1").textContent).toContain("四级冲刺");
    expect(screen.getByTestId("campus-archived-created-a1").textContent).toContain(
      dayText(recent.created_at),
    );
    expect(screen.getByTestId("campus-archived-at-a1").textContent).toContain(
      dayText(recent.archived_at),
    );
    expect(screen.getByTestId("campus-archived-at-a3").textContent).toBe("--");
  });

  it("narrows the list by profile name", () => {
    render(
      <ArchivedProfilesDialog profiles={[recent, older, legacy]} onRestore={vi.fn()} onRename={vi.fn()} onClose={vi.fn()} />,
    );

    fireEvent.change(screen.getByTestId("campus-archived-search"), {
      target: { value: "冲关" },
    });

    expect(screen.queryByTestId("campus-archived-row-a1")).toBeNull();
    expect(screen.getByTestId("campus-archived-row-a2")).toBeTruthy();
    expect(screen.getByTestId("campus-archived-list").textContent).toContain("六级冲关");
  });

  it("filters by when the profile was archived and keeps pre-timestamp rows as older", () => {
    render(
      <ArchivedProfilesDialog profiles={[recent, older, legacy]} onRestore={vi.fn()} onRename={vi.fn()} onClose={vi.fn()} />,
    );

    fireEvent.change(screen.getByTestId("campus-archived-filter"), {
      target: { value: "recent_7d" },
    });
    expect(screen.getByTestId("campus-archived-row-a1")).toBeTruthy();
    expect(screen.queryByTestId("campus-archived-row-a2")).toBeNull();
    expect(screen.queryByTestId("campus-archived-row-a3")).toBeNull();

    fireEvent.change(screen.getByTestId("campus-archived-filter"), {
      target: { value: "older" },
    });
    expect(screen.queryByTestId("campus-archived-row-a1")).toBeNull();
    expect(screen.getByTestId("campus-archived-row-a2")).toBeTruthy();
    expect(screen.getByTestId("campus-archived-row-a3")).toBeTruthy();
  });

  it("sorts by archive date first and can switch to creation date", () => {
    render(
      <ArchivedProfilesDialog profiles={[older, recent, legacy]} onRestore={vi.fn()} onRename={vi.fn()} onClose={vi.fn()} />,
    );

    expect(screen.getByTestId("campus-archived-list").textContent).toMatch(/四级冲刺.*六级冲关.*历史归档/s);

    fireEvent.change(screen.getByTestId("campus-archived-sort"), {
      target: { value: "created_desc" },
    });
    expect(screen.getByTestId("campus-archived-list").textContent).toMatch(/历史归档.*六级冲关.*四级冲刺/s);
  });

  it("says so when a search matches nothing", () => {
    render(
      <ArchivedProfilesDialog profiles={[recent]} onRestore={vi.fn()} onRename={vi.fn()} onClose={vi.fn()} />,
    );

    fireEvent.change(screen.getByTestId("campus-archived-search"), {
      target: { value: "不存在的名字" },
    });

    expect(screen.getByTestId("campus-archived-nomatch")).toBeTruthy();
    expect(screen.queryByTestId("campus-archived-list")).toBeNull();
  });

  it("says so when there is nothing archived at all", () => {
    render(<ArchivedProfilesDialog profiles={[]} onRestore={vi.fn()} onRename={vi.fn()} onClose={vi.fn()} />);
    expect(screen.getByTestId("campus-archived-empty")).toBeTruthy();
  });

  it("opens one profile's details and returns to the list", () => {
    render(
      <ArchivedProfilesDialog profiles={[recent]} onRestore={vi.fn()} onRename={vi.fn()} onClose={vi.fn()} />,
    );

    fireEvent.click(screen.getByTestId("campus-archived-detail-a1"));

    const detail = screen.getByTestId("campus-archived-detail");
    expect(detail.textContent).toContain("四级冲刺");
    expect(detail.textContent).toContain("2026-12-19");
    expect(detail.textContent).toContain("500");
    expect(detail.textContent).toContain("90");
    expect(screen.queryByTestId("campus-archived-list")).toBeNull();

    fireEvent.click(screen.getByTestId("campus-archived-detail-back"));
    expect(screen.getByTestId("campus-archived-list")).toBeTruthy();
  });

  it("asks for a rename from both the list and the detail view", () => {
    const onRename = vi.fn();
    render(
      <ArchivedProfilesDialog
        profiles={[recent]}
        onRestore={vi.fn()}
        onRename={onRename}
        onClose={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByTestId("campus-archived-rename-a1"));
    expect(onRename).toHaveBeenCalledWith("a1");

    fireEvent.click(screen.getByTestId("campus-archived-detail-a1"));
    fireEvent.click(screen.getByTestId("campus-archived-detail-rename"));
    expect(onRename).toHaveBeenCalledTimes(2);
    expect(onRename).toHaveBeenLastCalledWith("a1");
  });

  it("restores a profile from both the list and the detail view", () => {
    const onRestore = vi.fn();
    render(
      <ArchivedProfilesDialog profiles={[recent]} onRestore={onRestore} onRename={vi.fn()} onClose={vi.fn()} />,
    );

    fireEvent.click(screen.getByTestId("campus-archived-restore-a1"));
    expect(onRestore).toHaveBeenCalledWith("a1");

    fireEvent.click(screen.getByTestId("campus-archived-detail-a1"));
    fireEvent.click(screen.getByTestId("campus-archived-detail-restore"));
    expect(onRestore).toHaveBeenCalledTimes(2);
    expect(onRestore).toHaveBeenLastCalledWith("a1");
  });
});
