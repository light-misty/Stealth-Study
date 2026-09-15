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
  useProfiles,
} from "../hooks";

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
    expect(apiMock.submitReviewResult).toHaveBeenCalledWith("r1", true);
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
    expect(apiMock.patchMistake).toHaveBeenCalledWith("m1", { attribution: "misread" });
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

  it("stops polling as soon as the document leaves the pending state", async () => {
    vi.useFakeTimers();
    apiMock.getLibraryDoc
      .mockResolvedValueOnce(doc("d1", "pending"))
      .mockResolvedValueOnce(doc("d1", "ready"));
    const seen: string[] = [];
    const stop = pollDocReady("d1", 1000, (d) => seen.push(d.parse_status));

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
