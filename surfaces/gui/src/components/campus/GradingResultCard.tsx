import { useTranslation } from "react-i18next";
import type { GradeResult } from "../../campus/types";
import { DegradeBadge } from "./DegradeBadge";

// The four-part result card shared by every station (07 §5 T17 acceptance): dimension
// scores, a locatable error list, the model outline and — when the run was degraded —
// the degrade notice on top.

export function GradingResultCard({
  result,
  onLocate,
  onAddToMistake,
}: {
  result: GradeResult;
  onLocate?: (offset: number) => void;
  onAddToMistake?: () => void;
}) {
  const { t } = useTranslation();

  return (
    <div className="rounded-xl2 border border-line bg-panel px-4 py-3.5" data-testid="campus-grading-result">
      <DegradeBadge level={result.degrade_level} notice={result.notice} />

      <div className="mt-1 flex items-baseline justify-between">
        <div className="text-[13px] font-semibold text-ink">{t("campus.grading.dimensions")}</div>
        <div className="text-[11px] text-faint" data-testid="campus-grading-rubric">
          {t("campus.grading.rubric")}: {result.rubric}
        </div>
      </div>

      <ul className="mt-2 grid gap-1.5">
        {(result.dimensions ?? []).map((dim) => (
          <li
            key={dim.name}
            className="flex items-start gap-2 text-[12px]"
            data-testid="campus-grading-dimension"
            data-name={dim.name}
            data-score={dim.score}
            data-max={dim.max}
          >
            <span className="text-ink w-16 shrink-0">{dim.name}</span>
            <span className="text-muted">
              {dim.score}/{dim.max}
            </span>
            <span className="text-muted">{dim.comment}</span>
          </li>
        ))}
      </ul>

      <div className="mt-3 text-[13px] font-semibold text-ink">{t("campus.grading.errors")}</div>
      {(result.errors ?? []).length === 0 ? (
        <div className="mt-1 text-[12px] text-faint" data-testid="campus-grading-no-errors">
          {t("campus.grading.no_errors")}
        </div>
      ) : (
        <ul className="mt-1.5 grid gap-2">
          {(result.errors ?? []).map((err, index) => (
            <li
              key={`${err.original}-${index}`}
              className="rounded-lg border border-line px-2.5 py-2"
              data-testid="campus-grading-error"
              data-type={err.type}
              data-offset={err.offset ?? ""}
            >
              <div className="text-[12px] text-ink">{err.original}</div>
              <div className="text-[12px] text-muted mt-0.5">
                {t("campus.grading.suggestion")}: {err.suggestion}
              </div>
              {onLocate && err.offset !== null ? (
                <button
                  type="button"
                  className="mt-1 text-[12px] text-accent"
                  onClick={() => onLocate(err.offset as number)}
                  data-testid="campus-grading-locate"
                >
                  {t("campus.grading.locate")}
                </button>
              ) : null}
            </li>
          ))}
        </ul>
      )}

      <div className="mt-3 text-[12px] text-muted" data-testid="campus-grading-outline">
        <span className="text-ink">{t("campus.grading.model_outline")}</span>:{" "}
        {result.model_answer_outline}
      </div>

      <div className="mt-2 flex items-center justify-between">
        <div className="text-[11px] text-faint" data-testid="campus-grading-model">
          {t("campus.grading.model_used")}: {result.model_used}
        </div>
        {onAddToMistake ? (
          <button
            type="button"
            className="px-2.5 py-1 rounded-lg text-[12px] text-muted border border-line hover:text-ink"
            onClick={onAddToMistake}
            data-testid="campus-grading-to-mistake"
          >
            {t("campus.grading.add_to_mistake")}
          </button>
        ) : null}
      </div>

      <div className="mt-2 text-[11px] text-faint" data-testid="campus-grading-ai-notice">
        {t("campus.common.ai_notice")}
      </div>
    </div>
  );
}
