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
  it("renders nothing when there is no node to show", () => {
    render(<DeadlineBanner views={[]} />);
    expect(screen.queryByTestId("campus-deadline-banner")).toBeNull();
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
});
