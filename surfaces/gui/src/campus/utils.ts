import { CampusApiError } from "./api";
import type { DegradeLevel, DeadlineTier, ScoringState } from "./types";

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
