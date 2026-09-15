import { describe, expect, it } from "vitest";
import { CampusApiError } from "../api";
import {
  campusErrorInfo,
  campusErrorKey,
  COUNTDOWN_HIGHLIGHT_DAYS,
  daysUntil,
  degradeNoticeKey,
  formatPercent,
  isCountdownHighlight,
  nextIntervalDays,
  REVIEW_LADDER,
} from "../utils";

describe("nextIntervalDays (simplified SM-2 ladder, 01 §3)", () => {
  it("walks 1/2/4/7/15 as the correct-answer streak grows", () => {
    expect([1, 2, 3, 4, 5].map(nextIntervalDays)).toEqual([...REVIEW_LADDER]);
  });

  it("caps at the longest interval instead of growing forever", () => {
    expect(nextIntervalDays(6)).toBe(15);
    expect(nextIntervalDays(99)).toBe(15);
  });

  it("resets to one day for a broken streak and for junk input", () => {
    expect(nextIntervalDays(0)).toBe(1);
    expect(nextIntervalDays(-3)).toBe(1);
    expect(nextIntervalDays(Number.NaN)).toBe(1);
  });
});

describe("daysUntil", () => {
  const now = new Date("2026-06-15T23:30:00");

  it("counts whole days on local calendar boundaries", () => {
    expect(daysUntil("2026-06-15", now)).toBe(0);
    expect(daysUntil("2026-06-16", now)).toBe(1);
    expect(daysUntil("2026-06-14", now)).toBe(-1);
    expect(daysUntil("2026-12-25", now)).toBe(193);
  });

  it("accepts an ISO datetime and ignores the time part", () => {
    expect(daysUntil("2026-06-16T00:00:00Z", now)).toBe(1);
    expect(daysUntil("2026-06-16T23:59:59Z", now)).toBe(1);
  });

  it("returns null for missing or unparseable dates", () => {
    expect(daysUntil(null)).toBeNull();
    expect(daysUntil("")).toBeNull();
    expect(daysUntil("not-a-date")).toBeNull();
    expect(daysUntil("2026-02-31")).toBeNull();
    expect(daysUntil("2026-13-01")).toBeNull();
  });
});

describe("isCountdownHighlight", () => {
  it("highlights only the D-30/D-7/D-1/D-day marks", () => {
    for (const day of COUNTDOWN_HIGHLIGHT_DAYS) expect(isCountdownHighlight(day)).toBe(true);
    for (const day of [29, 14, 8, 6, 2, -1]) expect(isCountdownHighlight(day)).toBe(false);
  });
});

describe("degradeNoticeKey", () => {
  it("maps each degraded level to its notice key", () => {
    expect(degradeNoticeKey(0)).toBeNull();
    expect(degradeNoticeKey(1)).toBe("campus.grading.degrade_notice_1");
    expect(degradeNoticeKey(2)).toBe("campus.grading.degrade_notice_2");
    expect(degradeNoticeKey(3)).toBe("campus.grading.degrade_notice_3");
  });

  it("stays silent for null and clamps out-of-range levels onto the strongest notice", () => {
    expect(degradeNoticeKey(null)).toBeNull();
    expect(degradeNoticeKey(undefined)).toBeNull();
    expect(degradeNoticeKey(9)).toBe("campus.grading.degrade_notice_3");
  });
});

describe("campusErrorInfo", () => {
  it("unwraps a structured campus error", () => {
    const err = new CampusApiError("MODEL_TIMEOUT", "model timed out", true, 504);
    expect(campusErrorInfo(err)).toEqual({
      code: "MODEL_TIMEOUT",
      message: "model timed out",
      retryable: true,
    });
  });

  it("falls back to UNKNOWN for plain errors and non-errors", () => {
    expect(campusErrorInfo(new Error("boom"))).toEqual({
      code: "UNKNOWN",
      message: "boom",
      retryable: false,
    });
    expect(campusErrorInfo("weird")).toEqual({
      code: "UNKNOWN",
      message: "weird",
      retryable: false,
    });
    expect(campusErrorInfo(null).code).toBe("UNKNOWN");
  });

  it("maps an error code onto its i18n key", () => {
    expect(campusErrorKey("MODEL_TIMEOUT")).toBe("campus.error.model_timeout");
    expect(campusErrorKey("unknown")).toBe("campus.error.unknown");
  });
});

describe("formatPercent", () => {
  it("renders a 0-1 rate as a whole percentage", () => {
    expect(formatPercent(0)).toBe("0%");
    expect(formatPercent(1)).toBe("100%");
    expect(formatPercent(0.4237)).toBe("42%");
  });

  it("clamps out-of-range rates instead of printing nonsense", () => {
    expect(formatPercent(-0.5)).toBe("0%");
    expect(formatPercent(1.8)).toBe("100%");
    expect(formatPercent(Number.NaN)).toBe("0%");
  });
});
