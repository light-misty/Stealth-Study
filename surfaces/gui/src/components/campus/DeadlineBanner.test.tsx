import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { DeadlineView } from "../../campus/types";
import { DeadlineBanner } from "./DeadlineBanner";

afterEach(cleanup);

const view = (over: Partial<DeadlineView>): DeadlineView => ({
  id: "d1",
  node_type: "exam",
  date: "2026-10-20",
  days_left: 35,
  is_reference: false,
  ...over,
});

describe("DeadlineBanner", () => {
  it("keeps the countdown card on the rail with a blank number when nothing is registered", () => {
    render(<DeadlineBanner views={[]} />);
    const banner = screen.getByTestId("campus-deadline-banner");
    expect(banner.getAttribute("data-empty")).toBe("true");
    expect(banner.textContent).toContain("--");
    expect(screen.queryAllByTestId("campus-deadline-row")).toHaveLength(0);
  });

  it("counts down to the nearest node that has not passed and names it", () => {
    render(
      <DeadlineBanner
        views={[
          view({ id: "d1", node_type: "registration_close", date: "2026-09-25", days_left: 7 }),
          view({ id: "d2", node_type: "exam", date: "2026-11-01", days_left: 44 }),
        ]}
      />,
    );
    const banner = screen.getByTestId("campus-deadline-banner");
    expect(banner.getAttribute("data-empty")).toBe("false");
    expect(banner.querySelector(".hero-num")?.textContent).toBe("7");
    expect(banner.textContent).toContain("2026-09-25");
  });

  it("says the window has passed instead of counting negative days", () => {
    render(<DeadlineBanner views={[view({ id: "d1", days_left: -3 })]} />);
    const banner = screen.getByTestId("campus-deadline-banner");
    expect(banner.querySelector(".hero-num")).toBeNull();
    expect(banner.textContent).toContain("past");
  });

  it("lays each node out as name, date and days left", () => {
    render(
      <DeadlineBanner
        views={[view({ id: "d1", node_type: "exam", date: "2026-11-01", days_left: 44 })]}
      />,
    );
    const row = screen.getByTestId("campus-deadline-row");
    expect(
      Array.from(row.children)
        .map((cell) => cell.getAttribute("class"))
        .filter((name) => name !== null)
        .slice(0, 3),
    ).toEqual(["dl-name", "dl-date", "dl-left"]);
    expect(row.querySelector(".dl-date")?.textContent).toBe("11-01");
  });

  it("lists nodes soonest first", () => {
    render(
      <DeadlineBanner
        views={[
          view({ id: "d1", node_type: "exam", date: "2026-12-01", days_left: 77 }),
          view({ id: "d2", node_type: "registration_open", date: "2026-09-20", days_left: 5 }),
        ]}
      />,
    );
    const rows = screen.getAllByTestId("campus-deadline-row");
    expect(rows.map((r) => r.getAttribute("data-id"))).toEqual(["d2", "d1"]);
  });

  it("highlights the D-30 / D-7 / D-1 / D-day marks", () => {
    render(
      <DeadlineBanner
        views={[
          view({ id: "d0", days_left: 30 }),
          view({ id: "d1", days_left: 7 }),
          view({ id: "d2", days_left: 1 }),
          view({ id: "d3", days_left: 0 }),
          view({ id: "d4", days_left: 14 }),
        ]}
      />,
    );
    const rows = screen.getAllByTestId("campus-deadline-row");
    expect(rows.map((r) => r.getAttribute("data-highlight"))).toEqual([
      "true",
      "true",
      "true",
      "true",
      "false",
    ]);
  });

  it("marks a reference node as unofficial", () => {
    render(
      <DeadlineBanner
        views={[view({ id: "d1", is_reference: true }), view({ id: "d2", is_reference: false })]}
      />,
    );
    expect(screen.getAllByTestId("campus-deadline-reference")).toHaveLength(1);
  });

  it("spells out the node type instead of leaking the enum", () => {
    render(<DeadlineBanner views={[view({ node_type: "admission_ticket" })]} />);
    const row = screen.getByTestId("campus-deadline-row");
    expect(row.getAttribute("data-node-type")).toBe("admission_ticket");
    expect(row.textContent).not.toContain("admission_ticket");
    expect(row.textContent).not.toMatch(/^campus\./);
  });

  it("carries the backend deadline_snapshot tier on each row", () => {
    render(
      <DeadlineBanner
        views={[view({ id: "d1", days_left: 14, tier: "d30" }), view({ id: "d2", days_left: 3, tier: "d7" })]}
      />,
    );
    const rows = screen.getAllByTestId("campus-deadline-row");
    expect(rows.map((r) => r.getAttribute("data-tier"))).toEqual(["d30", "d7"]);
  });

  it("derives the tier from days_left when the snapshot omits it", () => {
    render(
      <DeadlineBanner
        views={[view({ id: "d1", days_left: 1 }), view({ id: "d2", days_left: 45 })]}
      />,
    );
    const rows = screen.getAllByTestId("campus-deadline-row");
    expect(rows.map((r) => r.getAttribute("data-tier"))).toEqual(["d1", "normal"]);
  });

  it("grades the bands through the data-tier hook plus a written count", () => {
    render(
      <DeadlineBanner
        views={[
          view({ id: "d1", days_left: 1, tier: "d1" }),
          view({ id: "d2", days_left: 5, tier: "d7" }),
          view({ id: "d3", days_left: 60, tier: "normal" }),
        ]}
      />,
    );
    const rows = screen.getAllByTestId("campus-deadline-row");
    const tiers = rows.map((r) => r.getAttribute("data-tier"));
    expect(new Set(tiers).size).toBe(3);
    // 分档上色由样式表按 [data-tier] 接管，所以组件这边要保证的是：每一档都挂得上钩子，
    // 而且剩余天数永远以文字给出 —— 颜色不是唯一线索（PRD §7.4）。
    for (const row of rows) {
      expect(row.className).toBe("dl-row");
      expect(row.querySelector(".dl-left")?.textContent).toMatch(/\d/);
    }
  });
});
