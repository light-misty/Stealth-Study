import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { CapabilitiesReport } from "../../campus/types";
import { EmptyModelGuide } from "./EmptyModelGuide";

afterEach(cleanup);

const report = (
  currentModel: string | null,
  tasks: CapabilitiesReport["tasks"],
): CapabilitiesReport => ({ current_model: currentModel, tasks });

const row = (
  task: CapabilitiesReport["tasks"][number]["task"],
  supported: boolean,
  reason: string | null = null,
) => ({ task, recommended: "rec", minimum: "min", supported, reason });

describe("EmptyModelGuide", () => {
  it("stays silent while capabilities are unknown", () => {
    render(<EmptyModelGuide capabilities={null} />);
    expect(screen.queryByTestId("campus-empty-model-guide")).toBeNull();
  });

  it("stays silent when the current model supports everything", () => {
    render(
      <EmptyModelGuide
        capabilities={report("gpt-4o", [row("grading", true), row("question", true)])}
      />,
    );
    expect(screen.queryByTestId("campus-empty-model-guide")).toBeNull();
  });

  it("explains that no model is configured at all", () => {
    render(<EmptyModelGuide capabilities={report(null, [row("grading", false)])} />);
    const guide = screen.getByTestId("campus-empty-model-guide");
    expect(guide.getAttribute("data-reason")).toBe("no_model");
    expect(guide.textContent).toContain("No model configured");
  });

  it("lists only the tasks the current model cannot do", () => {
    render(
      <EmptyModelGuide
        capabilities={report("small-7b", [
          row("grading", false, "needs 16B+"),
          row("question", true),
          row("explain", false, null),
        ])}
      />,
    );
    const guide = screen.getByTestId("campus-empty-model-guide");
    expect(guide.getAttribute("data-reason")).toBe("unsupported");
    const rows = screen.getAllByTestId("campus-empty-model-task");
    expect(rows.map((r) => r.getAttribute("data-task"))).toEqual(["grading", "explain"]);
    expect(guide.textContent).toContain("needs 16B+");
  });
});
