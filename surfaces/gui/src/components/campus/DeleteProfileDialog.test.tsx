import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { CampusApiError } from "../../campus/api";
import type { ExamProfile } from "../../campus/types";
import { DeleteProfileDialog } from "./DeleteProfileDialog";

vi.mock("../../campus/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../campus/api")>();
  return { ...actual, getProfileImpact: vi.fn() };
});

import * as api from "../../campus/api";

const apiMock = api as unknown as Record<string, ReturnType<typeof vi.fn>>;

afterEach(cleanup);

const profile: ExamProfile = {
  id: "p1",
  track_type: "cet",
  title: "四级冲刺",
  cert_type: null,
  level: "cet4",
  exam_date: "2026-12-19",
  target_score: 500,
  current_estimate: 420,
  subjects: ["reading"],
  daily_minutes: 60,
  status: "archived",
  created_at: "2026-09-01T00:00:00Z",
  updated_at: "2026-09-01T00:00:00Z",
  archived_at: "2026-09-10T00:00:00Z",
};

const impact = (over: Record<string, unknown> = {}) => ({
  profile_id: "p1",
  cascade: { exam_profile: 1, mistake_book: 3, source_doc: 2, doc_chunk: 7 },
  automation_tasks: 1,
  export_files: 4,
  ...over,
});

const rowsOf = () =>
  screen.getAllByTestId("campus-delete-row").map((row) => [row.getAttribute("data-key"), row.textContent]);

const total = () => screen.getByTestId("campus-delete-count").getAttribute("data-total");

function renderDialog(over: Partial<Parameters<typeof DeleteProfileDialog>[0]> = {}) {
  const onConfirm = over.onConfirm ?? vi.fn();
  render(
    <DeleteProfileDialog
      profile={profile}
      onConfirm={onConfirm}
      onClose={over.onClose ?? vi.fn()}
      busy={over.busy ?? false}
      error={over.error ?? null}
    />,
  );
  return onConfirm;
}

beforeEach(() => {
  for (const fn of Object.values(apiMock)) {
    if (typeof fn?.mockReset === "function") fn.mockReset();
  }
});

describe("DeleteProfileDialog", () => {
  it("names the profile and counts every group the delete will take", async () => {
    apiMock.getProfileImpact.mockResolvedValue(impact());
    renderDialog();

    await waitFor(() => expect(screen.getAllByTestId("campus-delete-row").length).toBe(5));
    expect(screen.getByTestId("campus-delete-dialog").textContent).toContain("四级冲刺");
    expect(apiMock.getProfileImpact).toHaveBeenCalledWith("p1");
    expect(rowsOf()).toEqual([
      ["library", "9"],
      ["mistakes", "3"],
      ["profile", "1"],
      ["automations", "1"],
      ["exports", "4"],
    ]);
    expect(total()).toBe("18");
  });

  it("holds the destructive action back until the cost is known", async () => {
    let resolve: (value: unknown) => void = () => {};
    apiMock.getProfileImpact.mockReturnValue(
      new Promise((next) => {
        resolve = next;
      }),
    );
    renderDialog();

    expect((screen.getByTestId("campus-delete-confirm") as HTMLButtonElement).disabled).toBe(true);
    resolve(impact());
    await waitFor(() =>
      expect((screen.getByTestId("campus-delete-confirm") as HTMLButtonElement).disabled).toBe(
        false,
      ),
    );
  });

  it("keeps a profile that owns nothing deletable and still says the profile itself goes", async () => {
    apiMock.getProfileImpact.mockResolvedValue(
      impact({ cascade: { exam_profile: 1 }, automation_tasks: 0, export_files: 0 }),
    );
    renderDialog();

    await waitFor(() => expect(screen.getAllByTestId("campus-delete-row").length).toBe(1));
    expect(rowsOf()).toEqual([["profile", "1"]]);
    expect(total()).toBe("1");
  });

  it("folds a table it has no label for into one other row", async () => {
    apiMock.getProfileImpact.mockResolvedValue(
      impact({ cascade: { exam_profile: 1, mistake_book: 2, quiz_archive: 5 } }),
    );
    renderDialog();

    await waitFor(() => expect(screen.getAllByTestId("campus-delete-row").length).toBe(5));
    expect(rowsOf()).toContainEqual(["other", "5"]);
    expect(rowsOf()).toContainEqual(["mistakes", "2"]);
    expect(total()).toBe("13");
  });

  it("releases the action with an honest note when the preview cannot be read", async () => {
    apiMock.getProfileImpact.mockRejectedValue(
      new CampusApiError("MODEL_TIMEOUT", "timeout", true, 504),
    );
    renderDialog();

    await waitFor(() => expect(screen.getByTestId("campus-delete-unavailable")).toBeTruthy());
    expect(screen.getByTestId("campus-delete-unavailable").textContent).toContain("unavailable");
    expect((screen.getByTestId("campus-delete-confirm") as HTMLButtonElement).disabled).toBe(false);
  });

  it("confirms once against the profile it showed", async () => {
    apiMock.getProfileImpact.mockResolvedValue(impact());
    const onConfirm = renderDialog();

    await waitFor(() =>
      expect((screen.getByTestId("campus-delete-confirm") as HTMLButtonElement).disabled).toBe(
        false,
      ),
    );
    fireEvent.click(screen.getByTestId("campus-delete-confirm"));
    expect(onConfirm).toHaveBeenCalledTimes(1);
    expect(onConfirm).toHaveBeenCalledWith("p1");
  });

  it("keeps a failed delete on screen with a way to try again", async () => {
    apiMock.getProfileImpact.mockResolvedValue(impact());
    const onConfirm = renderDialog({
      error: new CampusApiError("PROFILE_NOT_FOUND", "档案不存在", false, 404),
    });

    await waitFor(() => expect(screen.getByTestId("campus-delete-error")).toBeTruthy());
    expect(screen.getByTestId("campus-delete-error").textContent).toContain("Profile not found");
    fireEvent.click(screen.getByTestId("campus-delete-retry"));
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it("refuses a second delete while one is in flight", async () => {
    apiMock.getProfileImpact.mockResolvedValue(impact());
    renderDialog({ busy: true });

    await waitFor(() =>
      expect((screen.getByTestId("campus-delete-confirm") as HTMLButtonElement).disabled).toBe(true),
    );
  });
});
