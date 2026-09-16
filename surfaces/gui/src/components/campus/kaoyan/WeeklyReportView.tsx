import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useWeeklyReports } from "../../../campus/hooks";
import type { WeeklyReport } from "../../../campus/types";
import { campusErrorInfo, campusErrorKey, formatPercent } from "../../../campus/utils";
import { Markdown } from "../../Markdown";
import { TRACK_LABEL_KEYS } from "./PlanBoard";

function ReportDetail({ report }: { report: WeeklyReport }) {
  const { t } = useTranslation();
  return (
    <div
      className="mt-2 flex flex-col gap-2 rounded-xl2 border border-line bg-canvas p-3 text-[13px] text-ink"
      data-testid={`campus-weekly-detail-${report.id}`}
    >
      <div className="flex flex-wrap gap-x-4 gap-y-1">
        {Object.entries(report.completion_rate).map(([key, rate]) => (
          <span key={key} className="text-muted">
            {t(TRACK_LABEL_KEYS[key] ?? "", { defaultValue: key })} {formatPercent(rate)}
          </span>
        ))}
      </div>
      <div>
        <div className="mb-1 text-[12px] text-muted">{t("campus.kaoyan.weekly.top_mistakes")}</div>
        {report.top_mistake_points.length === 0 ? (
          <span className="text-faint">{t("campus.kaoyan.weekly.no_mistakes")}</span>
        ) : (
          <ul className="list-inside list-disc">
            {report.top_mistake_points.map((point) => (
              <li key={point.title}>
                {point.title} × {point.count}
              </li>
            ))}
          </ul>
        )}
      </div>
      <div>
        <div className="mb-1 text-[12px] text-muted">{t("campus.kaoyan.weekly.suggestion")}</div>
        <p>{report.suggestion}</p>
      </div>
      <Markdown text={report.content_md} />
    </div>
  );
}

export function WeeklyReportView({ profileId }: { profileId: string }) {
  const { t } = useTranslation();
  const { items, loading, error, retryable, reload, generate, generating, genError } =
    useWeeklyReports(profileId);
  const [picked, setPicked] = useState<string | null>(null);

  return (
    <div className="flex flex-col gap-3" data-testid="campus-weekly-view">
      <div className="flex items-center gap-2">
        <button
          type="button"
          className="rounded-full bg-solid px-3 py-1 text-[12px] text-onSolid disabled:opacity-60"
          data-testid="campus-weekly-generate"
          disabled={generating}
          onClick={() => {
            void generate();
          }}
        >
          {generating ? t("campus.kaoyan.weekly.generating") : t("campus.kaoyan.weekly.generate")}
        </button>
        {genError ? (
          <span className="text-[12px] text-warnInk" data-testid="campus-weekly-gen-error">
            {t(campusErrorKey(campusErrorInfo(genError).code), {
              defaultValue: campusErrorInfo(genError).message || t("campus.common.error"),
            })}
          </span>
        ) : null}
        {error ? (
          <span className="flex items-center gap-2 text-[12px] text-warnInk" data-testid="campus-weekly-error">
            <span>
              {t(campusErrorKey(campusErrorInfo(error).code), {
                defaultValue: campusErrorInfo(error).message || t("campus.common.error"),
              })}
            </span>
            {retryable ? (
              <button
                type="button"
                className="rounded-full border border-line px-2 py-[1px] text-[11px] text-ink hover:bg-chromeHover"
                onClick={reload}
                data-testid="campus-weekly-retry"
              >
                {t("campus.common.retry")}
              </button>
            ) : null}
          </span>
        ) : null}
      </div>

      {items.length === 0 && !loading ? (
        <div
          className="rounded-xl2 border border-dashed border-line p-4 text-center text-[13px] text-muted"
          data-testid="campus-weekly-empty"
        >
          {t("campus.kaoyan.weekly.empty")}
        </div>
      ) : (
        <ul className="flex flex-col gap-2">
          {items.map((item) => (
            <li
              key={item.id}
              data-testid={`campus-weekly-item-${item.id}`}
              className="cursor-pointer rounded-xl2 border border-line bg-panel px-3 py-2 text-[13px] text-ink hover:bg-chromeHover"
              onClick={() => setPicked(picked === item.id ? null : item.id)}
            >
              <div className="flex items-center justify-between">
                <span className="font-mono text-[12px]">
                  {item.week_start} ~ {item.week_end}
                </span>
                <span className="text-muted">
                  {formatPercent(item.completion_rate?.overall ?? 0)}
                </span>
              </div>
              {picked === item.id ? <ReportDetail report={item} /> : null}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
