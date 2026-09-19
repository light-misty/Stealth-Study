import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { CampusTrack, ProfileCreateInput } from "../../campus/types";

// Guided "create a profile" card — also the empty-state for a station with no profile
// (07 §5 T16 acceptance ①). Optional fields are omitted rather than sent blank so the
// backend applies its own defaults instead of choking on "".

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
    <div className="mod" data-testid="campus-profile-create-card">
      <div className="mod-head">
        <div className="mod-head-text">
          <span className="mod-title">{t("campus.profile.create")}</span>
          <span className="mod-desc">{t(`campus.track.${track}.tagline`)}</span>
        </div>
      </div>

      <div className={invalid ? "field is-bad" : "field"}>
        <span className="field-label">{t("campus.profile.title_label")}</span>
        <input
          className="input"
          value={title}
          onChange={(e) => {
            setTitle(e.target.value);
            setInvalid(false);
          }}
          data-testid="campus-profile-create-title"
        />
        {invalid ? (
          <span className="field-err" data-testid="campus-profile-create-error">
            {t("campus.profile.title_required")}
          </span>
        ) : null}
      </div>

      <div className="field">
        <span className="field-label">{t("campus.profile.exam_date_label")}</span>
        <input
          className="input input--num"
          type="date"
          value={examDate}
          onChange={(e) => setExamDate(e.target.value)}
          data-testid="campus-profile-create-exam-date"
        />
      </div>

      <div className="field-rows">
        <div className="field">
          <span className="field-label">{t("campus.profile.target_score_label")}</span>
          <input
            className="input input--num"
            inputMode="numeric"
            value={targetScore}
            onChange={(e) => setTargetScore(e.target.value)}
            data-testid="campus-profile-create-target-score"
          />
        </div>
        <div className="field">
          <span className="field-label">{t("campus.profile.daily_minutes_label")}</span>
          <input
            className="input input--num"
            inputMode="numeric"
            value={dailyMinutes}
            onChange={(e) => setDailyMinutes(e.target.value)}
            data-testid="campus-profile-create-daily-minutes"
          />
        </div>
      </div>

      <div className="mod-foot">
        {onCancel ? (
          <button
            type="button"
            className="btn btn--text"
            onClick={onCancel}
            data-testid="campus-profile-create-cancel"
          >
            {t("campus.profile.create_cancel")}
          </button>
        ) : null}
        <span className="st-spacer" />
        <button
          type="button"
          className="btn btn--primary"
          onClick={submit}
          disabled={busy}
          data-testid="campus-profile-create-submit"
        >
          {t("campus.profile.create_submit")}
        </button>
      </div>
    </div>
  );
}
