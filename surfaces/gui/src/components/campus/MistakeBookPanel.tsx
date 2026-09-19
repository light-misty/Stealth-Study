import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useMistakes } from "../../campus/hooks";
import { ATTRIBUTIONS, type Attribution, type MistakeFilters } from "../../campus/types";
import { campusErrorInfo, campusErrorKey } from "../../campus/utils";
import { Icon } from "../Icon";

// The mistake book is the one list that can reach four figures, so it renders on a
// window: only the rows near the viewport are mounted (02 §6 backs the query with an
// index). Row height is fixed, which is what makes the arithmetic cheap.
// 归因下拉是行内紧凑档（.sel--sm），行高不被控件撑开；卡头再给一个按错因筛选的入口。

const ROW_HEIGHT = 58;
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
  const [attribution, setAttribution] = useState<Attribution | "">("");
  const query: MistakeFilters = { ...filters, attribution: attribution || undefined };
  const { items, total, loading, error, retryable, reload, setAttribution: patchAttribution } =
    useMistakes(profileId, query);
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
    <section className="mod" data-testid="campus-mistake-panel">
      <div className="mod-head">
        <span className="ib ib--brand">
          <Icon name="list" size={16} />
        </span>
        <div className="mod-head-text">
          <span className="mod-title">{t("campus.mistake.title")}</span>
          <span className="mod-desc">{t("campus.mistake.hint")}</span>
        </div>
        <div className="mod-acts">
          <span className="sec-n" data-testid="campus-mistake-total">
            {t("campus.mistake.count", { count: total })}
          </span>
          <div className="sel sel--sm">
            <select
              value={attribution}
              onChange={(e) => setAttribution(e.target.value as Attribution | "")}
              data-testid="campus-mistake-filter"
              aria-label={t("campus.mistake.attribution")}
            >
              <option value="">{t("campus.mistake.attribution_all")}</option>
              {ATTRIBUTIONS.map((option) => (
                <option key={option} value={option}>
                  {t(`campus.common.attribution.${option}`)}
                </option>
              ))}
            </select>
            <Icon name="chevronDown" size={13} className="sel-chev" />
          </div>
        </div>
      </div>

      {loading ? (
        <div className="stack-gap" data-testid="campus-mistake-loading">
          <div className="sk" />
          <div className="sk" style={{ width: "78%" }} />
          <span className="body-text">{t("campus.common.loading")}</span>
        </div>
      ) : null}

      {error ? (
        <div className="alert" data-testid="campus-mistake-error">
          <Icon name="warning" size={14} />
          <div className="alert-text">
            <span className="alert-title">
              {t(campusErrorKey(campusErrorInfo(error).code), {
                defaultValue: campusErrorInfo(error).message || t("campus.common.error"),
              })}
            </span>
          </div>
          {retryable ? (
            <button
              type="button"
              className="btn btn--ghost btn--sm"
              onClick={reload}
              data-testid="campus-mistake-retry"
            >
              {t("campus.common.retry")}
            </button>
          ) : null}
        </div>
      ) : null}

      {!loading && items.length === 0 ? (
        <div className="empty" data-testid="campus-mistake-empty">
          <span className="ib ib--brand">
            <Icon name="book" size={17} />
          </span>
          <span className="empty-title">{t("campus.mistake.empty")}</span>
        </div>
      ) : null}

      {items.length > 0 ? (
        <>
          <div
            ref={scroller}
            className="rows fill thin"
            style={{ height: viewport }}
            onScroll={(e) => setScrollTop(e.currentTarget.scrollTop)}
            data-testid="campus-mistake-scroller"
          >
            <div style={{ height: items.length * ROW_HEIGHT, position: "relative" }}>
              {slice.map((entry, index) => (
                <div
                  key={entry.id}
                  className="lrow"
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
                  <div className="lrow-text">
                    <span className="lrow-title" data-testid="campus-mistake-subject">
                      {t(`campus.common.subject.${entry.subject}`, { defaultValue: entry.subject })}
                    </span>
                    <span className="lrow-meta">
                      {t("campus.mistake.wrong_count", { count: entry.wrong_count })}
                    </span>
                  </div>
                  <div className="lrow-ctl">
                    <div className="sel sel--sm">
                      <select
                        value={entry.attribution}
                        onChange={(e) =>
                          void patchAttribution(entry.id, e.target.value as Attribution)
                        }
                        data-testid="campus-mistake-attribution"
                        aria-label={t("campus.mistake.attribution")}
                      >
                        {ATTRIBUTIONS.map((option) => (
                          <option key={option} value={option}>
                            {t(`campus.common.attribution.${option}`)}
                          </option>
                        ))}
                      </select>
                      <Icon name="chevronDown" size={13} className="sel-chev" />
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
          <div className="mod-foot">
            <span className="sec-n" data-testid="campus-mistake-window">
              {t("campus.mistake.window_info", { shown: slice.length, total })}
            </span>
          </div>
        </>
      ) : null}
    </section>
  );
}
