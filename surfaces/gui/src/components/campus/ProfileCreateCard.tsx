import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { CampusTrack, ProfileCreateInput } from "../../campus/types";

// Guided "create a profile" card — also the empty-state for a station with no profile
// (07 §5 T16 acceptance ①). Optional fields are omitted rather than sent blank so the
// backend applies its own defaults instead of choking on "".

const FIELD =
  "w-full rounded-lg border border-line bg-transparent px-2.5 py-1.5 text-[13px] text-ink outline-none";

export function ProfileCreateCard({
  track,
  onCreate,
  onCancel,
  busy = false,
}: {
  track: CampusTrack;
  onCreate: (input: ProfileCreateInput) => void | Promise<void>;
  onCancel?: () => void;
  busy?: boolean;
}) {
  const { t } = useTranslation();
  const [title, setTitle] = useState("");
  const [examDate, setExamDate] = useState("");
  const [targetScore, setTargetScore] = useState("");
  const [dailyMinutes, setDailyMinutes] = useState("");
  const [invalid, setInvalid] = useState(false);

  const numberOrUndefined = (raw: string): number | undefined => {
    const trimmed = raw.trim();
    if (!trimmed) return undefined;
    const parsed = Number(trimmed);
    return Number.isFinite(parsed) ? parsed : undefined;
  };

  const submit = () => {
    // A second click while the create is in flight would POST a second profile (A2 has no
    // client-generated idempotency key yet), so the button is locked until it settles.
    if (busy) return;
    const cleanTitle = title.trim();
    if (!cleanTitle) {
      setInvalid(true);
      return;
    }
    setInvalid(false);
    const target = numberOrUndefined(targetScore);
    const minutes = numberOrUndefined(dailyMinutes);
    onCreate({
      track_type: track,
      title: cleanTitle,
      ...(examDate ? { exam_date: examDate } : {}),
      ...(target === undefined ? {} : { target_score: target }),
      ...(minutes === undefined ? {} : { daily_minutes: minutes }),
    });
  };

  return (
    <div
      className="rounded-xl2 border border-line bg-panel px-4 py-3.5"
      data-testid="campus-profile-create-card"
    >
      <div className="text-[13px] font-semibold text-ink">{t("campus.profile.create")}</div>

      <div className="mt-3 grid gap-2.5">
        <label className="block">
          <span className="text-[12px] text-muted">{t("campus.profile.title_label")}</span>
          <input
            className={`${FIELD} mt-1`}
            value={title}
            onChange={(e) => {
              setTitle(e.target.value);
              setInvalid(false);
            }}
            data-testid="campus-profile-create-title"
          />
        </label>
        <label className="block">
          <span className="text-[12px] text-muted">{t("campus.profile.exam_date_label")}</span>
          <input
            type="date"
            className={`${FIELD} mt-1`}
            value={examDate}
            onChange={(e) => setExamDate(e.target.value)}
            data-testid="campus-profile-create-exam-date"
          />
        </label>
        <div className="grid grid-cols-2 gap-2.5">
          <label className="block">
            <span className="text-[12px] text-muted">{t("campus.profile.target_score_label")}</span>
            <input
              className={`${FIELD} mt-1`}
              value={targetScore}
              onChange={(e) => setTargetScore(e.target.value)}
              data-testid="campus-profile-create-target-score"
            />
          </label>
          <label className="block">
            <span className="text-[12px] text-muted">{t("campus.profile.daily_minutes_label")}</span>
            <input
              className={`${FIELD} mt-1`}
              value={dailyMinutes}
              onChange={(e) => setDailyMinutes(e.target.value)}
              data-testid="campus-profile-create-daily-minutes"
            />
          </label>
        </div>
      </div>

      {invalid && (
        <div className="mt-2 text-[12px] text-warnInk" data-testid="campus-profile-create-error">
          {t("campus.profile.title_required")}
        </div>
      )}

      <div className="mt-3 flex items-center gap-2">
        <button
          type="button"
          className="px-3 py-1.5 rounded-lg bg-accent text-white text-[13px] disabled:opacity-40"
          onClick={submit}
          disabled={busy}
          data-testid="campus-profile-create-submit"
        >
          {t("campus.profile.create_submit")}
        </button>
        {onCancel && (
          <button
            type="button"
            className="px-2 py-1.5 text-[13px] text-faint hover:text-muted"
            onClick={onCancel}
            data-testid="campus-profile-create-cancel"
          >
            {t("campus.profile.create_cancel")}
          </button>
        )}
      </div>
    </div>
  );
}
