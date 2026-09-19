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
    createDeadline: vi.fn(),
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
    deleteProfile: vi.fn(),
    getProfileImpact: vi.fn(),
  };
});

import * as api from "../../campus/api";
import { clearCampusCache } from "../../campus/hooks";
import { localDay } from "../../campus/utils";
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
    clearCampusCache();
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

  it("does not leak the switcher's create card into another track", async () => {
    const { rerender } = render(<CampusStationView track="cet" />);
    await waitFor(() => expect(screen.getByTestId("campus-profile-switcher")).toBeTruthy());
    fireEvent.click(screen.getByTestId("campus-profile-create"));
    await waitFor(() => expect(screen.getByTestId("campus-profile-create-card")).toBeTruthy());

    rerender(<CampusStationView track="kaoyan" />);
    await waitFor(() =>
      expect(screen.getByTestId("campus-station").getAttribute("data-track")).toBe("kaoyan"),
    );
    expect(screen.queryByTestId("campus-profile-create-card")).toBeNull();
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

  it("moves the rail's countdown the moment a milestone is added", async () => {
    const node = {
      id: "d1",
      node_type: "registration_close",
      date: "2026-10-05",
      days_left: 16,
      is_reference: false,
    };
    apiMock.getReminders.mockResolvedValue({ banner: [], expired: [] });
    apiMock.listDeadlines.mockResolvedValue({ items: [] });
    apiMock.createDeadline.mockResolvedValue(node);
    render(<CampusStationView track="cert" />);
    await waitFor(() => expect(screen.getByTestId("campus-deadline-banner")).toBeTruthy());
    expect(screen.getByTestId("campus-deadline-banner").getAttribute("data-empty")).toBe("true");

    apiMock.getReminders.mockResolvedValue({ banner: [node], expired: [] });
    fireEvent.click(screen.getByTestId("campus-station-tab-cert_setup"));
    fireEvent.change(screen.getByTestId("campus-cert-setup-date"), {
      target: { value: "2026-10-05" },
    });
    fireEvent.click(screen.getByTestId("campus-cert-setup-create"));

    await waitFor(() => expect(apiMock.createDeadline).toHaveBeenCalled());
    await waitFor(() =>
      expect(screen.getByTestId("campus-deadline-banner").getAttribute("data-empty")).toBe("false"),
    );
    expect(screen.getByTestId("campus-deadline-banner").textContent).toContain("16");
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

  it("lays the first-paint skeleton out as the full station shell", () => {
    apiMock.listProfiles.mockReturnValue(new Promise(() => {}));
    apiMock.getAppState.mockReturnValue(new Promise(() => {}));
    render(<CampusStationView track="cet" />);
    const loading = screen.getByTestId("campus-station-loading");
    expect(loading.getAttribute("data-track")).toBe("cet");
    expect(screen.getByText("CET-4/6")).toBeTruthy();
    expect(loading.querySelectorAll(".st-tab").length).toBe(9);
    expect(loading.querySelectorAll(".st-rail .card").length).toBe(3);
  });

  it("opens the archived profiles from the station header and restores one", async () => {
    const boxed: ExamProfile = {
      ...profile("a1"),
      status: "archived",
      archived_at: "2026-09-05T00:00:00Z",
    };
    apiMock.listProfiles.mockResolvedValue({ items: [profile("p1"), boxed] });
    apiMock.patchProfile.mockImplementation(async (id: string, patch: { status?: string }) => ({
      ...profile(id),
      status: patch.status ?? "active",
    }));
    render(<CampusStationView track="cet" />);
    await waitFor(() => expect(screen.getByTestId("campus-profile-switcher")).toBeTruthy());

    const entry = screen.getByTestId("campus-profile-archived-entry");
    expect(entry.textContent).toContain("1");
    expect(screen.queryAllByTestId("campus-profile-item")).toHaveLength(1);

    fireEvent.click(entry);
    await screen.findByTestId("campus-archived-dialog");
    expect(screen.getByTestId("campus-archived-row-a1").textContent).toContain("四级冲刺");

    fireEvent.click(screen.getByTestId("campus-archived-restore-a1"));
    await waitFor(() => expect(apiMock.patchProfile).toHaveBeenCalledWith("a1", { status: "active" }));
    await waitFor(() => expect(apiMock.listProfiles.mock.calls.length).toBeGreaterThan(1));
  });

  const boxedA1 = (): ExamProfile => ({
    ...profile("a1"),
    status: "archived",
    archived_at: "2026-09-05T00:00:00Z",
  });

  /** A desk the delete can actually empty: A1 reads this array, A5 takes the row out of it. */
  const deskOf = (...items: ExamProfile[]) => {
    const desk = [...items];
    apiMock.listProfiles.mockImplementation(async () => ({ items: [...desk] }));
    apiMock.deleteProfile.mockImplementation(async (id: string) => {
      const index = desk.findIndex((p) => p.id === id);
      if (index < 0) throw new CampusApiError("PROFILE_NOT_FOUND", `档案不存在：${id}`, false, 404);
      desk.splice(index, 1);
      return {
        deleted: true,
        cascade: { exam_profile: 1 },
        automation_tasks: 0,
        export_files: 0,
      };
    });
    return desk;
  };

  it("counts what the delete takes before it is confirmed", async () => {
    deskOf(profile(), boxedA1());
    apiMock.getProfileImpact.mockResolvedValue({
      profile_id: "a1",
      cascade: { exam_profile: 1, source_doc: 1, doc_chunk: 4, mistake_book: 2 },
      automation_tasks: 1,
      export_files: 0,
    });
    render(<CampusStationView track="cet" />);
    await waitFor(() => expect(screen.getByTestId("campus-profile-switcher")).toBeTruthy());

    fireEvent.click(screen.getByTestId("campus-profile-archived-entry"));
    await screen.findByTestId("campus-archived-dialog");
    fireEvent.click(screen.getByTestId("campus-archived-delete-a1"));

    await screen.findByTestId("campus-delete-dialog");
    expect(apiMock.getProfileImpact).toHaveBeenCalledWith("a1");
    expect(screen.getByTestId("campus-delete-count").getAttribute("data-total")).toBe("9");
    expect(apiMock.deleteProfile).not.toHaveBeenCalled();

    fireEvent.click(screen.getByTestId("campus-delete-confirm"));
    await waitFor(() => expect(apiMock.deleteProfile).toHaveBeenCalledWith("a1"));
    await waitFor(() => expect(screen.queryByTestId("campus-delete-dialog")).toBeNull());
    await waitFor(() => expect(screen.queryByTestId("campus-archived-row-a1")).toBeNull());
  });

  it("keeps the confirmation on screen, with its cost still counted, when the delete is refused", async () => {
    deskOf(profile(), boxedA1());
    apiMock.getProfileImpact.mockResolvedValue({
      profile_id: "a1",
      cascade: { exam_profile: 1 },
      automation_tasks: 0,
      export_files: 0,
    });
    apiMock.deleteProfile.mockRejectedValue(
      new CampusApiError("PROFILE_NOT_FOUND", "档案不存在：a1", false, 404),
    );
    render(<CampusStationView track="cet" />);
    await waitFor(() => expect(screen.getByTestId("campus-profile-switcher")).toBeTruthy());

    fireEvent.click(screen.getByTestId("campus-profile-archived-entry"));
    await screen.findByTestId("campus-archived-dialog");
    fireEvent.click(screen.getByTestId("campus-archived-delete-a1"));
    await screen.findByTestId("campus-delete-dialog");

    fireEvent.click(screen.getByTestId("campus-delete-confirm"));
    await screen.findByTestId("campus-delete-error");
    expect(screen.getByTestId("campus-delete-error").textContent).toContain("Profile not found");
    expect(screen.getByTestId("campus-delete-dialog").textContent).toContain("四级冲刺");

    fireEvent.click(screen.getByTestId("campus-delete-cancel"));
    await waitFor(() => expect(screen.queryByTestId("campus-delete-dialog")).toBeNull());
    expect(screen.getByTestId("campus-archived-row-a1")).toBeTruthy();
  });

  it("deletes a finished profile from the switcher, where it can do nothing else", async () => {
    const done: ExamProfile = { ...profile("f1"), status: "finished" };
    deskOf(profile(), done);
    apiMock.getProfileImpact.mockResolvedValue({
      profile_id: "f1",
      cascade: { exam_profile: 1, attempt: 6 },
      automation_tasks: 0,
      export_files: 0,
    });
    render(<CampusStationView track="cet" />);
    await waitFor(() => expect(screen.getByTestId("campus-profile-switcher")).toBeTruthy());

    fireEvent.click(screen.getByTestId("campus-profile-delete-f1"));
    await screen.findByTestId("campus-delete-dialog");
    expect(screen.getByTestId("campus-delete-count").getAttribute("data-total")).toBe("7");
    fireEvent.click(screen.getByTestId("campus-delete-confirm"));

    await waitFor(() => expect(apiMock.deleteProfile).toHaveBeenCalledWith("f1"));
    await waitFor(() => expect(screen.queryByTestId("campus-profile-delete-f1")).toBeNull());
    expect(screen.getByTestId("campus-profile-item")).toBeTruthy();
  });

  it("hides the archived entry while nothing is archived", async () => {
    render(<CampusStationView track="cet" />);
    await waitFor(() => expect(screen.getByTestId("campus-station")).toBeTruthy());
    expect(screen.queryByTestId("campus-profile-archived-entry")).toBeNull();
  });

  it("renames an on-desk profile from the switcher", async () => {
    const twin = { ...profile("p2"), title: "已占用的名字" };
    apiMock.listProfiles.mockResolvedValue({ items: [profile("p1"), twin] });
    apiMock.patchProfile.mockResolvedValue({ ...profile("p1"), title: "改好了" });
    render(<CampusStationView track="cet" />);
    await waitFor(() => expect(screen.getByTestId("campus-profile-rename-p1")).toBeTruthy());

    fireEvent.click(screen.getByTestId("campus-profile-rename-p1"));
    const input = screen.getByTestId("campus-profile-rename-input") as HTMLInputElement;
    expect(input.value).toBe("四级冲刺");

    fireEvent.change(input, { target: { value: "已占用的名字" } });
    expect(screen.getByTestId("campus-profile-rename-error")).toBeTruthy();
    expect((screen.getByTestId("campus-profile-rename-save") as HTMLButtonElement).disabled).toBe(
      true,
    );

    fireEvent.change(input, { target: { value: "改好了" } });
    fireEvent.click(screen.getByTestId("campus-profile-rename-save"));

    await waitFor(() =>
      expect(apiMock.patchProfile).toHaveBeenCalledWith("p1", { title: "改好了" }),
    );
    await waitFor(() => expect(screen.queryByTestId("campus-profile-rename")).toBeNull());
  });

  it("renames a boxed profile from the archived list", async () => {
    const boxed = { ...profile("a1"), status: "archived" as const, archived_at: "2026-09-05T00:00:00Z" };
    apiMock.listProfiles.mockResolvedValue({ items: [profile("p1"), boxed] });
    apiMock.patchProfile.mockResolvedValue(boxed);
    render(<CampusStationView track="cet" />);
    await waitFor(() => expect(screen.getByTestId("campus-profile-archived-entry")).toBeTruthy());

    fireEvent.click(screen.getByTestId("campus-profile-archived-entry"));
    fireEvent.click(screen.getByTestId("campus-archived-rename-a1"));

    const input = screen.getByTestId("campus-profile-rename-input") as HTMLInputElement;
    expect(input.value).toBe("四级冲刺");
    fireEvent.change(input, { target: { value: "箱子里的新名" } });
    fireEvent.click(screen.getByTestId("campus-profile-rename-save"));
    await waitFor(() =>
      expect(apiMock.patchProfile).toHaveBeenCalledWith("a1", { title: "箱子里的新名" }),
    );
    expect(screen.getByTestId("campus-archived-dialog")).toBeTruthy();
  });

  it("restores a boxed profile under a new name when the desk took its old one", async () => {
    const boxed = { ...profile("a1"), status: "archived" as const, archived_at: "2026-09-05T00:00:00Z" };
    apiMock.listProfiles.mockResolvedValue({ items: [profile("p1"), boxed] });
    apiMock.patchProfile.mockImplementation(async (id: string, patch: { title?: string }) => {
      if (!patch.title) {
        throw new CampusApiError("DUPLICATE_TITLE", "同名档案已存在：四级冲刺", false, 409);
      }
      return { ...profile(id), status: "active", title: patch.title, archived_at: null };
    });
    render(<CampusStationView track="cet" />);
    await waitFor(() => expect(screen.getByTestId("campus-profile-archived-entry")).toBeTruthy());

    fireEvent.click(screen.getByTestId("campus-profile-archived-entry"));
    fireEvent.click(screen.getByTestId("campus-archived-restore-a1"));

    const dialog = await screen.findByTestId("campus-profile-conflict");
    expect(dialog.textContent).toContain("A profile with this title already exists");
    const input = screen.getByTestId("campus-profile-conflict-title") as HTMLInputElement;
    expect(input.value).toBe("四级冲刺 (2)");
    expect((screen.getByTestId("campus-profile-conflict-ok") as HTMLButtonElement).textContent).toContain(
      "Rename and restore",
    );

    fireEvent.change(input, { target: { value: "四级冲刺" } });
    expect(screen.getByTestId("campus-profile-conflict-error")).toBeTruthy();
    expect((screen.getByTestId("campus-profile-conflict-ok") as HTMLButtonElement).disabled).toBe(
      true,
    );

    fireEvent.change(input, { target: { value: "回归档案" } });
    fireEvent.click(screen.getByTestId("campus-profile-conflict-ok"));

    await waitFor(() =>
      expect(apiMock.patchProfile).toHaveBeenCalledWith("a1", {
        status: "active",
        title: "回归档案",
      }),
    );
    await waitFor(() => expect(screen.queryByTestId("campus-profile-conflict")).toBeNull());
  });

  it("still offers the archived profiles when every profile of the station is archived", async () => {
    const boxed = { ...profile("a1"), status: "archived" as const };
    apiMock.listProfiles.mockResolvedValue({ items: [boxed] });
    apiMock.getAppState.mockResolvedValue({ active_profile_id: "a1", settings: {} });
    render(<CampusStationView track="cet" />);

    await waitFor(() => expect(screen.getByTestId("campus-station-empty")).toBeTruthy());
    fireEvent.click(screen.getByTestId("campus-profile-archived-entry"));
    await screen.findByTestId("campus-archived-dialog");
    expect(screen.getByTestId("campus-archived-row-a1")).toBeTruthy();
  });

  it("shows one module per screen and switches on the tab", async () => {
    render(<CampusStationView track="cet" />);
    await waitFor(() => expect(screen.getByTestId("campus-station")).toBeTruthy());

    const pane = (key: string) => screen.getByTestId(`campus-station-pane-${key}`);
    expect(pane("mistake").hasAttribute("hidden")).toBe(false);
    expect(pane("vocab").hasAttribute("hidden")).toBe(true);

    fireEvent.click(screen.getByTestId("campus-station-tab-vocab"));
    expect(pane("mistake").hasAttribute("hidden")).toBe(true);
    expect(pane("vocab").hasAttribute("hidden")).toBe(false);
    expect(screen.getByTestId("campus-station-tab-vocab").getAttribute("aria-selected")).toBe(
      "true",
    );
    expect(screen.getByTestId("campus-station-tab-mistake").getAttribute("aria-selected")).toBe(
      "false",
    );
  });

  it("walks the tab strip with the arrow keys", async () => {
    render(<CampusStationView track="cet" />);
    await waitFor(() => expect(screen.getByTestId("campus-station-tab-mistake")).toBeTruthy());

    const tabs = screen.getByRole("tablist");
    fireEvent.keyDown(tabs, { key: "ArrowRight" });
    expect(screen.getByTestId("campus-station-pane-review").hasAttribute("hidden")).toBe(false);
    fireEvent.keyDown(tabs, { key: "End" });
    expect(screen.getByTestId("campus-station-pane-common-errors").hasAttribute("hidden")).toBe(
      false,
    );
    fireEvent.keyDown(tabs, { key: "Home" });
    expect(screen.getByTestId("campus-station-pane-mistake").hasAttribute("hidden")).toBe(false);
  });

  it("keeps every panel mounted, so a hidden module keeps its own loaded state", async () => {
    render(<CampusStationView track="cet" />);
    await waitFor(() => expect(screen.getByTestId("campus-station")).toBeTruthy());
    // The mock-exam console is three tabs in; it must already exist, not mount on demand.
    expect(screen.getByTestId("campus-station-pane-mock")).toBeTruthy();
    fireEvent.click(screen.getByTestId("campus-station-tab-mock"));
    expect(screen.getByTestId("campus-station-pane-mock").hasAttribute("hidden")).toBe(false);
  });

  it("badges the review tab and jumps there from the rail's quick action", async () => {
    apiMock.listDueReviews.mockResolvedValue({
      items: [
        {
          id: "r1",
          profile_id: "p1",
          item_type: "vocab",
          item_id: "v1",
          interval_days: 4,
          ease: 2.5,
          reps: 1,
          streak_right: 1,
          next_due: "2026-09-19",
          payload: { word: "abandon" },
        },
      ],
    });
    render(<CampusStationView track="cet" />);
    const tab = await screen.findByTestId("campus-station-tab-review");
    expect(tab.textContent).toContain("1");

    fireEvent.click(screen.getByTestId("campus-station-goto-review"));
    expect(screen.getByTestId("campus-station-pane-review").hasAttribute("hidden")).toBe(false);
    expect(screen.getByTestId("campus-station-pane-mistake").hasAttribute("hidden")).toBe(true);
  });

  it("fills the rail's four rows from today's report, in the desk's own order", async () => {
    apiMock.getProgress.mockResolvedValue({
      by_track: { politics: { done: 3, total: 8, rate: 0.375 } },
      streak_days: 5,
      heatmap: [{ date: localDay(new Date()), count: 4 }],
      today: {
        date: "2026-09-19",
        minutes: { done: 42, plan: 90 },
        tasks: { done: 2, total: 8 },
        review: { done: 1, total: 4 },
        grading: { done: 0, total: 1 },
        vocab: { done: 12, quota: 20 },
        docs: { ready: 4, total: 5 },
        knowledge: { mastered: 6, total: 10 },
      },
    });
    render(<CampusStationView track="cet" />);

    await waitFor(() => expect(screen.getByTestId("campus-station-progress")).toBeTruthy());
    // 卡头的百分比就是首行时长的比例，与设计稿一致。
    expect(screen.getByTestId("campus-station-progress-rate").textContent).toBe("47%");
    expect(
      screen
        .getAllByTestId("campus-station-progress-row")
        .map((row) => [row.getAttribute("data-row"), row.querySelector(".prog-v")?.textContent]),
    ).toEqual([
      ["minutes", "42/90"],
      ["vocab", "12/20"],
      ["review", "1/4"],
      ["grading", "0/1"],
    ]);
    expect(screen.getByTestId("campus-station-goto-review")).toBeTruthy();
    expect(screen.getByTestId("campus-station-streak").textContent).toContain("5");
    const cells = screen.getAllByTestId("campus-station-heat-cell");
    expect(cells).toHaveLength(21);
    // 窗口从今天往回数，所以今天那一格落在最后。
    expect(cells[cells.length - 1].getAttribute("class")).toContain("hc--3");
    expect(cells[0].getAttribute("class")).toBe("hc");
    expect(screen.getByTestId("campus-station-checkin").textContent).toContain("1");
  });

  it("keeps all three rail cards on the desk when the report is empty", async () => {
    apiMock.getProgress.mockResolvedValue({ by_track: {}, streak_days: 0, heatmap: [] });
    render(<CampusStationView track="cet" />);
    await waitFor(() => expect(screen.getByTestId("campus-station")).toBeTruthy());

    expect(screen.getByTestId("campus-countdown-banner")).toBeTruthy();
    expect(screen.getByTestId("campus-station-progress")).toBeTruthy();
    expect(screen.getByTestId("campus-station-streak")).toBeTruthy();
    expect(
      screen
        .getAllByTestId("campus-station-progress-row")
        .map((row) => row.querySelector(".prog-v")?.textContent),
    ).toEqual(["0/0", "0/0", "0/0", "0/0"]);
    expect(
      screen.getAllByTestId("campus-station-progress-row")[0].querySelector(".prog-k")?.textContent,
    ).toBe("Minutes");
    expect(screen.getByTestId("campus-station-progress-rate").textContent).toBe("0%");
    expect(screen.getAllByTestId("campus-station-heat-cell")).toHaveLength(21);
  });

  it("remounts from cache without flashing the loading skeleton", async () => {
    render(<CampusStationView track="cet" />);
    await waitFor(() => expect(screen.getByTestId("campus-station")).toBeTruthy());
    cleanup();

    apiMock.listProfiles.mockReturnValue(new Promise(() => {}));
    apiMock.getAppState.mockReturnValue(new Promise(() => {}));

    render(<CampusStationView track="cet" />);
    expect(screen.queryByTestId("campus-station-loading")).toBeNull();
    expect(screen.getByTestId("campus-station")).toBeTruthy();
    expect(screen.getByTestId("campus-station").getAttribute("data-track")).toBe("cet");
  });
});
