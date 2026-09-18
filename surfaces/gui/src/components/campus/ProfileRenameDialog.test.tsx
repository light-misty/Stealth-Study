import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ExamProfile } from "../../campus/types";
import { ProfileRenameDialog } from "./ProfileRenameDialog";

afterEach(cleanup);

const profile = (id: string, title: string, status: ExamProfile["status"] = "active"): ExamProfile => ({
  id,
  track_type: "cet",
  title,
  cert_type: null,
  level: "cet4",
  exam_date: null,
  target_score: null,
  current_estimate: null,
  subjects: [],
  daily_minutes: 60,
  status,
  created_at: "2026-09-01T00:00:00Z",
  updated_at: "2026-09-01T00:00:00Z",
  archived_at: status === "archived" ? "2026-09-05T00:00:00Z" : null,
});

function renderDialog(props: Partial<Parameters<typeof ProfileRenameDialog>[0]> = {}) {
  const target = props.profile ?? profile("p1", "四级冲刺");
  const onSubmit = props.onSubmit ?? (async () => true);
  render(
    <ProfileRenameDialog
      profile={target}
      profiles={props.profiles ?? [target, profile("p2", "六级冲关")]}
      onSubmit={onSubmit}
      onClose={props.onClose ?? vi.fn()}
    />,
  );
  return { target, input: screen.getByTestId("campus-profile-rename-input") as HTMLInputElement };
}

describe("ProfileRenameDialog", () => {
  it("starts from the profile's current name", () => {
    const { input } = renderDialog();
    expect(input.value).toBe("四级冲刺");
  });

  it("refuses a name an unarchived profile holds, and allows one only the box holds", () => {
    const { input } = renderDialog({
      profiles: [
        profile("p1", "四级冲刺"),
        profile("p2", "六级冲关"),
        profile("p3", "箱子里的", "archived"),
      ],
    });

    fireEvent.change(input, { target: { value: "六级冲关" } });
    expect(screen.getByTestId("campus-profile-rename-error").textContent).toContain(
      "A profile with this title already exists",
    );
    expect((screen.getByTestId("campus-profile-rename-save") as HTMLButtonElement).disabled).toBe(
      true,
    );

    fireEvent.change(input, { target: { value: "箱子里的" } });
    expect(screen.queryByTestId("campus-profile-rename-error")).toBeNull();
    expect((screen.getByTestId("campus-profile-rename-save") as HTMLButtonElement).disabled).toBe(
      false,
    );
  });

  it("keeps the name required and trims what it sends", async () => {
    const onSubmit = vi.fn(async () => true);
    const onClose = vi.fn();
    const { input } = renderDialog({ onSubmit, onClose });

    fireEvent.change(input, { target: { value: "   " } });
    expect(screen.getByTestId("campus-profile-rename-error").textContent).toContain(
      "A profile name is required",
    );

    fireEvent.change(input, { target: { value: "  新名字  " } });
    fireEvent.click(screen.getByTestId("campus-profile-rename-save"));

    await waitFor(() => expect(onSubmit).toHaveBeenCalledWith("新名字"));
    await waitFor(() => expect(onClose).toHaveBeenCalled());
  });

  it("keeps the dialog open with the reason when the backend still refuses", async () => {
    const onClose = vi.fn();
    const { input } = renderDialog({
      onSubmit: async () => false,
      profiles: [profile("p1", "四级冲刺")],
      onClose,
    });

    fireEvent.change(input, { target: { value: "别处占用的" } });
    fireEvent.click(screen.getByTestId("campus-profile-rename-save"));

    await waitFor(() =>
      expect(screen.getByTestId("campus-profile-rename-error")).toBeTruthy(),
    );
    expect(onClose).not.toHaveBeenCalled();
    expect(input.value).toBe("别处占用的");
  });
});
