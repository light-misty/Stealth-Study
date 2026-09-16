import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { CampusApiError } from "../../../campus/api";
import type { KnowledgePoint, KnowledgePointNode, MasteryCoverage } from "../../../campus/types";

vi.mock("../../../campus/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../../campus/api")>();
  return {
    ...actual,
    getKnowledgeTree: vi.fn(),
    createKnowledgePoint: vi.fn(),
    deleteKnowledgePoint: vi.fn(),
    setMastery: vi.fn(),
    getMasteryCoverage: vi.fn(),
  };
});

import * as api from "../../../campus/api";
import { KnowledgeTreePanel } from "./KnowledgeTreePanel";

const apiMock = api as unknown as Record<string, ReturnType<typeof vi.fn>>;

afterEach(cleanup);

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
  node("c1", { title: "chapter", question_count: 4, mistake_count: 2 }, [
    node("s1", { parent_id: "c1", title: "section" }, [
      node("k1", { parent_id: "s1", title: "leaf" }),
    ]),
  ]),
  node("c2", { title: "solo" }),
];

const coverage = (over: Partial<MasteryCoverage> = {}): MasteryCoverage => ({
  coverage: 0.4,
  weak_top5: [{ point_id: "k1", title: "leaf", level: "unknown" }],
  ...over,
});

const rowIds = () =>
  screen.getAllByTestId("campus-cert-tree-node").map((el) => el.getAttribute("data-id"));

const rowOf = (id: string) => {
  const row = screen
    .getAllByTestId("campus-cert-tree-node")
    .find((el) => el.getAttribute("data-id") === id);
  if (!row) throw new Error(`row ${id} not found`);
  return row;
};

describe("KnowledgeTreePanel", () => {
  beforeEach(() => {
    for (const key of [
      "getKnowledgeTree",
      "createKnowledgePoint",
      "deleteKnowledgePoint",
      "setMastery",
      "getMasteryCoverage",
    ]) {
      apiMock[key].mockReset();
    }
    apiMock.getKnowledgeTree.mockResolvedValue({ roots: tree() });
    apiMock.getMasteryCoverage.mockResolvedValue(coverage());
  });

  it("renders the three-layer tree with depths and live counts", async () => {
    render(<KnowledgeTreePanel profileId="p1" />);
    await waitFor(() => expect(rowIds()).toEqual(["c1", "s1", "k1", "c2"]));

    expect(rowOf("c1").getAttribute("data-depth")).toBe("1");
    expect(rowOf("s1").getAttribute("data-depth")).toBe("2");
    expect(rowOf("k1").getAttribute("data-depth")).toBe("3");
    expect(rowOf("c1").getAttribute("data-questions")).toBe("4");
    expect(rowOf("c1").getAttribute("data-mistakes")).toBe("2");
  });

  it("collapses and re-expands a branch", async () => {
    render(<KnowledgeTreePanel profileId="p1" />);
    await waitFor(() => expect(rowIds()).toEqual(["c1", "s1", "k1", "c2"]));

    fireEvent.click(within(rowOf("c1")).getByTestId("campus-cert-tree-toggle"));
    expect(rowIds()).toEqual(["c1", "c2"]);

    fireEvent.click(within(rowOf("c1")).getByTestId("campus-cert-tree-toggle"));
    expect(rowIds()).toEqual(["c1", "s1", "k1", "c2"]);
  });

  it("shows the coverage and the weak top5 with recorded levels", async () => {
    render(<KnowledgeTreePanel profileId="p1" />);
    await waitFor(() => expect(screen.getByTestId("campus-cert-tree-coverage")).toBeTruthy());
    expect(screen.getByTestId("campus-cert-tree-coverage").getAttribute("data-coverage")).toBe(
      "0.4",
    );
    expect(screen.getAllByTestId("campus-cert-tree-weak-row")).toHaveLength(1);
    const dots = within(rowOf("k1")).getByTestId("campus-mastery-dots");
    expect(dots.getAttribute("data-level")).toBe("unknown");
  });

  it("marks a mastery level through H5 and refreshes the coverage", async () => {
    apiMock.setMastery.mockResolvedValue({
      id: "m1",
      level: "mastered",
      point_id: "k1",
      dimension: null,
    });
    render(<KnowledgeTreePanel profileId="p1" />);
    await waitFor(() => expect(rowOf("k1")).toBeTruthy());

    fireEvent.click(within(rowOf("k1")).getByTestId("campus-cert-tree-level-mastered"));
    await waitFor(() =>
      expect(apiMock.setMastery).toHaveBeenCalledWith("p1", { pointId: "k1", level: "mastered" }),
    );
    await waitFor(() => expect(apiMock.getMasteryCoverage).toHaveBeenCalledTimes(2));
    await waitFor(() =>
      expect(within(rowOf("k1")).getByTestId("campus-mastery-dots").getAttribute("data-level")).toBe(
        "mastered",
      ),
    );
  });

  it("keeps the old level visible when the H5 write fails", async () => {
    apiMock.setMastery.mockRejectedValue(new CampusApiError("INVALID_LEVEL", "bad", false, 400));
    render(<KnowledgeTreePanel profileId="p1" />);
    await waitFor(() => expect(rowOf("k1")).toBeTruthy());

    fireEvent.click(within(rowOf("k1")).getByTestId("campus-cert-tree-level-fuzzy"));
    await waitFor(() => expect(screen.getByTestId("campus-cert-tree-error")).toBeTruthy());
    expect(
      within(rowOf("k1")).getByTestId("campus-mastery-dots").getAttribute("data-level"),
    ).toBe("unknown");
  });

  it("adds a child under a node through H2", async () => {
    apiMock.createKnowledgePoint.mockResolvedValue(point("s9", { parent_id: "c1", title: "new" }));
    render(<KnowledgeTreePanel profileId="p1" />);
    await waitFor(() => expect(rowIds()).toEqual(["c1", "s1", "k1", "c2"]));

    fireEvent.click(within(rowOf("c1")).getByTestId("campus-cert-tree-add"));
    fireEvent.change(screen.getByTestId("campus-cert-tree-add-title"), {
      target: { value: "new" },
    });
    fireEvent.click(screen.getByTestId("campus-cert-tree-add-submit"));

    await waitFor(() =>
      expect(apiMock.createKnowledgePoint).toHaveBeenCalledWith({
        profileId: "p1",
        title: "new",
        parent_id: "c1",
      }),
    );
    await waitFor(() => expect(rowIds()).toEqual(["c1", "s1", "k1", "s9", "c2"]));
  });

  it("adds a root node from the empty tree", async () => {
    apiMock.getKnowledgeTree.mockResolvedValue({ roots: [] });
    apiMock.createKnowledgePoint.mockResolvedValue(point("c9", { title: "root" }));
    render(<KnowledgeTreePanel profileId="p1" />);
    await waitFor(() => expect(screen.getByTestId("campus-cert-tree-empty")).toBeTruthy());

    fireEvent.click(screen.getByTestId("campus-cert-tree-add-root"));
    fireEvent.change(screen.getByTestId("campus-cert-tree-add-title"), {
      target: { value: "root" },
    });
    fireEvent.click(screen.getByTestId("campus-cert-tree-add-submit"));

    await waitFor(() =>
      expect(apiMock.createKnowledgePoint).toHaveBeenCalledWith({
        profileId: "p1",
        title: "root",
        parent_id: null,
      }),
    );
    await waitFor(() => expect(rowIds()).toEqual(["c9"]));
  });

  it("rejects a blank title without calling H2", async () => {
    render(<KnowledgeTreePanel profileId="p1" />);
    await waitFor(() => expect(rowIds()).toEqual(["c1", "s1", "k1", "c2"]));

    fireEvent.click(within(rowOf("c1")).getByTestId("campus-cert-tree-add"));
    fireEvent.change(screen.getByTestId("campus-cert-tree-add-title"), { target: { value: "  " } });
    fireEvent.click(screen.getByTestId("campus-cert-tree-add-submit"));

    expect(apiMock.createKnowledgePoint).not.toHaveBeenCalled();
    expect(screen.getByTestId("campus-cert-tree-error")).toBeTruthy();
  });

  it("stops offering child adds at the third layer", async () => {
    render(<KnowledgeTreePanel profileId="p1" />);
    await waitFor(() => expect(rowOf("k1")).toBeTruthy());

    expect(within(rowOf("k1")).queryByTestId("campus-cert-tree-add")).toBeNull();
    expect(within(rowOf("s1")).getByTestId("campus-cert-tree-add")).toBeTruthy();
  });

  it("keeps the form open and shows the error when H2 fails", async () => {
    apiMock.createKnowledgePoint.mockRejectedValue(refused());
    render(<KnowledgeTreePanel profileId="p1" />);
    await waitFor(() => expect(rowOf("c1")).toBeTruthy());

    fireEvent.click(within(rowOf("c1")).getByTestId("campus-cert-tree-add"));
    fireEvent.change(screen.getByTestId("campus-cert-tree-add-title"), { target: { value: "x" } });
    fireEvent.click(screen.getByTestId("campus-cert-tree-add-submit"));

    await waitFor(() => expect(screen.getByTestId("campus-cert-tree-error")).toBeTruthy());
    expect(screen.getByTestId("campus-cert-tree-add-title")).toBeTruthy();
    expect(rowIds()).toEqual(["c1", "s1", "k1", "c2"]);
  });

  it("deletes a node through H3 and refetches the tree", async () => {
    apiMock.deleteKnowledgePoint.mockResolvedValue({ deleted: true, orphaned_children: 0 });
    render(<KnowledgeTreePanel profileId="p1" />);
    await waitFor(() => expect(rowIds()).toEqual(["c1", "s1", "k1", "c2"]));

    fireEvent.click(within(rowOf("c2")).getByTestId("campus-cert-tree-delete"));
    await waitFor(() => expect(apiMock.deleteKnowledgePoint).toHaveBeenCalledWith("c2"));
    await waitFor(() => expect(apiMock.getKnowledgeTree).toHaveBeenCalledTimes(2));
  });

  it("shows the load error with a retry", async () => {
    apiMock.getKnowledgeTree.mockRejectedValue(
      new CampusApiError("MODEL_TIMEOUT", "timed out", true, 504),
    );
    render(<KnowledgeTreePanel profileId="p1" />);
    await waitFor(() => expect(screen.getByTestId("campus-cert-tree-error")).toBeTruthy());
    expect(screen.getByTestId("campus-cert-tree-retry")).toBeTruthy();
  });
});

const refused = () => new CampusApiError("ILLEGAL_TRANSITION", "nope", false, 409);
