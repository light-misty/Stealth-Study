import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../campus/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../campus/api")>();
  return {
    ...actual,
    getAppState: vi.fn(),
    patchAppState: vi.fn(),
  };
});

import * as api from "../../campus/api";
import { CampusSection } from "./CampusSection";

const apiMock = api as unknown as Record<string, ReturnType<typeof vi.fn>>;

afterEach(cleanup);

describe("CampusSection (settings ▸ campus, G-06)", () => {
  beforeEach(() => {
    for (const fn of Object.values(apiMock)) if (typeof fn?.mockReset === "function") fn.mockReset();
  });

  it("loads the stored preferences into the three fields", async () => {
    apiMock.getAppState.mockResolvedValue({
      active_profile_id: "p1",
      settings: { daily_minutes: 90, push_time: "07:30", review_intensity: "intense" },
    });
    render(<CampusSection />);

    const minutes = (await screen.findByTestId("campus-settings-daily-minutes")) as HTMLInputElement;
    const pushTime = screen.getByTestId("campus-settings-push-time") as HTMLInputElement;
    const intensity = screen.getByTestId("campus-settings-intensity") as HTMLSelectElement;
    expect(minutes.value).toBe("90");
    expect(pushTime.value).toBe("07:30");
    expect(intensity.value).toBe("intense");
  });

  it("falls back to the documented defaults when the store has none", async () => {
    apiMock.getAppState.mockResolvedValue({ active_profile_id: null, settings: {} });
    render(<CampusSection />);

    expect(((await screen.findByTestId("campus-settings-daily-minutes")) as HTMLInputElement).value).toBe("60");
    expect((screen.getByTestId("campus-settings-push-time") as HTMLInputElement).value).toBe("20:00");
    expect((screen.getByTestId("campus-settings-intensity") as HTMLSelectElement).value).toBe("standard");
  });

  it("saves the edited preferences through patchAppState", async () => {
    apiMock.getAppState.mockResolvedValue({
      active_profile_id: "p1",
      settings: { daily_minutes: 60, push_time: "20:00", review_intensity: "standard" },
    });
    apiMock.patchAppState.mockResolvedValue({
      active_profile_id: "p1",
      settings: { daily_minutes: 45, push_time: "06:30", review_intensity: "light" },
    });
    render(<CampusSection />);
    await screen.findByTestId("campus-settings-daily-minutes");

    fireEvent.change(screen.getByTestId("campus-settings-daily-minutes"), {
      target: { value: "45" },
    });
    fireEvent.change(screen.getByTestId("campus-settings-push-time"), {
      target: { value: "06:30" },
    });
    fireEvent.change(screen.getByTestId("campus-settings-intensity"), {
      target: { value: "light" },
    });
    fireEvent.click(screen.getByTestId("campus-settings-save"));

    await waitFor(() =>
      expect(apiMock.patchAppState).toHaveBeenCalledWith({
        settings: { daily_minutes: 45, push_time: "06:30", review_intensity: "light" },
      }),
    );
    expect(screen.getByTestId("campus-settings-saved")).toBeTruthy();
  });

  it("refuses to save a non-positive daily-minutes value", async () => {
    apiMock.getAppState.mockResolvedValue({ active_profile_id: null, settings: {} });
    render(<CampusSection />);
    await screen.findByTestId("campus-settings-daily-minutes");

    fireEvent.change(screen.getByTestId("campus-settings-daily-minutes"), {
      target: { value: "0" },
    });
    expect(screen.getByTestId("campus-settings-save").hasAttribute("disabled")).toBe(true);
    expect(apiMock.patchAppState).not.toHaveBeenCalled();
  });

  it("survives a failed load with a retry", async () => {
    apiMock.getAppState.mockRejectedValueOnce(new Error("down"));
    render(<CampusSection />);
    expect(await screen.findByTestId("campus-settings-error")).toBeTruthy();

    apiMock.getAppState.mockResolvedValue({ active_profile_id: null, settings: {} });
    fireEvent.click(screen.getByTestId("campus-settings-retry"));
    await waitFor(() => expect(screen.getByTestId("campus-settings-daily-minutes")).toBeTruthy());
    expect(screen.queryByTestId("campus-settings-error")).toBeNull();
  });
});
