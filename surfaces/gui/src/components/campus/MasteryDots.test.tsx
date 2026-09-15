import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { MASTERY_LEVELS } from "../../campus/types";
import { MasteryDots } from "./MasteryDots";

afterEach(cleanup);

describe("MasteryDots", () => {
  it("renders one dot per level and marks the current one", () => {
    render(<MasteryDots level="fuzzy" />);
    const dots = screen.getAllByTestId("campus-mastery-dot");
    expect(dots).toHaveLength(MASTERY_LEVELS.length);
    expect(dots.map((d) => d.getAttribute("data-on"))).toEqual(["false", "true", "false"]);
    expect(screen.getByTestId("campus-mastery-dots").getAttribute("data-level")).toBe("fuzzy");
  });

  it("always spells the level out — colour is never the only signal (PRD §7.4)", () => {
    render(<MasteryDots level="mastered" />);
    const label = screen.getByTestId("campus-mastery-label");
    expect(label.textContent).toBe("Mastered");
    expect(screen.getByTestId("campus-mastery-dots").getAttribute("aria-label")).toContain("Mastered");
  });

  it("covers all three levels without falling back to a raw key", () => {
    for (const level of MASTERY_LEVELS) {
      render(<MasteryDots level={level} />);
      expect(screen.getByTestId("campus-mastery-label").textContent).not.toMatch(/^campus\./);
      cleanup();
    }
  });
});
