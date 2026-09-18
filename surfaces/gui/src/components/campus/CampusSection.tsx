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
  "h-[34px] rounded-[10px] border border-line bg-paper px-2.5 text-[13px] text-ink outline-none focus:border-accent";

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
        <div className="set-panel mt-4">
          {/* 行 · 每日学习时长 */}
          <div className="set-row">
            <span className="ib ib--accent">
              <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="9" />
                <polyline points="12 7 12 12 15.5 13.5" />
              </svg>
            </span>
            <div className="set-text">
              <span className="set-title">{t("campus.settings.daily_minutes")}</span>
              <span className="set-desc">{t("campus.settings.daily_minutes_help")}</span>
            </div>
            <div className="set-ctl">
              <input
                type="number"
                min={1}
                className={`${FIELD} w-[96px]`}
                value={dailyMinutes}
                onChange={(e) => {
                  setDailyMinutes(e.target.value);
                  setSaved(false);
                  setSaveFailed(false);
                }}
                data-testid="campus-settings-daily-minutes"
              />
            </div>
          </div>

          {/* 行 · 推送时间 */}
          <div className="set-row">
            <span className="ib ib--brand">
              <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
                <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
              </svg>
            </span>
            <div className="set-text">
              <span className="set-title">{t("campus.settings.push_time")}</span>
              <span className="set-desc">{t("campus.settings.push_time_help")}</span>
            </div>
            <div className="set-ctl">
              <input
                type="time"
                className={`${FIELD} w-[132px]`}
                value={pushTime}
                onChange={(e) => {
                  setPushTime(e.target.value);
                  setSaved(false);
                  setSaveFailed(false);
                }}
                data-testid="campus-settings-push-time"
              />
            </div>
          </div>

          {/* 行 · 复习强度 */}
          <div className="set-row">
            <span className="ib ib--success">
              <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 2l7 3v6c0 5-3.5 8.5-7 10-3.5-1.5-7-5-7-10V5l7-3z" />
                <path d="M12 8v5" />
                <path d="M9.5 11.5h5" />
              </svg>
            </span>
            <div className="set-text">
              <span className="set-title">{t("campus.settings.review_intensity")}</span>
              <span className="set-desc">{t("campus.settings.review_intensity_help")}</span>
            </div>
            <div className="set-ctl">
              <select
                className={`${FIELD} min-w-[120px]`}
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
            </div>
          </div>

          {/* 底部署名操作区 */}
          <div className="flex items-center justify-end gap-2.5 border-t border-line px-5 py-3.5">
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
            <button
              type="button"
              className="h-[34px] rounded-[10px] bg-accent px-4 text-[13px] text-white disabled:opacity-40"
              onClick={save}
              disabled={!canSave}
              data-testid="campus-settings-save"
            >
              {t("campus.settings.save")}
            </button>
          </div>
        </div>
      )}
    </section>
  );
}
