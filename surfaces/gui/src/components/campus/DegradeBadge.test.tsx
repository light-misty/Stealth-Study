import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { DegradeBadge } from "./DegradeBadge";

afterEach(cleanup);

describe("DegradeBadge", () => {
  it("renders nothing while the result is not degraded", () => {
    render(<DegradeBadge level={0} />);
    expect(screen.queryByTestId("campus-degrade-badge")).toBeNull();
  });

  it("renders a notice for every degraded level", () => {
    for (const level of [1, 2, 3] as const) {
      render(<DegradeBadge level={level} />);
      const badge = screen.getByTestId("campus-degrade-badge");
      expect(badge.getAttribute("data-degrade-level")).toBe(String(level));
      // i18n resolved (never a raw key leaking to the user).
      expect(badge.textContent).not.toMatch(/^campus\./);
      expect(badge.textContent).toContain("for reference only");
      cleanup();
    }
  });

  it("shows the backend notice as a second line when one comes back", () => {
    render(<DegradeBadge level={2} notice="模型返回超时，已按降级结果给出" />);
    expect(screen.getByTestId("campus-degrade-notice-detail").textContent).toContain("模型返回超时");
  });

  it("clamps an out-of-range level onto the strongest notice", () => {
    render(<DegradeBadge level={9} />);
    expect(screen.getByTestId("campus-degrade-badge").getAttribute("data-degrade-level")).toBe("3");
  });
});
