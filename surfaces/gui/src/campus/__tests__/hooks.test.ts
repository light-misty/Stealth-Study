import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { CampusApiError } from "../api";
import type {
  ExamProfile,
  LibraryQAAnswer,
  MistakeBookEntry,
  ReviewDueItem,
  SourceDoc,
} from "../types";

vi.mock("../api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api")>();
  return {
    ...actual,
    listProfiles: vi.fn(),
    getAppState: vi.fn(),
    patchAppState: vi.fn(),
    getCapabilities: vi.fn(),
    listDueReviews: vi.fn(),
    submitReviewResult: vi.fn(),
    listMistakes: vi.fn(),
    patchMistake: vi.fn(),
    listLibraryDocs: vi.fn(),
    getLibraryDoc: vi.fn(),
    importLibraryDoc: vi.fn(),
    retryLibraryDoc: vi.fn(),
    deleteLibraryDoc: vi.fn(),
    askLibrary: vi.fn(),
    getReminders: vi.fn(),
    listTasks: vi.fn(),
    getProgress: vi.fn(),
    listWeeklyReports: vi.fn(),
    generateWeeklyReport: vi.fn(),
  };
});

import * as api from "../api";
import {
  pollDocReady,
  useActiveProfile,
  useCapabilities,
  useDeadlineViews,
  useDueReviews,
  useLibraryDocs,
  useLibraryQA,
  useMistakes,
  usePlanProgress,
  usePlanTasks,
  useProfiles,
  useWeeklyReports,
} from "../hooks";
import type { PlanTask, ProgressReport, WeeklyReport } from "../types";

const apiMock = api as unknown as Record<string, ReturnType<typeof vi.fn>>;

const profile = (id: string, status: ExamProfile["status"] = "active"): ExamProfile => ({
  id,
  track_type: "cet",
  title: `profile-${id}`,
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

const dueItem = (id: string): ReviewDueItem => ({
  id,
  profile_id: "p1",
  item_type: "mistake",
  item_id: "m1",
  due_at: "2026-09-15T00:00:00Z",
  interval_days: 1,
  streak_right: 0,
  ease: 2.5,
  status: "pending",
  last_reviewed_at: null,
  created_at: "2026-09-01T00:00:00Z",
  payload: { word: "abandon" },
});

const mistake = (id: string, attribution = "pending"): MistakeBookEntry => ({
  id,
  profile_id: "p1",
  attempt_id: "a1",
  track_type: "cet",
  subject: "reading",
  question_id: null,
  point_id: null,
  attribution: attribution as MistakeBookEntry["attribution"],
  attribution_confidence: null,
  wrong_count: 1,
  last_wrong_at: "2026-09-01T00:00:00Z",
  resolved: 0,
  note: "",
  created_at: "2026-09-01T00:00:00Z",
  updated_at: "2026-09-01T00:00:00Z",
});

const doc = (id: string, parseStatus: SourceDoc["parse_status"] = "pending"): SourceDoc => ({
  id,
  profile_id: "p1",
  title: `${id}.pdf`,
  file_path: `/tmp/${id}.pdf`,
  file_type: "pdf",
  page_count: 3,
  parse_status: parseStatus,
  fail_reason: parseStatus === "failed" ? "no_text_layer" : null,
  chunk_count: 0,
  char_count: 0,
  imported_at: "2026-09-01T00:00:00Z",
});

beforeEach(() => {
  for (const fn of Object.values(apiMock)) if (typeof fn?.mockReset === "function") fn.mockReset();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("useProfiles", () => {
  it("loads the profile list and exposes loading then data", async () => {
    apiMock.listProfiles.mockResolvedValue({ items: [profile("p1")] });
    const { result } = renderHook(() => useProfiles());

    expect(result.current.loading).toBe(true);
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.profiles.map((p: ExamProfile) => p.id)).toEqual(["p1"]);
    expect(apiMock.listProfiles).toHaveBeenCalledWith(undefined);
  });

  it("reloads on demand and surfaces the structured error", async () => {
    apiMock.listProfiles.mockResolvedValueOnce({ items: [] });
    const { result } = renderHook(() => useProfiles("cet"));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.profiles).toEqual([]);

    apiMock.listProfiles.mockRejectedValueOnce(
      new CampusApiError("MODEL_TIMEOUT", "timeout", true, 504),
    );
    await act(async () => {
      result.current.reload();
    });
    await waitFor(() => expect(result.current.error).toBeTruthy());
    expect(result.current.retryable).toBe(true);
    expect(apiMock.listProfiles).toHaveBeenLastCalledWith("cet");
  });
});

describe("useActiveProfile", () => {
  it("resolves the profile recorded in app state", async () => {
    apiMock.getAppState.mockResolvedValue({ active_profile_id: "p2", settings: {} });
    const profiles = [profile("p1"), profile("p2")];
    const { result } = renderHook(() => useActiveProfile(profiles));

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.profile?.id).toBe("p2");
  });

  it("falls back to the first active profile when app state is empty or stale", async () => {
    apiMock.getAppState.mockResolvedValue({ active_profile_id: "ghost", settings: {} });
    const profiles = [profile("p1", "archived"), profile("p2")];
    const { result } = renderHook(() => useActiveProfile(profiles));

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.profile?.id).toBe("p2");
  });

  it("writes a switch back through app state (A7)", async () => {
    apiMock.getAppState.mockResolvedValue({ active_profile_id: "p1", settings: {} });
    apiMock.patchAppState.mockResolvedValue({ active_profile_id: "p2", settings: {} });
    const { result } = renderHook(() => useActiveProfile([profile("p1"), profile("p2")]));
    await waitFor(() => expect(result.current.loading).toBe(false));

    await act(async () => {
      await result.current.setActive("p2");
    });
    expect(apiMock.patchAppState).toHaveBeenCalledWith({ active_profile_id: "p2" });
    expect(result.current.profile?.id).toBe("p2");
  });
});

describe("useDueReviews", () => {
  it("lists due items and drops one optimistically after a result", async () => {
    apiMock.listDueReviews.mockResolvedValue({ items: [dueItem("r1"), dueItem("r2")] });
    apiMock.submitReviewResult.mockResolvedValue({ ...dueItem("r1"), status: "done" });
    const { result } = renderHook(() => useDueReviews("p1"));
    await waitFor(() => expect(result.current.items).toHaveLength(2));

    await act(async () => {
      await result.current.submit("r1", true);
    });
    expect(apiMock.submitReviewResult).toHaveBeenCalledWith("p1", "r1", true);
    expect(result.current.items.map((i: ReviewDueItem) => i.id)).toEqual(["r2"]);
  });

  it("restores the item and reports the error when the write fails", async () => {
    apiMock.listDueReviews.mockResolvedValue({ items: [dueItem("r1")] });
    apiMock.submitReviewResult.mockRejectedValue(
      new CampusApiError("RQ_NOT_FOUND", "gone", false, 404),
    );
    const { result } = renderHook(() => useDueReviews("p1"));
    await waitFor(() => expect(result.current.items).toHaveLength(1));

    await act(async () => {
      await result.current.submit("r1", false);
    });
    expect(result.current.items.map((i: ReviewDueItem) => i.id)).toEqual(["r1"]);
    expect(result.current.error).toBeInstanceOf(CampusApiError);
  });
});

describe("useMistakes", () => {
  it("lists mistakes and re-attributes one in place", async () => {
    apiMock.listMistakes.mockResolvedValue({ items: [mistake("m1")], total: 1 });
    apiMock.patchMistake.mockResolvedValue(mistake("m1", "misread"));
    const { result } = renderHook(() => useMistakes("p1"));
    await waitFor(() => expect(result.current.items).toHaveLength(1));

    await act(async () => {
      await result.current.setAttribution("m1", "misread");
    });
    expect(apiMock.patchMistake).toHaveBeenCalledWith("p1", "m1", { attribution: "misread" });
    expect(result.current.items[0].attribution).toBe("misread");
  });

  it("keeps the row untouched when the patch fails", async () => {
    apiMock.listMistakes.mockResolvedValue({ items: [mistake("m1")], total: 1 });
    apiMock.patchMistake.mockRejectedValue(new Error("offline"));
    const { result } = renderHook(() => useMistakes("p1"));
    await waitFor(() => expect(result.current.items).toHaveLength(1));

    await act(async () => {
      await result.current.setAttribution("m1", "misread");
    });
    expect(result.current.items[0].attribution).toBe("pending");
    expect(result.current.error).toBeInstanceOf(Error);
  });
});

describe("useLibraryDocs", () => {
  it("imports, retries and removes docs against the local list", async () => {
    apiMock.listLibraryDocs.mockResolvedValue({ items: [doc("d1")] });
    apiMock.importLibraryDoc.mockResolvedValue(doc("d2"));
    apiMock.retryLibraryDoc.mockResolvedValue(doc("d1", "ready"));
    apiMock.deleteLibraryDoc.mockResolvedValue({ deleted: true });
    const { result } = renderHook(() => useLibraryDocs("p1"));
    await waitFor(() => expect(result.current.items).toHaveLength(1));

    await act(async () => {
      await result.current.importDoc({ name: "d2.pdf" } as unknown as File);
    });
    expect(result.current.items.map((d: SourceDoc) => d.id)).toEqual(["d1", "d2"]);

    await act(async () => {
      await result.current.retry("d1");
    });
    expect(result.current.items[0].parse_status).toBe("ready");

    await act(async () => {
      await result.current.remove("d1");
    });
    expect(result.current.items.map((d: SourceDoc) => d.id)).toEqual(["d2"]);
  });

  it("merges a document fetched by the poll back into the list", async () => {
    apiMock.listLibraryDocs.mockResolvedValue({ items: [doc("d1", "pending")] });
    const { result } = renderHook(() => useLibraryDocs("p1"));
    await waitFor(() => expect(result.current.items).toHaveLength(1));

    act(() => {
      result.current.applyDoc(doc("d1", "ready"));
    });
    expect(result.current.items[0].parse_status).toBe("ready");
    expect(result.current.items).toHaveLength(1);
  });

  it("stops polling as soon as the document leaves the pending state", async () => {
    vi.useFakeTimers();
    apiMock.getLibraryDoc
      .mockResolvedValueOnce(doc("d1", "pending"))
      .mockResolvedValueOnce(doc("d1", "ready"));
    const seen: string[] = [];
    const stop = pollDocReady("p1", "d1", 1000, (d) => seen.push(d.parse_status));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    expect(seen).toEqual(["pending"]);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    expect(seen).toEqual(["pending", "ready"]);
    expect(apiMock.getLibraryDoc).toHaveBeenCalledTimes(2);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });
    expect(apiMock.getLibraryDoc).toHaveBeenCalledTimes(2);
    stop();
  });
});

describe("useLibraryQA", () => {
  it("asks a question and keeps the citations", async () => {
    const answer: LibraryQAAnswer = {
      answer: "see page 3",
      citations: [{ doc_id: "d1", page_no: 3, snippet: "…" }],
      used_retrieval: "keyword",
      chunks_used: 4,
    };
    apiMock.askLibrary.mockResolvedValue(answer);
    const { result } = renderHook(() => useLibraryQA("p1"));
    await act(async () => {
      await result.current.ask("what is on page 3?");
    });
    expect(apiMock.askLibrary).toHaveBeenCalledWith("p1", "what is on page 3?", undefined);
    expect(result.current.answer?.citations).toHaveLength(1);
    expect(result.current.asking).toBe(false);
  });

  it("clears the asking flag and reports failures", async () => {
    apiMock.askLibrary.mockRejectedValue(new CampusApiError("DOC_NOT_READY", "busy", true, 409));
    const { result } = renderHook(() => useLibraryQA("p1"));
    await act(async () => {
      await result.current.ask("?");
    });
    expect(result.current.asking).toBe(false);
    expect(result.current.error).toBeInstanceOf(CampusApiError);
    expect(result.current.answer).toBeNull();
  });
});

describe("useDeadlineViews", () => {
  it("reads the banner feed from H10", async () => {
    apiMock.getReminders.mockResolvedValue({
      banner: [{ id: "d1", node_type: "exam", date: "2026-10-20", days_left: 35, is_reference: false }],
      expired: [],
    });
    const { result } = renderHook(() => useDeadlineViews("p1"));
    await waitFor(() => expect(result.current.views).toHaveLength(1));
    expect(result.current.views[0].days_left).toBe(35);
  });

  it("stays empty without a profile instead of firing a request", async () => {
    const { result } = renderHook(() => useDeadlineViews(null));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.views).toEqual([]);
    expect(apiMock.getReminders).not.toHaveBeenCalled();
  });
});

describe("useCapabilities", () => {
  it("loads the capability report used by EmptyModelGuide", async () => {
    apiMock.getCapabilities.mockResolvedValue({
      current_model: "gpt-4o-mini",
      tasks: [{ task: "grading", recommended: "x", minimum: "y", supported: false, reason: "weak" }],
    });
    const { result } = renderHook(() => useCapabilities());
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.capabilities?.current_model).toBe("gpt-4o-mini");
  });
});

const planTask = (
  id: string,
  overrides: Partial<PlanTask> = {},
): PlanTask => ({
  id,
  plan_id: "plan-1",
  profile_id: "p1",
  title: `task-${id}`,
  detail: "",
  subject: "politics",
  scheduled_date: "2026-09-07",
  est_minutes: 60,
  priority: 2,
  status: "todo",
  board_card_id: null,
  completed_at: null,
  created_at: "2026-09-01T00:00:00Z",
  updated_at: "2026-09-01T00:00:00Z",
  ...overrides,
});

const weeklyReport = (id: string, overrides: Partial<WeeklyReport> = {}): WeeklyReport => ({
  id,
  profile_id: "p1",
  week_start: "2026-09-07",
  week_end: "2026-09-13",
  completion_rate: { overall: 0.5, politics: 0.4, english: 0.6 },
  top_mistake_points: [{ point_id: "kp1", title: "马原", count: 3 }],
  suggestion: "下周优先补政治",
  content_md: "# 一、总览\n…",
  created_at: "2026-09-13T00:00:00Z",
  ...overrides,
});

const progressReport = (): ProgressReport => ({
  by_track: {
    overall: { done: 5, total: 20, rate: 0.25 },
    politics: { done: 2, total: 10, rate: 0.2 },
  },
  streak_days: 3,
  heatmap: [{ date: "2026-09-10", count: 2 }],
});

describe("usePlanTasks", () => {
  it("loads the plan tasks for the profile", async () => {
    apiMock.listTasks.mockResolvedValue({ items: [planTask("t1"), planTask("t2")] });
    const { result } = renderHook(() => usePlanTasks("p1"));
    expect(result.current.loading).toBe(true);
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(apiMock.listTasks).toHaveBeenCalledWith("p1");
    expect(result.current.items.map((task: PlanTask) => task.id)).toEqual(["t1", "t2"]);
  });

  it("skips the request without a profile", async () => {
    const { result } = renderHook(() => usePlanTasks(null));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.items).toEqual([]);
    expect(apiMock.listTasks).not.toHaveBeenCalled();
  });

  it("surfaces a structured error and reloads on demand", async () => {
    apiMock.listTasks.mockRejectedValue(new CampusApiError("PROFILE_NOT_FOUND", "gone", false, 404));
    const { result } = renderHook(() => usePlanTasks("p1"));
    await waitFor(() => expect(result.current.error).toBeTruthy());
    expect(result.current.retryable).toBe(false);

    apiMock.listTasks.mockResolvedValue({ items: [planTask("t1")] });
    await act(async () => {
      result.current.reload();
    });
    await waitFor(() => expect(result.current.items).toHaveLength(1));
    expect(result.current.error).toBeNull();
  });
});

describe("usePlanProgress", () => {
  it("loads the progress report", async () => {
    apiMock.getProgress.mockResolvedValue(progressReport());
    const { result } = renderHook(() => usePlanProgress("p1"));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(apiMock.getProgress).toHaveBeenCalledWith("p1");
    expect(result.current.progress?.streak_days).toBe(3);
  });

  it("skips the request without a profile", async () => {
    const { result } = renderHook(() => usePlanProgress(null));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.progress).toBeNull();
    expect(apiMock.getProgress).not.toHaveBeenCalled();
  });
});

describe("useWeeklyReports", () => {
  it("loads the report list and prepends a generated report", async () => {
    apiMock.listWeeklyReports.mockResolvedValue({ items: [weeklyReport("w1")] });
    apiMock.generateWeeklyReport.mockResolvedValue(weeklyReport("w2"));
    const { result } = renderHook(() => useWeeklyReports("p1"));
    await waitFor(() => expect(result.current.items).toHaveLength(1));

    await act(async () => {
      await result.current.generate();
    });
    expect(apiMock.generateWeeklyReport).toHaveBeenCalledWith("p1");
    expect(result.current.items.map((report: WeeklyReport) => report.id)).toEqual(["w2", "w1"]);
    expect(result.current.generating).toBe(false);
  });

  it("replaces the same week entry on regenerate (UPSERT keeps the row id)", async () => {
    apiMock.listWeeklyReports.mockResolvedValue({ items: [weeklyReport("w1")] });
    apiMock.generateWeeklyReport.mockResolvedValue(weeklyReport("w1", { suggestion: "更新" }));
    const { result } = renderHook(() => useWeeklyReports("p1"));
    await waitFor(() => expect(result.current.items).toHaveLength(1));

    await act(async () => {
      await result.current.generate();
    });
    expect(result.current.items).toHaveLength(1);
    expect(result.current.items[0].suggestion).toBe("更新");
  });

  it("reports the generate error and keeps the list", async () => {
    apiMock.listWeeklyReports.mockResolvedValue({ items: [weeklyReport("w1")] });
    apiMock.generateWeeklyReport.mockRejectedValue(
      new CampusApiError("NO_TASK_DATA", "empty", false, 409),
    );
    const { result } = renderHook(() => useWeeklyReports("p1"));
    await waitFor(() => expect(result.current.items).toHaveLength(1));

    await act(async () => {
      await result.current.generate();
    });
    expect(result.current.genError).toBeTruthy();
    expect(result.current.items).toHaveLength(1);
  });

  it("does not fire a generate without a profile", async () => {
    apiMock.listWeeklyReports.mockResolvedValue({ items: [] });
    const { result } = renderHook(() => useWeeklyReports(null));
    await waitFor(() => expect(result.current.loading).toBe(false));

    await act(async () => {
      await result.current.generate();
    });
    expect(apiMock.generateWeeklyReport).not.toHaveBeenCalled();
  });
});
