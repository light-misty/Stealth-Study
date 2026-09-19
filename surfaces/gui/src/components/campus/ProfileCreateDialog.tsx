import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { CampusTrack, ProfileCreateInput } from "../../campus/types";
import { CampusDialog } from "./CampusDialog";

export function ProfileCreateDialog({
  track,
  onCreate,
  onClose,
  busy = false,
}: {
  track: CampusTrack;
  onCreate: (input: ProfileCreateInput) => void | Promise<void>;
  onClose: () => void;
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
    <CampusDialog
      testId="campus-profile-create-dialog"
      title={t("campus.profile.create")}
      icon="plus"
      onClose={onClose}
      footer={
        <>
          <button
            type="button"
            className="btn btn--text"
            onClick={onClose}
            data-testid="campus-profile-create-cancel"
          >
            {t("campus.profile.create_cancel")}
          </button>
          <button
            type="button"
            className="btn btn--primary"
            onClick={submit}
            disabled={busy}
            data-testid="campus-profile-create-submit"
          >
            {t("campus.profile.create_submit")}
          </button>
        </>
      }
    >
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
    </CampusDialog>
  );
}
