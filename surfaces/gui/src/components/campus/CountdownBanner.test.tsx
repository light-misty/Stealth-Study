import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { CountdownBanner } from "./CountdownBanner";

afterEach(cleanup);

const now = new Date("2026-09-15T10:00:00");

describe("CountdownBanner", () => {
  it("keeps the card on the rail with a blank number when no exam date is set", () => {
    render(<CountdownBanner examDate={null} now={now} />);
    const banner = screen.getByTestId("campus-countdown-banner");
    expect(banner.getAttribute("data-days-left")).toBe("");
    expect(banner.textContent).toContain("--");
    expect(banner.textContent).toContain("Exam date not set");
    expect(banner.querySelector(".bar")).toBeTruthy();
  });

  it("treats an unusable date as no date instead of guessing one", () => {
    render(<CountdownBanner examDate="2026-02-31" now={now} />);
    const banner = screen.getByTestId("campus-countdown-banner");
    expect(banner.getAttribute("data-days-left")).toBe("");
    expect(banner.textContent).toContain("--");
  });

  it("counts the days that are left", () => {
    render(<CountdownBanner examDate="2026-09-27" now={now} />);
    const banner = screen.getByTestId("campus-countdown-banner");
    expect(banner.getAttribute("data-days-left")).toBe("12");
    expect(banner.textContent).toContain("12");
    expect(banner.getAttribute("data-highlight")).toBe("false");
  });

  it("highlights the D-30 / D-7 / D-1 / D-day marks", () => {
    for (const [days, date] of [
      [30, "2026-10-15"],
      [7, "2026-09-22"],
      [1, "2026-09-16"],
      [0, "2026-09-15"],
    ] as const) {
      render(<CountdownBanner examDate={date} now={now} />);
      const banner = screen.getByTestId("campus-countdown-banner");
      expect(banner.getAttribute("data-days-left")).toBe(String(days));
      expect(banner.getAttribute("data-highlight")).toBe("true");
      cleanup();
    }
  });

  it("says the exam has passed instead of counting negative days", () => {
    render(<CountdownBanner examDate="2026-09-10" now={now} />);
    const banner = screen.getByTestId("campus-countdown-banner");
    expect(banner.getAttribute("data-days-left")).toBe("-5");
    expect(banner.getAttribute("data-passed")).toBe("true");
    expect(banner.textContent).not.toContain("campus.");
  });
});
