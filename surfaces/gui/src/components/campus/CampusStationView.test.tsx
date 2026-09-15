import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { CampusApiError } from "../../campus/api";
import type { ExamProfile } from "../../campus/types";

vi.mock("../../campus/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../campus/api")>();
  return {
    ...actual,
    listProfiles: vi.fn(),
    getAppState: vi.fn(),
    patchAppState: vi.fn(),
    createProfile: vi.fn(),
    patchProfile: vi.fn(),
    getCapabilities: vi.fn(),
    listMistakes: vi.fn(),
    listDueReviews: vi.fn(),
    listLibraryDocs: vi.fn(),
    getReminders: vi.fn(),
  };
});

import * as api from "../../campus/api";
import { CampusStationView } from "./CampusStationView";

const apiMock = api as unknown as Record<string, ReturnType<typeof vi.fn>>;

afterEach(cleanup);

const profile = (id = "p1", examDate: string | null = "2026-12-19"): ExamProfile => ({
  id,
  track_type: "cet",
  title: "四级冲刺",
  cert_type: null,
  level: "cet4",
  exam_date: examDate,
  target_score: 500,
  current_estimate: 420,
  subjects: ["reading"],
  daily_minutes: 60,
  status: "active",
  created_at: "2026-09-01T00:00:00Z",
  updated_at: "2026-09-01T00:00:00Z",
});

describe("CampusStationView", () => {
  beforeEach(() => {
    for (const fn of Object.values(apiMock)) if (typeof fn?.mockReset === "function") fn.mockReset();
    apiMock.listProfiles.mockResolvedValue({ items: [profile()] });
    apiMock.getAppState.mockResolvedValue({ active_profile_id: "p1", settings: {} });
    apiMock.patchAppState.mockResolvedValue({ active_profile_id: "p1", settings: {} });
    apiMock.getCapabilities.mockResolvedValue({
      current_model: "gpt-4o",
      tasks: [{ task: "grading", recommended: "a", minimum: "b", supported: true, reason: null }],
    });
    apiMock.listMistakes.mockResolvedValue({ items: [], total: 0 });
    apiMock.listDueReviews.mockResolvedValue({ items: [] });
    apiMock.listLibraryDocs.mockResolvedValue({ items: [] });
    apiMock.getReminders.mockResolvedValue({ banner: [], expired: [] });
    apiMock.patchProfile.mockResolvedValue(profile("p1"));
  });

  it("renders the station shell for a track once a profile exists", async () => {
    render(<CampusStationView track="cet" />);
    await waitFor(() => expect(screen.getByTestId("campus-station")).toBeTruthy());
    expect(screen.getByTestId("campus-station").getAttribute("data-track")).toBe("cet");
    expect(screen.getByTestId("campus-profile-switcher")).toBeTruthy();
  });

  it("shows the create-profile guide when there is no profile yet", async () => {
    apiMock.listProfiles.mockResolvedValue({ items: [] });
    apiMock.getAppState.mockResolvedValue({ active_profile_id: null, settings: {} });
    render(<CampusStationView track="cet" />);

    await waitFor(() => expect(screen.getByTestId("campus-station-empty")).toBeTruthy());
    expect(screen.getByTestId("campus-profile-create-card")).toBeTruthy();
    expect(screen.queryByTestId("campus-station")).toBeNull();
  });

  it("creates the first profile from the guide card", async () => {
    apiMock.listProfiles.mockResolvedValue({ items: [] });
    apiMock.getAppState.mockResolvedValue({ active_profile_id: null, settings: {} });
    apiMock.createProfile.mockResolvedValue(profile("p9"));
    render(<CampusStationView track="kaoyan" />);
    await waitFor(() => expect(screen.getByTestId("campus-profile-create-card")).toBeTruthy());

    fireEvent.change(screen.getByTestId("campus-profile-create-title"), {
      target: { value: "考研 2027" },
    });
    fireEvent.click(screen.getByTestId("campus-profile-create-submit"));

    await waitFor(() => expect(apiMock.createProfile).toHaveBeenCalled());
    expect(apiMock.createProfile.mock.calls[0][0]).toMatchObject({
      track_type: "kaoyan",
      title: "考研 2027",
    });
  });

  it("guides the user when no model is configured", async () => {
    apiMock.getCapabilities.mockResolvedValue({
      current_model: null,
      tasks: [{ task: "grading", recommended: "a", minimum: "b", supported: false, reason: null }],
    });
    render(<CampusStationView track="cet" />);
    await waitFor(() => expect(screen.getByTestId("campus-empty-model-guide")).toBeTruthy());
    expect(screen.getByTestId("campus-empty-model-guide").getAttribute("data-reason")).toBe("no_model");
  });

  it("stays quiet about the model when everything is supported", async () => {
    render(<CampusStationView track="cet" />);
    await waitFor(() => expect(screen.getByTestId("campus-station")).toBeTruthy());
    await waitFor(() => expect(screen.queryByTestId("campus-empty-model-guide")).toBeNull());
  });

  it("shows the exam countdown on the CET station", async () => {
    render(<CampusStationView track="cet" />);
    await waitFor(() => expect(screen.getByTestId("campus-countdown-banner")).toBeTruthy());
    expect(screen.getByTestId("campus-countdown-banner").getAttribute("data-days-left")).not.toBe("");
  });

  it("shows the deadline banner on the certificate station", async () => {
    apiMock.getReminders.mockResolvedValue({
      banner: [
        { id: "d1", node_type: "exam", date: "2026-10-20", days_left: 7, is_reference: true },
      ],
      expired: [],
    });
    render(<CampusStationView track="cert" />);
    await waitFor(() => expect(screen.getByTestId("campus-deadline-banner")).toBeTruthy());
    expect(screen.getByTestId("campus-deadline-reference")).toBeTruthy();
  });

  it("mounts the shared panels on every track and the library only where configured", async () => {
    render(<CampusStationView track="cet" />);
    await waitFor(() => expect(screen.getByTestId("campus-mistake-panel")).toBeTruthy());
    expect(screen.getByTestId("campus-review-queue")).toBeTruthy();
    expect(screen.queryByTestId("campus-library-panel")).toBeNull();
    cleanup();

    render(<CampusStationView track="kaoyan" />);
    await waitFor(() => expect(screen.getByTestId("campus-library-panel")).toBeTruthy());
    expect(screen.getByTestId("campus-qa-panel")).toBeTruthy();
  });

  it("archives a profile through the switcher and refreshes the list", async () => {
    render(<CampusStationView track="cet" />);
    await waitFor(() => expect(screen.getByTestId("campus-station")).toBeTruthy());

    fireEvent.click(screen.getByTestId("campus-profile-archive-p1"));
    await waitFor(() => expect(apiMock.patchProfile).toHaveBeenCalledWith("p1", { status: "archived" }));
    await waitFor(() => expect(apiMock.listProfiles.mock.calls.length).toBeGreaterThan(1));
  });

  it("surfaces a load failure with a retry instead of an empty station", async () => {
    apiMock.listProfiles.mockRejectedValue(
      new CampusApiError("MODEL_TIMEOUT", "timeout", true, 504),
    );
    render(<CampusStationView track="cet" />);
    await waitFor(() => expect(screen.getByTestId("campus-station-error")).toBeTruthy());
    expect(screen.getByTestId("campus-station-retry")).toBeTruthy();
  });

  it("renders a skeleton while the profile list is in flight", () => {
    apiMock.listProfiles.mockReturnValue(new Promise(() => {}));
    render(<CampusStationView track="cet" />);
    expect(screen.getByTestId("campus-station-loading")).toBeTruthy();
  });
});
