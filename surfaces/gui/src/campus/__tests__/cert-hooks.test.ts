import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { CampusApiError } from "../api";
import type {
  CertDeadline,
  KnowledgePoint,
  KnowledgePointNode,
  Mastery,
  MasteryCoverage,
} from "../types";

vi.mock("../api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api")>();
  return {
    ...actual,
    getKnowledgeTree: vi.fn(),
    createKnowledgePoint: vi.fn(),
    deleteKnowledgePoint: vi.fn(),
    setMastery: vi.fn(),
    getMasteryCoverage: vi.fn(),
    listDeadlines: vi.fn(),
    createDeadline: vi.fn(),
    createDeadlineReminders: vi.fn(),
  };
});

import * as api from "../api";
import { useCertDeadlines, useKnowledgeTree, useMasteryCoverage } from "../hooks";

const apiMock = api as unknown as Record<string, ReturnType<typeof vi.fn>>;

afterEach(() => {
  vi.clearAllMocks();
});

const point = (id: string, over: Partial<KnowledgePoint> = {}): KnowledgePoint => ({
  id,
  profile_id: "p1",
  title: `point-${id}`,
  parent_id: null,
  desc: null,
  order_index: 0,
  source: "manual",
  question_count: 0,
  mistake_count: 0,
  created_at: "2026-09-01T00:00:00Z",
  updated_at: "2026-09-01T00:00:00Z",
  ...over,
});

const node = (
  id: string,
  over: Partial<KnowledgePoint> = {},
  children: KnowledgePointNode[] = [],
): KnowledgePointNode => ({ ...point(id, over), children });

const tree = (): KnowledgePointNode[] => [
  node("c1", { title: "章一" }, [
    node("s1", { parent_id: "c1", title: "节一" }, [
      node("k1", { parent_id: "s1", title: "点一" }),
    ]),
  ]),
  node("c2", { title: "章二" }),
];

const coverage = (over: Partial<MasteryCoverage> = {}): MasteryCoverage => ({
  coverage: 0.4,
  weak_top5: [{ point_id: "k1", title: "点一", level: "unknown" }],
  ...over,
});

const deadline = (id: string, date: string, over: Partial<CertDeadline> = {}) => ({
  id,
  profile_id: "p1",
  node_type: "exam",
  date,
  is_reference: 0,
  automation_ids: [] as string[],
  note: "",
  created_at: "2026-09-01T00:00:00Z",
  updated_at: "2026-09-01T00:00:00Z",
  days_left: 20,
  ...over,
});

const masteryRow = (pointId: string, level: Mastery["level"]): Mastery => ({
  id: "m1",
  profile_id: "p1",
  level,
  point_id: pointId,
  dimension: null,
  score_0_100: null,
  evidence: "",
  updated_at: "2026-09-16T00:00:00Z",
});

const refused = () => new CampusApiError("ILLEGAL_TRANSITION", "nope", false, 409);

describe("useKnowledgeTree", () => {
  beforeEach(() => {
    apiMock.getKnowledgeTree.mockReset().mockResolvedValue({ roots: tree() });
    apiMock.createKnowledgePoint.mockReset();
    apiMock.deleteKnowledgePoint.mockReset();
    apiMock.setMastery.mockReset();
  });

  it("loads the nested tree from H1", async () => {
    const { result } = renderHook(() => useKnowledgeTree("p1"));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.roots.map((r) => r.id)).toEqual(["c1", "c2"]);
    expect(result.current.roots[0].children[0].children[0].id).toBe("k1");
  });

  it("skips the request without a profile", async () => {
    const { result } = renderHook(() => useKnowledgeTree(null));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(apiMock.getKnowledgeTree).not.toHaveBeenCalled();
    expect(result.current.roots).toEqual([]);
  });

  it("adds a point under its parent and keeps the tree shape", async () => {
    apiMock.createKnowledgePoint.mockResolvedValue(point("k2", { parent_id: "s1", title: "点二" }));
    const { result } = renderHook(() => useKnowledgeTree("p1"));
    await waitFor(() => expect(result.current.loading).toBe(false));

    const captured: (KnowledgePointNode | null)[] = [];
    await act(async () => {
      captured.push(await result.current.addPoint({ title: "点二", parentId: "s1" }));
    });
    expect(apiMock.createKnowledgePoint).toHaveBeenCalledWith({
      profileId: "p1",
      title: "点二",
      parent_id: "s1",
    });
    expect(captured[0]?.id).toBe("k2");
    const section = result.current.roots[0].children[0];
    expect(section.children.map((c) => c.id)).toEqual(["k1", "k2"]);
  });

  it("adds a root point when no parent is given", async () => {
    apiMock.createKnowledgePoint.mockResolvedValue(point("c3", { title: "章三" }));
    const { result } = renderHook(() => useKnowledgeTree("p1"));
    await waitFor(() => expect(result.current.loading).toBe(false));

    await act(async () => {
      await result.current.addPoint({ title: "章三" });
    });
    expect(result.current.roots.map((r) => r.id)).toEqual(["c1", "c2", "c3"]);
  });

  it("leaves the tree untouched when the create fails", async () => {
    apiMock.createKnowledgePoint.mockRejectedValue(refused());
    const { result } = renderHook(() => useKnowledgeTree("p1"));
    await waitFor(() => expect(result.current.loading).toBe(false));

    let created: KnowledgePointNode | null | undefined;
    await act(async () => {
      created = await result.current.addPoint({ title: "x", parentId: "s1" });
    });
    expect(created).toBeNull();
    expect(result.current.error).toBeTruthy();
    expect(result.current.roots[0].children[0].children.map((c) => c.id)).toEqual(["k1"]);
  });

  it("deletes a point and refetches the tree (orphans may re-root)", async () => {
    apiMock.deleteKnowledgePoint.mockResolvedValue({ deleted: true, orphaned_children: 1 });
    const { result } = renderHook(() => useKnowledgeTree("p1"));
    await waitFor(() => expect(result.current.loading).toBe(false));

    await act(async () => {
      await result.current.removePoint("c1");
    });
    expect(apiMock.deleteKnowledgePoint).toHaveBeenCalledWith("c1");
    await waitFor(() => expect(apiMock.getKnowledgeTree).toHaveBeenCalledTimes(2));
  });

  it("reports a failed delete without reloading", async () => {
    apiMock.deleteKnowledgePoint.mockRejectedValue(refused());
    const { result } = renderHook(() => useKnowledgeTree("p1"));
    await waitFor(() => expect(result.current.loading).toBe(false));

    let outcome: unknown;
    await act(async () => {
      outcome = await result.current.removePoint("c1");
    });
    expect(outcome).toBeNull();
    expect(result.current.error).toBeTruthy();
    expect(apiMock.getKnowledgeTree).toHaveBeenCalledTimes(1);
  });

  it("sets a point mastery through H5 and returns the stored row", async () => {
    apiMock.setMastery.mockResolvedValue(masteryRow("k1", "mastered"));
    const { result } = renderHook(() => useKnowledgeTree("p1"));
    await waitFor(() => expect(result.current.loading).toBe(false));

    const captured: (Mastery | null)[] = [];
    await act(async () => {
      captured.push(await result.current.setLevel("k1", "mastered"));
    });
    expect(apiMock.setMastery).toHaveBeenCalledWith("p1", { pointId: "k1", level: "mastered" });
    expect(captured[0]?.level).toBe("mastered");
  });

  it("returns null when the mastery write fails", async () => {
    apiMock.setMastery.mockRejectedValue(new CampusApiError("INVALID_LEVEL", "bad", false, 400));
    const { result } = renderHook(() => useKnowledgeTree("p1"));
    await waitFor(() => expect(result.current.loading).toBe(false));

    let stored: Mastery | null | undefined;
    await act(async () => {
      stored = await result.current.setLevel("k1", "mastered");
    });
    expect(stored).toBeNull();
    expect(result.current.error).toBeTruthy();
  });
});

describe("useMasteryCoverage", () => {
  it("loads coverage and the weak top5 from H6", async () => {
    apiMock.getMasteryCoverage.mockReset().mockResolvedValue(coverage());
    const { result } = renderHook(() => useMasteryCoverage("p1"));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.data?.coverage).toBe(0.4);
    expect(result.current.data?.weak_top5).toHaveLength(1);
  });

  it("stays empty without a profile", async () => {
    apiMock.getMasteryCoverage.mockReset();
    const { result } = renderHook(() => useMasteryCoverage(null));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(apiMock.getMasteryCoverage).not.toHaveBeenCalled();
    expect(result.current.data).toBeNull();
  });
});

describe("useCertDeadlines", () => {
  beforeEach(() => {
    apiMock.listDeadlines.mockReset().mockResolvedValue({
      items: [deadline("n1", "2026-10-01"), deadline("n2", "2026-10-20", { node_type: "exam" })],
    });
    apiMock.createDeadline.mockReset();
    apiMock.createDeadlineReminders.mockReset();
  });

  it("loads the node timeline from H8", async () => {
    const { result } = renderHook(() => useCertDeadlines("p1"));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.items.map((i) => i.id)).toEqual(["n1", "n2"]);
    expect(result.current.items[0].days_left).toBe(20);
  });

  it("appends the created node and refetches the timeline", async () => {
    apiMock.createDeadline.mockResolvedValue(deadline("n3", "2026-11-01"));
    const { result } = renderHook(() => useCertDeadlines("p1"));
    await waitFor(() => expect(result.current.loading).toBe(false));

    let created: unknown;
    await act(async () => {
      created = await result.current.createNode({
        profileId: "p1",
        nodeType: "score_query",
        date: "2026-11-01",
      });
    });
    expect(apiMock.createDeadline).toHaveBeenCalled();
    expect((created as { id: string }).id).toBe("n3");
    await waitFor(() => expect(apiMock.listDeadlines).toHaveBeenCalledTimes(2));
  });

  it("keeps the timeline and reports the error when the create fails", async () => {
    apiMock.createDeadline.mockRejectedValue(
      new CampusApiError("DUPLICATE_NODE", "dup", false, 409),
    );
    const { result } = renderHook(() => useCertDeadlines("p1"));
    await waitFor(() => expect(result.current.loading).toBe(false));

    let created: unknown;
    await act(async () => {
      created = await result.current.createNode({
        profileId: "p1",
        nodeType: "exam",
        date: "2026-11-01",
      });
    });
    expect(created).toBeNull();
    expect(result.current.error).toBeTruthy();
    expect(result.current.items).toHaveLength(2);
    expect(apiMock.listDeadlines).toHaveBeenCalledTimes(1);
  });

  it("stores the reminder ids on the node after H9", async () => {
    apiMock.createDeadlineReminders.mockResolvedValue({ automation_ids: ["a1", "a2", "a3"] });
    const { result } = renderHook(() => useCertDeadlines("p1"));
    await waitFor(() => expect(result.current.loading).toBe(false));

    let ids: string[] = [];
    await act(async () => {
      ids = (await result.current.createReminders("n1")) ?? [];
    });
    expect(apiMock.createDeadlineReminders).toHaveBeenCalledWith("n1");
    expect(ids).toEqual(["a1", "a2", "a3"]);
    expect(result.current.items.find((i) => i.id === "n1")?.automation_ids).toEqual([
      "a1",
      "a2",
      "a3",
    ]);
  });

  it("returns null when the reminder call fails", async () => {
    apiMock.createDeadlineReminders.mockRejectedValue(
      new CampusApiError("AUTOMATION_UNAVAILABLE", "no store", false, 503),
    );
    const { result } = renderHook(() => useCertDeadlines("p1"));
    await waitFor(() => expect(result.current.loading).toBe(false));

    let ids: string[] | null | undefined;
    await act(async () => {
      ids = await result.current.createReminders("n1");
    });
    expect(ids).toBeNull();
    expect(result.current.error).toBeTruthy();
  });
});
