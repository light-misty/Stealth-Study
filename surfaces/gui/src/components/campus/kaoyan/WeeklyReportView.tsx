import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useWeeklyReports } from "../../../campus/hooks";
import type { WeeklyReport } from "../../../campus/types";
import { campusErrorInfo, campusErrorKey, formatPercent } from "../../../campus/utils";
import { Markdown } from "../../Markdown";
import { Icon } from "../../Icon";
import { TRACK_LABEL_KEYS } from "./PlanBoard";

// 周卡默认折叠：一屏能看到近 8 周；展开后才给完成率、错点与建议。
// 状态色只是同一串数字的另一条通道，百分比与次数始终以文字呈现（PRD §7.4）。

const rateCellClass = (rate: number): string =>
  rate >= 0.8 ? "cell" : rate >= 0.65 ? "cell cell--partial" : "cell cell--miss";

const ReportDetail = ({ report }: { report: WeeklyReport }) => {
  const { t } = useTranslation();
  const mistakes = report.top_mistake_points;
  return (
    <div className="rpt-b" data-testid={`campus-weekly-detail-${report.id}`}>
      <div className="cells">
        {Object.entries(report.completion_rate).map(([key, rate]) => (
          <span className={rateCellClass(rate)} key={key}>
            <span className="cdot" />
            {t(TRACK_LABEL_KEYS[key] ?? "", { defaultValue: key })} {formatPercent(rate)}
          </span>
        ))}
      </div>

      <div className="sec">
        <div className="sec-text">
          <span className="sec-title">{t("campus.kaoyan.weekly.top_mistakes")}</span>
        </div>
        <span className="sec-n">{mistakes.length}</span>
      </div>
      {mistakes.length === 0 ? (
        <div className="body-text">{t("campus.kaoyan.weekly.no_mistakes")}</div>
      ) : (
        <div className="rows">
          {mistakes.map((point) => (
            <div className="lrow" key={point.title}>
              <div className="lrow-text">
                <span className="lrow-title">{point.title}</span>
              </div>
              <span className={point.count >= 5 ? "tag tag--danger" : "tag tag--warn"}>
                {t("campus.mistake.wrong_count", { count: point.count })}
              </span>
            </div>
          ))}
        </div>
      )}

      <div className="sec">
        <div className="sec-text">
          <span className="sec-title">{t("campus.kaoyan.weekly.suggestion")}</span>
        </div>
      </div>
      <div className="prose">
        <p>{report.suggestion}</p>
        <Markdown text={report.content_md} />
      </div>
      <span className="ai-note">
        <Icon name="sparkle" size={12} />
        {t("campus.common.ai_notice")}
      </span>
    </div>
  );
};

export function WeeklyReportView({ profileId }: { profileId: string }) {
  const { t } = useTranslation();
  const { items, loading, error, retryable, reload, generate, generating, genError } =
    useWeeklyReports(profileId);
  const [openIds, setOpenIds] = useState<string[]>(() => (items[0] ? [items[0].id] : []));

  const toggle = (id: string) =>
    setOpenIds((prev) => (prev.includes(id) ? prev.filter((row) => row !== id) : [...prev, id]));

  return (
    <section className="mod" data-testid="campus-weekly-view">
      <div className="mod-head">
        <span className="ib ib--brand">
          <Icon name="chart" size={16} />
        </span>
        <div className="mod-head-text">
          <span className="mod-title">{t("campus.kaoyan.weekly.title")}</span>
          <span className="mod-desc">{t("campus.kaoyan.weekly.hint")}</span>
        </div>
        <div className="mod-acts">
          <button
            type="button"
            className="btn btn--primary btn--sm"
            data-testid="campus-weekly-generate"
            disabled={generating}
            onClick={() => {
              void generate();
            }}
          >
            {generating ? t("campus.kaoyan.weekly.generating") : t("campus.kaoyan.weekly.generate")}
          </button>
        </div>
      </div>

      {genError ? (
        <div className="alert" data-testid="campus-weekly-gen-error">
          <Icon name="warning" size={14} />
          <div className="alert-text">
            <span className="alert-title">
              {t(campusErrorKey(campusErrorInfo(genError).code), {
                defaultValue: campusErrorInfo(genError).message || t("campus.common.error"),
              })}
            </span>
          </div>
        </div>
      ) : null}

      {error ? (
        <div className="alert" data-testid="campus-weekly-error">
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
              data-testid="campus-weekly-retry"
            >
              {t("campus.common.retry")}
            </button>
          ) : null}
        </div>
      ) : null}

      {loading ? (
        <div className="stack-gap">
          <div className="sk" style={{ width: 180 }} />
          <div className="sk" />
        </div>
      ) : items.length === 0 ? (
        <div className="empty" data-testid="campus-weekly-empty">
          <span className="ib ib--brand">
            <Icon name="chart" size={17} />
          </span>
          <span className="empty-title">{t("campus.kaoyan.weekly.empty")}</span>
        </div>
      ) : (
        <div className="fill thin qcol">
          {items.map((item) => {
            const open = openIds.includes(item.id);
            return (
              <div key={item.id} className={open ? "rpt is-on" : "rpt"} data-testid={`campus-weekly-item-${item.id}`}>
                <button
                  type="button"
                  className="rpt-h"
                  data-testid={`campus-weekly-head-${item.id}`}
                  aria-expanded={open}
                  onClick={() => toggle(item.id)}
                >
                  <Icon name="chevronRight" size={13} className="rpt-chev" />
                  <span className="rpt-d">
                    {item.week_start} ~ {item.week_end.slice(5)}
                  </span>
                  <span className="rpt-n">
                    {t("campus.kaoyan.board.overall")} {formatPercent(item.completion_rate?.overall ?? 0)}
                  </span>
                </button>
                {open ? <ReportDetail report={item} /> : null}
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}
