import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ExamProfile } from "../../campus/types";
import { ProfileSwitcher } from "./ProfileSwitcher";

afterEach(cleanup);

const profile = (id: string, status: ExamProfile["status"] = "active"): ExamProfile => ({
  id,
  track_type: "cet",
  title: `档案-${id}`,
  cert_type: null,
  level: "cet4",
  exam_date: "2026-12-19",
  target_score: 500,
  current_estimate: 420,
  subjects: ["reading"],
  daily_minutes: 60,
  status,
  created_at: "2026-09-01T00:00:00Z",
  updated_at: "2026-09-01T00:00:00Z",
  archived_at: status === "archived" ? "2026-09-05T00:00:00Z" : null,
});

const itemById = (id: string): HTMLElement => {
  const found = screen
    .getAllByTestId("campus-profile-item")
    .find((el) => el.getAttribute("data-profile-id") === id);
  if (!found) throw new Error(`profile row ${id} not rendered`);
  return found;
};

describe("ProfileSwitcher", () => {
  it("lists only non-archived profiles and marks the active one", () => {
    render(
      <ProfileSwitcher
        profiles={[profile("p1"), profile("p2"), profile("p3", "archived")]}
        activeId="p2"
        onSwitch={vi.fn()}
        onCreate={vi.fn()}
        onArchive={vi.fn()}
      />,
    );

    const items = screen.getAllByTestId("campus-profile-item");
    expect(items.map((el) => el.getAttribute("data-profile-id"))).toEqual(["p1", "p2"]);
    expect(itemById("p2").getAttribute("data-active")).toBe("true");
    expect(itemById("p1").getAttribute("data-active")).toBe("false");
  });

  it("reports switching, archiving and creating", () => {
    const onSwitch = vi.fn();
    const onArchive = vi.fn();
    const onCreate = vi.fn();
    render(
      <ProfileSwitcher
        profiles={[profile("p1")]}
        activeId="p1"
        onSwitch={onSwitch}
        onCreate={onCreate}
        onArchive={onArchive}
      />,
    );

    fireEvent.click(itemById("p1"));
    expect(onSwitch).toHaveBeenCalledWith("p1");

    fireEvent.click(screen.getByTestId("campus-profile-archive-p1"));
    expect(onArchive).toHaveBeenCalledWith("p1");

    fireEvent.click(screen.getByTestId("campus-profile-create"));
    expect(onCreate).toHaveBeenCalled();
  });

  it("shows the empty hint instead of a list when nothing is left", () => {
    render(
      <ProfileSwitcher
        profiles={[]}
        activeId={null}
        onSwitch={vi.fn()}
        onCreate={vi.fn()}
        onArchive={vi.fn()}
      />,
    );

    expect(screen.queryByTestId("campus-profile-item")).toBeNull();
    expect(screen.getByTestId("campus-profile-empty")).toBeTruthy();
  });

  it("hides the archive action when no handler is supplied", () => {
    render(
      <ProfileSwitcher profiles={[profile("p1")]} activeId="p1" onSwitch={vi.fn()} onCreate={vi.fn()} />,
    );
    expect(screen.queryByTestId("campus-profile-archive-p1")).toBeNull();
  });

  it("asks for a rename per on-desk profile", () => {
    const onRename = vi.fn();
    render(
      <ProfileSwitcher
        profiles={[profile("p1"), profile("p2", "archived")]}
        activeId="p1"
        onSwitch={vi.fn()}
        onCreate={vi.fn()}
        onRename={onRename}
      />,
    );

    fireEvent.click(screen.getByTestId("campus-profile-rename-p1"));
    expect(onRename).toHaveBeenCalledWith("p1");
    expect(screen.queryByTestId("campus-profile-rename-p2")).toBeNull();
  });

  it("offers the archived profiles with their count", () => {
    const onShowArchived = vi.fn();
    render(
      <ProfileSwitcher
        profiles={[profile("p1"), profile("p2", "archived"), profile("p3", "archived")]}
        activeId="p1"
        onSwitch={vi.fn()}
        onCreate={vi.fn()}
        onShowArchived={onShowArchived}
      />,
    );

    const entry = screen.getByTestId("campus-profile-archived-entry");
    expect(entry.textContent).toContain("2");

    fireEvent.click(entry);
    expect(onShowArchived).toHaveBeenCalled();
  });

  it("keeps the archived entry out of the header while the box is empty", () => {
    render(
      <ProfileSwitcher
        profiles={[profile("p1")]}
        activeId="p1"
        onSwitch={vi.fn()}
        onCreate={vi.fn()}
        onShowArchived={vi.fn()}
      />,
    );
    expect(screen.queryByTestId("campus-profile-archived-entry")).toBeNull();
  });
});
