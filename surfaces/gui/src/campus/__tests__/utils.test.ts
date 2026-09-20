import { describe, expect, it } from "vitest";
import { CampusApiError } from "../api";
import type { ExamProfile, ProfileImpact } from "../types";
import {
  campusErrorInfo,
  campusErrorKey,
  checkInSummary,
  COUNTDOWN_HIGHLIGHT_DAYS,
  daysUntil,
  deadlineTier,
  degradeNoticeKey,
  formatPercent,
  heatWindow,
  isCountdownHighlight,
  localDay,
  nextIntervalDays,
  profileImpactRows,
  profileImpactTotal,
  progressRatio,
  REVIEW_LADDER,
  profileTitleTaken,
  scoringStateOf,
  suggestProfileTitle,
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

describe("deadlineTier (mirrors stealth_study/campus/reminders.tier)", () => {
  it("maps the documented D-30/D-7/D-1 bands plus due/overdue", () => {
    expect(deadlineTier(1)).toBe("d1");
    expect(deadlineTier(2)).toBe("d7");
    expect(deadlineTier(7)).toBe("d7");
    expect(deadlineTier(8)).toBe("d30");
    expect(deadlineTier(30)).toBe("d30");
    expect(deadlineTier(31)).toBe("normal");
    expect(deadlineTier(0)).toBe("today");
    expect(deadlineTier(-1)).toBe("overdue");
  });

  it("keeps junk input on the plain tier instead of throwing", () => {
    expect(deadlineTier(Number.NaN)).toBe("normal");
  });
});

describe("scoringStateOf (CERT scoring points, hit/partial/miss)", () => {
  it("maps the backend 1 / 0.5 / 0 scores onto the three states", () => {
    expect(scoringStateOf(1, 1)).toBe("hit");
    expect(scoringStateOf(0.5, 1)).toBe("partial");
    expect(scoringStateOf(0, 1)).toBe("miss");
  });

  it("stays robust against float jitter and junk input", () => {
    expect(scoringStateOf(0.9999999, 1)).toBe("hit");
    expect(scoringStateOf(2, 2)).toBe("hit");
    expect(scoringStateOf(0.3, 1)).toBe("partial");
    expect(scoringStateOf(Number.NaN, 1)).toBe("miss");
    expect(scoringStateOf(1, 0)).toBe("miss");
    expect(scoringStateOf(-1, 1)).toBe("miss");
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

describe("profileTitleTaken (the desk holds a name, the box does not)", () => {
  const onDesk = { id: "p1", title: "四级冲刺", status: "active" };
  const finished = { id: "p2", title: "已结课", status: "finished" };
  const boxed = { id: "p3", title: "箱子里", status: "archived" };
  const all = [onDesk, finished, boxed] as unknown as ExamProfile[];

  it("matches an unarchived profile's title, ignoring case and surrounding space", () => {
    expect(profileTitleTaken(all, " 四级冲刺 ")).toBe(true);
    expect(profileTitleTaken(all, "四级冲刺", "p1")).toBe(false);
    expect(profileTitleTaken(all, "已结课")).toBe(true);
    expect(profileTitleTaken(all, "箱子里")).toBe(false);
    expect(profileTitleTaken(all, "没人的名字")).toBe(false);
    expect(profileTitleTaken(all, "   ")).toBe(false);
  });
});

describe("suggestProfileTitle", () => {
  const taken = [{ id: "p1", title: "冲刺 (2)", status: "active" }] as unknown as ExamProfile[];

  it("offers the first free numbered variant", () => {
    expect(suggestProfileTitle([], "四级冲刺")).toBe("四级冲刺 (2)");
    expect(suggestProfileTitle(taken, "冲刺")).toBe("冲刺 (3)");
    expect(suggestProfileTitle(taken, "  ")).toBe("");
  });
});

describe("rail maths (progressRatio / heatWindow / checkInSummary)", () => {
  const at = (day: string) => new Date(`${day}T12:00:00`);

  it("clamps a ratio into the bar's own track", () => {
    expect(progressRatio(42, 90)).toBeCloseTo(0.4667, 3);
    expect(progressRatio(150, 90)).toBe(1);
    expect(progressRatio(0, 0)).toBe(0);
    expect(progressRatio(-5, 10)).toBe(0);
  });

  it("writes the local calendar day without sliding across UTC", () => {
    expect(localDay(new Date(2026, 8, 19))).toBe("2026-09-19");
    expect(localDay(new Date(2026, 0, 5))).toBe("2026-01-05");
  });

  it("pads a 21-day window ending today, gaps included", () => {
    const cells = heatWindow([{ date: "2026-09-19", count: 3 }], 21, at("2026-09-19"));
    expect(cells).toHaveLength(21);
    expect(cells[0].date).toBe("2026-08-30");
    expect(cells[0].count).toBe(0);
    expect(cells[20]).toEqual({ date: "2026-09-19", count: 3 });
  });

  it("drops a completion outside the window instead of widening it", () => {
    const cells = heatWindow([{ date: "2026-01-01", count: 9 }], 21, at("2026-09-19"));
    expect(cells.every((cell) => cell.count === 0)).toBe(true);
  });

  it("counts this Monday-first week and calendar month separately", () => {
    // 2026-09-17 is a Thursday: the week runs Mon 14 to Sun 20, September has 30 days.
    const summary = checkInSummary(
      [
        { date: "2026-09-14", count: 1 },
        { date: "2026-09-16", count: 2 },
        { date: "2026-09-20", count: 1 },
        { date: "2026-08-31", count: 4 },
      ],
      at("2026-09-17"),
    );
    expect(summary).toEqual({ weekDone: 3, weekTotal: 7, monthDone: 3, monthTotal: 30 });
  });

  it("reads a streak of nothing as nothing", () => {
    expect(checkInSummary([], at("2026-09-17"))).toEqual({
      weekDone: 0,
      weekTotal: 7,
      monthDone: 0,
      monthTotal: 30,
    });
  });
});

describe("profileImpactRows (what an irreversible delete costs)", () => {
  const impact = (
    cascade: Record<string, number>,
    automation_tasks = 0,
    export_files = 0,
  ): ProfileImpact => ({ profile_id: "p1", cascade, automation_tasks, export_files });

  it("groups the tables the user knows, drops the empty ones and keeps the profile last", () => {
    expect(
      profileImpactRows(impact({ source_doc: 2, doc_chunk: 7, mistake_book: 3, exam_profile: 1 }, 1, 4)),
    ).toEqual([
      { key: "library", count: 9 },
      { key: "mistakes", count: 3 },
      { key: "profile", count: 1 },
      { key: "automations", count: 1 },
      { key: "exports", count: 4 },
    ]);
  });

  it("folds a table it has no label for into one other row", () => {
    expect(profileImpactRows(impact({ quiz_archive: 5, mistake_book: 2 }))).toEqual([
      { key: "mistakes", count: 2 },
      { key: "other", count: 5 },
    ]);
  });

  it("counts the whole cost, the profile row included", () => {
    expect(
      profileImpactTotal(impact({ source_doc: 2, mistake_book: 3, exam_profile: 1 }, 1, 4)),
    ).toBe(11);
    expect(profileImpactTotal(null)).toBe(null);
  });
});
