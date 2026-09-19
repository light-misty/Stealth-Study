import { CampusApiError } from "./api";
import type {
  DegradeLevel,
  DeadlineTier,
  ExamProfile,
  ProfileImpact,
  ScoringState,
} from "./types";

// Shared display helpers for the campus station UI. Kept dependency-free and pure so
// every panel can be tested without rendering or network access.

/** Simplified SM-2 ladder (01 §3): 1/2/4/7/15 days, reset to 1 on a wrong answer. */
export const REVIEW_LADDER = [1, 2, 4, 7, 15] as const;

/** Countdown marks that get the highlighted treatment (CERT-12 / 04 §3.2). */
export const COUNTDOWN_HIGHLIGHT_DAYS = [30, 7, 1, 0] as const;

export const UNKNOWN_ERROR_CODE = "UNKNOWN";

const DAY_MS = 86_400_000;

/** Days from `now` until `date`, measured on calendar days (time-of-day ignored).
 *  Returns null for missing/unparseable input so callers render nothing rather than "NaN". */
export function daysUntil(date: string | null | undefined, now: Date = new Date()): number | null {
  if (!date) return null;
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(date);
  if (!match) return null;
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const target = Date.UTC(year, month - 1, day);
  if (Number.isNaN(target)) return null;
  const probe = new Date(target);
  // Reject roll-over dates such as 2026-02-31, which Date.UTC would silently shift.
  if (probe.getUTCMonth() !== month - 1 || probe.getUTCDate() !== day) return null;
  const today = Date.UTC(now.getFullYear(), now.getMonth(), now.getDate());
  return Math.round((target - today) / DAY_MS);
}

export function isCountdownHighlight(daysLeft: number): boolean {
  return (COUNTDOWN_HIGHLIGHT_DAYS as readonly number[]).includes(daysLeft);
}

/** The `deadline_snapshot` band of a countdown (ss/campus/reminders.tier). */
export function deadlineTier(daysLeft: number): DeadlineTier {
  if (!Number.isFinite(daysLeft)) return "normal";
  if (daysLeft < 0) return "overdue";
  if (daysLeft === 0) return "today";
  if (daysLeft === 1) return "d1";
  if (daysLeft <= 7) return "d7";
  if (daysLeft <= 30) return "d30";
  return "normal";
}

/** Three-state reading of a scoring point score (the backend maps hit/partial/miss onto 1/0.5/0). */
export function scoringStateOf(score: number, max: number): ScoringState {
  if (!Number.isFinite(score) || !Number.isFinite(max) || max <= 0 || score <= 0) return "miss";
  if (score / max >= 0.999) return "hit";
  return "partial";
}

/** Next interval after a review answer: `streakRight` is the consecutive-correct count. */
export function nextIntervalDays(streakRight: number): number {
  if (!Number.isFinite(streakRight) || streakRight <= 0) return REVIEW_LADDER[0];
  const index = Math.min(Math.floor(streakRight), REVIEW_LADDER.length) - 1;
  return REVIEW_LADDER[index];
}

/** i18n key of the degrade notice, or null when the result was not degraded (03 §5-3). */
export function degradeNoticeKey(
  level: DegradeLevel | number | null | undefined,
): string | null {
  if (!level || level < 1) return null;
  return `campus.grading.degrade_notice_${Math.min(Math.floor(level), 3)}`;
}

export function formatPercent(rate: number): string {
  if (!Number.isFinite(rate)) return "0%";
  const clamped = Math.min(Math.max(rate, 0), 1);
  return `${Math.round(clamped * 100)}%`;
}

export interface CampusErrorInfo {
  code: string;
  message: string;
  retryable: boolean;
}

export function campusErrorInfo(err: unknown): CampusErrorInfo {
  if (err instanceof CampusApiError) {
    return { code: err.code, message: err.message, retryable: err.retryable };
  }
  if (err instanceof Error) {
    return { code: UNKNOWN_ERROR_CODE, message: err.message, retryable: false };
  }
  return { code: UNKNOWN_ERROR_CODE, message: err == null ? "" : String(err), retryable: false };
}

/** Locale key for a backend error code; components pass the message as defaultValue. */
export function campusErrorKey(code: string): string {
  return `campus.error.${(code || UNKNOWN_ERROR_CODE).toLowerCase()}`;
}

export function formatTimestamp(value: string | null | undefined): string {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  const pad = (part: number) => String(part).padStart(2, "0");
  return (
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}` +
    ` ${pad(date.getHours())}:${pad(date.getMinutes())}`
  );
}

export function daysSince(value: string | null | undefined): number | null {
  if (!value) return null;
  const at = new Date(value).getTime();
  if (Number.isNaN(at)) return null;
  return (Date.now() - at) / (24 * 60 * 60 * 1000);
}

export function profileTitleTaken(
  profiles: ExamProfile[],
  title: string,
  exceptId?: string | null,
): boolean {
  const wanted = title.trim().toLowerCase();
  if (!wanted) return false;
  return profiles.some(
    (p) => p.id !== exceptId && p.status !== "archived" && p.title.trim().toLowerCase() === wanted,
  );
}

export function suggestProfileTitle(profiles: ExamProfile[], title: string, exceptId?: string): string {
  const base = title.trim();
  if (!base) return "";
  for (let n = 2; n < 100; n += 1) {
    const candidate = `${base} (${n})`;
    if (!profileTitleTaken(profiles, candidate, exceptId)) return candidate;
  }
  return "";
}

/**
 * The A11 cascade told back in the words the station already uses for it (02 §7.3). Ordered:
 * the desk's own modules first, then the profile row itself, then the two things that live
 * outside campus.db. A table this list never heard of lands in `other` rather than vanishing —
 * an irreversible delete must not under-report what it takes.
 */
export const PROFILE_IMPACT_GROUPS: readonly { key: string; tables: readonly string[] }[] = [
  { key: "library", tables: ["source_doc", "doc_chunk"] },
  { key: "questions", tables: ["question_bank_item"] },
  { key: "vocab", tables: ["vocab_item"] },
  { key: "knowledge", tables: ["knowledge_point", "mastery"] },
  { key: "attempts", tables: ["attempt"] },
  { key: "mistakes", tables: ["mistake_book"] },
  { key: "review", tables: ["review_queue"] },
  { key: "plans", tables: ["study_plan", "plan_task"] },
  { key: "exams", tables: ["mock_exam", "assessment"] },
  { key: "reports", tables: ["weekly_report"] },
  { key: "deadlines", tables: ["cert_deadline"] },
  { key: "school", tables: ["school_profile"] },
];

/** The group keys, in render order, including the three that are not campus tables. */
export const PROFILE_IMPACT_KEYS: readonly string[] = [
  ...PROFILE_IMPACT_GROUPS.map((group) => group.key),
  "other",
  "profile",
  "automations",
  "exports",
];

export interface ProfileImpactRow {
  key: string;
  count: number;
}

export function profileImpactRows(impact: ProfileImpact | null): ProfileImpactRow[] {
  if (!impact) return [];
  const rows: ProfileImpactRow[] = [];
  const named = new Set<string>();
  for (const group of PROFILE_IMPACT_GROUPS) {
    const count = group.tables.reduce(
      (sum, table) => sum + (impact.cascade[table] ?? 0),
      0,
    );
    for (const table of group.tables) named.add(table);
    if (count) rows.push({ key: group.key, count });
  }
  const other = Object.entries(impact.cascade).reduce(
    (sum, [table, count]) =>
      named.has(table) || table === "exam_profile" ? sum : sum + count,
    0,
  );
  if (other) rows.push({ key: "other", count: other });
  if (impact.cascade.exam_profile) rows.push({ key: "profile", count: impact.cascade.exam_profile });
  if (impact.automation_tasks) rows.push({ key: "automations", count: impact.automation_tasks });
  if (impact.export_files) rows.push({ key: "exports", count: impact.export_files });
  return rows;
}

/** Everything the delete takes, the profile row included; `null` when the cost is unknown. */
export function profileImpactTotal(impact: ProfileImpact | null): number | null {
  if (!impact) return null;
  return profileImpactRows(impact).reduce((sum, row) => sum + row.count, 0);
}

/** The rail's heat strip is a fixed 21-day window, so the caption can say 近 21 天 truthfully. */
export const HEAT_WINDOW_DAYS = 21;

/** `YYYY-MM-DD` in the viewer's own calendar — `toISOString` would slide across a UTC boundary. */
export function localDay(date: Date): string {
  const pad = (part: number) => String(part).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

/** A row's fill ratio, clamped: an over-plan day must not paint a bar past its own track. */
export function progressRatio(done: number, total: number): number {
  if (!total) return 0;
  return Math.max(0, Math.min(1, done / total));
}

/** The window as `days` cells, oldest first, ending on the local today, gaps filled with zero. */
export function heatWindow(
  heatmap: readonly { date: string; count: number }[],
  days: number = HEAT_WINDOW_DAYS,
  now: Date = new Date(),
): { date: string; count: number }[] {
  const counts = new Map(heatmap.map((cell) => [cell.date, cell.count]));
  const cells: { date: string; count: number }[] = [];
  for (let back = days - 1; back >= 0; back -= 1) {
    const day = new Date(now.getFullYear(), now.getMonth(), now.getDate() - back);
    const date = localDay(day);
    cells.push({ date, count: counts.get(date) ?? 0 });
  }
  return cells;
}

/** How much of this week (Monday first) and this calendar month already has a check-in. */
export function checkInSummary(
  heatmap: readonly { date: string; count: number }[],
  now: Date = new Date(),
): { weekDone: number; weekTotal: number; monthDone: number; monthTotal: number } {
  const days = new Set(heatmap.filter((cell) => cell.count > 0).map((cell) => cell.date));
  const monday = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  monday.setDate(monday.getDate() - ((monday.getDay() + 6) % 7));
  let weekDone = 0;
  for (let step = 0; step < 7; step += 1) {
    const day = new Date(monday.getFullYear(), monday.getMonth(), monday.getDate() + step);
    if (days.has(localDay(day))) weekDone += 1;
  }
  const monthTotal = new Date(now.getFullYear(), now.getMonth() + 1, 0).getDate();
  let monthDone = 0;
  for (let step = 1; step <= monthTotal; step += 1) {
    const day = new Date(now.getFullYear(), now.getMonth(), step);
    if (days.has(localDay(day))) monthDone += 1;
  }
  return { weekDone, weekTotal: 7, monthDone, monthTotal };
}
