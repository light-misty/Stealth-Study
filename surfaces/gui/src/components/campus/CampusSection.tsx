import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { getAppState, patchAppState } from "../../campus/api";
import {
  REVIEW_INTENSITIES,
  type ReviewIntensity,
} from "../../campus/types";

// Settings ▸ Campus tab body (04 §4.6, G-06): the three exam-prep preferences the PRD
// puts on the campus tab — daily study minutes, the review push time and the interval
// intensity. Values live in campus.db's app_state (A6/A7); the layering rule holds here
// too: plain fields, no track branching, all copy through i18n.

const FIELD =
  "w-full rounded-lg border border-line bg-transparent px-2.5 py-1.5 text-[13px] text-ink outline-none";
const LABEL = "text-[12px] text-muted";

const DEFAULT_MINUTES = "60";
const DEFAULT_PUSH_TIME = "20:00";
const DEFAULT_INTENSITY: ReviewIntensity = "standard";

export function CampusSection() {
  const { t } = useTranslation();
  const [dailyMinutes, setDailyMinutes] = useState(DEFAULT_MINUTES);
  const [pushTime, setPushTime] = useState(DEFAULT_PUSH_TIME);
  const [intensity, setIntensity] = useState<ReviewIntensity>(DEFAULT_INTENSITY);
  const [loading, setLoading] = useState(true);
  const [loadFailed, setLoadFailed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  const [saveFailed, setSaveFailed] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    setLoadFailed(false);
    getAppState()
      .then((state) => {
        setDailyMinutes(String(state.settings.daily_minutes ?? DEFAULT_MINUTES));
        setPushTime(state.settings.push_time ?? DEFAULT_PUSH_TIME);
        setIntensity(state.settings.review_intensity ?? DEFAULT_INTENSITY);
        setLoading(false);
      })
      .catch(() => {
        setLoading(false);
        setLoadFailed(true);
      });
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const minutes = Number(dailyMinutes);
  const minutesValid = Number.isFinite(minutes) && minutes >= 1;
  const canSave = !loading && !loadFailed && !busy && minutesValid;

  const save = () => {
    if (!canSave) return;
    setBusy(true);
    setSaved(false);
    setSaveFailed(false);
    patchAppState({
      settings: { daily_minutes: minutes, push_time: pushTime, review_intensity: intensity },
    })
      .then(() => {
        setBusy(false);
        setSaved(true);
      })
      .catch(() => {
        setBusy(false);
        setSaveFailed(true);
      });
  };

  return (
    <section data-testid="campus-settings">
      <div className="text-[15px] font-semibold text-ink">{t("campus.settings.title")}</div>

      {loadFailed ? (
        <div className="mt-4" data-testid="campus-settings-error">
          <div className="text-[13px] text-warnInk">{t("campus.common.error")}</div>
          <button
            type="button"
            className="mt-2 px-3 py-1.5 rounded-lg border border-line text-[13px] text-ink hover:border-lineStrong"
            onClick={load}
            data-testid="campus-settings-retry"
          >
            {t("campus.common.retry")}
          </button>
        </div>
      ) : loading ? (
        <div className="mt-4 text-[13px] text-muted" data-testid="campus-settings-loading">
          {t("campus.common.loading")}
        </div>
      ) : (
        <div className="mt-4 grid gap-3 max-w-md">
          <label className="block">
            <span className={LABEL}>{t("campus.settings.daily_minutes")}</span>
            <input
              type="number"
              min={1}
              className={`${FIELD} mt-1`}
              value={dailyMinutes}
              onChange={(e) => {
                setDailyMinutes(e.target.value);
                setSaved(false);
                setSaveFailed(false);
              }}
              data-testid="campus-settings-daily-minutes"
            />
          </label>
          <label className="block">
            <span className={LABEL}>{t("campus.settings.push_time")}</span>
            <input
              type="time"
              className={`${FIELD} mt-1`}
              value={pushTime}
              onChange={(e) => {
                setPushTime(e.target.value);
                setSaved(false);
                setSaveFailed(false);
              }}
              data-testid="campus-settings-push-time"
            />
          </label>
          <label className="block">
            <span className={LABEL}>{t("campus.settings.review_intensity")}</span>
            <select
              className={`${FIELD} mt-1`}
              value={intensity}
              onChange={(e) => {
                setIntensity(e.target.value as ReviewIntensity);
                setSaved(false);
                setSaveFailed(false);
              }}
              data-testid="campus-settings-intensity"
            >
              {REVIEW_INTENSITIES.map((value) => (
                <option key={value} value={value}>
                  {t(`campus.settings.intensity_${value}`)}
                </option>
              ))}
            </select>
          </label>

          <div className="flex items-center gap-2.5">
            <button
              type="button"
              className="px-3 py-1.5 rounded-lg bg-accent text-white text-[13px] disabled:opacity-40"
              onClick={save}
              disabled={!canSave}
              data-testid="campus-settings-save"
            >
              {t("campus.settings.save")}
            </button>
            {saved && (
              <span className="text-[12px] text-muted" data-testid="campus-settings-saved">
                {t("campus.settings.saved")}
              </span>
            )}
            {saveFailed && (
              <span className="text-[12px] text-warnInk" data-testid="campus-settings-save-error">
                {t("campus.common.error")}
              </span>
            )}
          </div>
        </div>
      )}
    </section>
  );
}
