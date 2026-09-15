import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useMistakes } from "../../campus/hooks";
import { ATTRIBUTIONS, type Attribution, type MistakeFilters } from "../../campus/types";
import { campusErrorInfo, campusErrorKey } from "../../campus/utils";

// The mistake book is the one list that can reach four figures, so it renders on a
// window: only the rows near the viewport are mounted (02 §6 backs the query with an
// index). Row height is fixed, which is what makes the arithmetic cheap.

const ROW_HEIGHT = 72;
const OVERSCAN = 4;
const DEFAULT_VIEWPORT = 420;

export function MistakeBookPanel({
  profileId,
  filters,
}: {
  profileId: string;
  filters?: MistakeFilters;
}) {
  const { t } = useTranslation();
  const { items, total, loading, error, retryable, reload, setAttribution } = useMistakes(
    profileId,
    filters ?? {},
  );
  const [scrollTop, setScrollTop] = useState(0);
  const [viewport, setViewport] = useState(DEFAULT_VIEWPORT);
  const scroller = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const el = scroller.current;
    if (el && el.clientHeight > 0) setViewport(el.clientHeight);
  }, []);

  const windowSize = Math.ceil(viewport / ROW_HEIGHT) + OVERSCAN;
  const start = Math.max(0, Math.floor(scrollTop / ROW_HEIGHT) - OVERSCAN);
  const slice = items.slice(start, start + windowSize);

  return (
    <div className="rounded-xl2 border border-line bg-panel" data-testid="campus-mistake-panel">
      <div className="flex items-center justify-between px-4 pt-3.5">
        <div className="text-[13px] font-semibold text-ink">{t("campus.mistake.title")}</div>
        <div className="text-[11px] text-faint" data-testid="campus-mistake-total">
          {t("campus.mistake.count", { count: total })}
        </div>
      </div>

      {loading ? (
        <div className="px-4 py-3 text-[12px] text-faint" data-testid="campus-mistake-loading">
          {t("campus.common.loading")}
        </div>
      ) : null}

      {error ? (
        <div className="px-4 py-2 text-[12px] text-warnInk" data-testid="campus-mistake-error">
          {t(campusErrorKey(campusErrorInfo(error).code), {
            defaultValue: campusErrorInfo(error).message || t("campus.common.error"),
          })}
          {retryable ? (
            <button
              type="button"
              className="ml-2 text-accent"
              onClick={reload}
              data-testid="campus-mistake-retry"
            >
              {t("campus.common.retry")}
            </button>
          ) : null}
        </div>
      ) : null}

      {!loading && items.length === 0 ? (
        <div className="px-4 py-3 text-[12px] text-faint" data-testid="campus-mistake-empty">
          {t("campus.mistake.empty")}
        </div>
      ) : null}

      {items.length > 0 ? (
        <>
          <div
            ref={scroller}
            className="mt-2 overflow-y-auto px-4"
            style={{ height: viewport }}
            onScroll={(e) => setScrollTop(e.currentTarget.scrollTop)}
            data-testid="campus-mistake-scroller"
          >
            <div style={{ height: items.length * ROW_HEIGHT, position: "relative" }}>
              {slice.map((entry, index) => (
                <div
                  key={entry.id}
                  className="flex items-center justify-between gap-2 border-b border-line/60 pr-1"
                  style={{
                    position: "absolute",
                    top: (start + index) * ROW_HEIGHT,
                    left: 0,
                    right: 0,
                    height: ROW_HEIGHT,
                  }}
                  data-testid="campus-mistake-row"
                  data-id={entry.id}
                  data-attribution={entry.attribution}
                  data-resolved={String(entry.resolved)}
                >
                  <div className="min-w-0">
                    <div className="text-[12px] text-ink truncate" data-testid="campus-mistake-subject">
                      {t(`campus.common.subject.${entry.subject}`, { defaultValue: entry.subject })}
                    </div>
                    <div className="text-[11px] text-faint">
                      {t("campus.mistake.wrong_count", { count: entry.wrong_count })}
                    </div>
                  </div>
                  <select
                    className="shrink-0 rounded-lg border border-line bg-transparent px-2 py-1 text-[12px] text-muted"
                    value={entry.attribution}
                    onChange={(e) => void setAttribution(entry.id, e.target.value as Attribution)}
                    data-testid="campus-mistake-attribution"
                    aria-label={t("campus.mistake.attribution")}
                  >
                    {ATTRIBUTIONS.map((option) => (
                      <option key={option} value={option}>
                        {t(`campus.common.attribution.${option}`)}
                      </option>
                    ))}
                  </select>
                </div>
              ))}
            </div>
          </div>
          <div className="px-4 pb-3 pt-1 text-[11px] text-faint" data-testid="campus-mistake-window">
            {t("campus.mistake.window_info", { shown: slice.length, total })}
          </div>
        </>
      ) : null}
    </div>
  );
}
