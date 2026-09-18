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
    getKnowledgeTree: vi.fn(),
    getMasteryCoverage: vi.fn(),
    listDeadlines: vi.fn(),
    listTasks: vi.fn(),
    getProgress: vi.fn(),
    listWeeklyReports: vi.fn(),
    createAssessment: vi.fn(),
    getAssessment: vi.fn(),
    patchAssessment: vi.fn(),
    finishAssessment: vi.fn(),
    listVocabToday: vi.fn(),
    setVocabMastery: vi.fn(),
    makeMnemonic: vi.fn(),
    listQuestions: vi.fn(),
    submitAttempt: vi.fn(),
    submitGrading: vi.fn(),
    getAttempt: vi.fn(),
    listGradingHistory: vi.fn(),
    getCommonErrors: vi.fn(),
    createMockExam: vi.fn(),
    getMockExam: vi.fn(),
    advanceMockStage: vi.fn(),
    pauseMockExam: vi.fn(),
    submitMockExam: vi.fn(),
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
  archived_at: null,
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
    apiMock.getKnowledgeTree.mockResolvedValue({ roots: [] });
    apiMock.getMasteryCoverage.mockResolvedValue({ coverage: 0, weak_top5: [] });
    apiMock.listDeadlines.mockResolvedValue({ items: [] });
    apiMock.listTasks.mockResolvedValue({ items: [] });
    apiMock.getProgress.mockResolvedValue({ by_track: {}, streak_days: 0, heatmap: [] });
    apiMock.listWeeklyReports.mockResolvedValue({ items: [] });
    apiMock.patchProfile.mockResolvedValue(profile("p1"));
    apiMock.listVocabToday.mockResolvedValue({ new_items: [], review_items: [] });
    apiMock.listQuestions.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 50 });
    apiMock.listGradingHistory.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 10 });
    apiMock.getCommonErrors.mockResolvedValue({ top3: [] });
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

  it("keeps the switcher's create card submittable (opening it is not a request in flight)", async () => {
    // Regression: one flag used to mean both "the inline card is open" and "a create is running",
    // so opening the card from the switcher handed `busy` to its submit and the button was
    // disabled before the user could ever click it. The empty-state path never showed it.
    render(<CampusStationView track="cet" />);
    await waitFor(() => expect(screen.getByTestId("campus-profile-switcher")).toBeTruthy());
    expect(screen.queryByTestId("campus-profile-create-card")).toBeNull();

    fireEvent.click(screen.getByTestId("campus-profile-create"));
    await waitFor(() => expect(screen.getByTestId("campus-profile-create-card")).toBeTruthy());
    const submit = screen.getByTestId("campus-profile-create-submit") as HTMLButtonElement;
    expect(submit.disabled).toBe(false);

    fireEvent.change(screen.getByTestId("campus-profile-create-title"), {
      target: { value: "第二个档案" },
    });
    fireEvent.click(submit);
    await waitFor(() => expect(apiMock.createProfile).toHaveBeenCalled());
    expect(apiMock.createProfile.mock.calls[0][0]).toMatchObject({ title: "第二个档案" });
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

  it("mounts the shared panels on every track and the kaoyan panels only where configured", async () => {
    render(<CampusStationView track="cet" />);
    await waitFor(() => expect(screen.getByTestId("campus-mistake-panel")).toBeTruthy());
    expect(screen.getByTestId("campus-review-queue")).toBeTruthy();
    expect(screen.queryByTestId("campus-library-panel")).toBeNull();
    cleanup();

    render(<CampusStationView track="kaoyan" />);
    await waitFor(() => expect(screen.getByTestId("campus-library-panel")).toBeTruthy());
    expect(screen.getByTestId("campus-major-qa-view")).toBeTruthy();
    await waitFor(() => expect(screen.getByTestId("campus-plan-editor")).toBeTruthy());
    expect(screen.getByTestId("campus-weekly-view")).toBeTruthy();
    expect(screen.getByTestId("campus-tutor-chat")).toBeTruthy();
    expect(screen.queryByTestId("campus-qa-panel")).toBeNull();
  });

  it("mounts the CET panels on the cet track", async () => {
    render(<CampusStationView track="cet" />);
    await waitFor(() => expect(screen.getByTestId("campus-station")).toBeTruthy());
    expect(screen.getByTestId("campus-cet-assessment-start")).toBeTruthy();
    expect(screen.getByTestId("campus-cet-vocab-empty")).toBeTruthy();
    expect(screen.getByTestId("campus-cet-listening-empty")).toBeTruthy();
    // One workshop per grading domain, each with its OWN testid: the station mounts both, so a
    // shared `campus-cet-grading-*` prefix put duplicate ids in one document.
    expect(screen.getByTestId("campus-cet-essay-grading-text")).toBeTruthy();
    expect(screen.getByTestId("campus-cet-translation-grading-text")).toBeTruthy();
    expect(screen.getAllByTestId("campus-cet-essay-grading-text")).toHaveLength(1);
    expect(screen.getByTestId("campus-mock-start")).toBeTruthy();
    expect(screen.getByTestId("campus-cet-common-errors")).toBeTruthy();
  });

  it("mounts the cert panels on the certificate station", async () => {
    render(<CampusStationView track="cert" />);
    await waitFor(() => expect(screen.getByTestId("campus-cert-tree-panel")).toBeTruthy());
    expect(screen.getByTestId("campus-cert-grading-panel")).toBeTruthy();
    expect(screen.getByTestId("campus-cert-setup-panel")).toBeTruthy();
    expect(screen.queryByTestId("campus-library-panel")).toBeNull();
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

  it("explains a duplicate title in a dialog and keeps the station on screen", async () => {
    apiMock.createProfile.mockRejectedValue(
      new CampusApiError("DUPLICATE_TITLE", "同名档案已存在：四级冲刺", false, 409),
    );
    render(<CampusStationView track="cet" />);
    await waitFor(() => expect(screen.getByTestId("campus-profile-switcher")).toBeTruthy());

    fireEvent.click(screen.getByTestId("campus-profile-create"));
    fireEvent.change(screen.getByTestId("campus-profile-create-title"), {
      target: { value: "四级冲刺" },
    });
    fireEvent.click(screen.getByTestId("campus-profile-create-submit"));

    const dialog = await screen.findByTestId("campus-profile-conflict");
    expect(dialog.textContent).toContain("A profile with this title already exists");
    expect(dialog.textContent).toContain("四级冲刺");
    expect(screen.queryByTestId("campus-station-error")).toBeNull();
    expect(screen.getByTestId("campus-station")).toBeTruthy();
    expect((screen.getByTestId("campus-profile-create-title") as HTMLInputElement).value).toBe(
      "四级冲刺",
    );

    fireEvent.click(screen.getByTestId("campus-profile-conflict-close"));
    await waitFor(() => expect(screen.queryByTestId("campus-profile-conflict")).toBeNull());
  });

  it("closes the conflict dialog with Escape", async () => {
    apiMock.createProfile.mockRejectedValue(
      new CampusApiError("DUPLICATE_TITLE", "同名档案已存在", false, 409),
    );
    render(<CampusStationView track="cet" />);
    await waitFor(() => expect(screen.getByTestId("campus-profile-switcher")).toBeTruthy());

    fireEvent.click(screen.getByTestId("campus-profile-create"));
    fireEvent.change(screen.getByTestId("campus-profile-create-title"), {
      target: { value: "四级冲刺" },
    });
    fireEvent.click(screen.getByTestId("campus-profile-create-submit"));
    await screen.findByTestId("campus-profile-conflict");

    fireEvent.keyDown(window, { key: "Escape" });
    await waitFor(() => expect(screen.queryByTestId("campus-profile-conflict")).toBeNull());
  });

  it("reports a refused archive in the dialog instead of swallowing the failure", async () => {
    apiMock.patchProfile.mockRejectedValue(
      new CampusApiError("PROFILE_READ_ONLY", "档案已结课，拒绝写入", false, 409),
    );
    render(<CampusStationView track="cet" />);
    await waitFor(() => expect(screen.getByTestId("campus-profile-archive-p1")).toBeTruthy());

    fireEvent.click(screen.getByTestId("campus-profile-archive-p1"));

    const dialog = await screen.findByTestId("campus-profile-conflict");
    expect(dialog.textContent).toContain("Profile is finished and read-only");
    expect(screen.getByTestId("campus-station")).toBeTruthy();
  });

  it("renders a skeleton while the profile list is in flight", () => {
    apiMock.listProfiles.mockReturnValue(new Promise(() => {}));
    render(<CampusStationView track="cet" />);
    expect(screen.getByTestId("campus-station-loading")).toBeTruthy();
  });
});
