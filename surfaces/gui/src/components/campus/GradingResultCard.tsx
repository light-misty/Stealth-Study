import { useTranslation } from "react-i18next";
import type { GradeResult } from "../../campus/types";
import { DegradeBadge } from "./DegradeBadge";
import { Icon } from "../Icon";

// The four-part result card shared by every station (07 §5 T17 acceptance): dimension
// scores, a locatable error list, the model outline and — when the run was degraded —
// the degrade notice on top.
// 版式取自设计稿 campus.css 的「批改结果卡共享」一节：分项用条带、错误用子卡、
// 脚注固定给模型署名与 AI 声明。

const dimWidth = (score: number, max: number): string =>
  `${Math.round((max ? score / max : 0) * 100)}%`;

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
  const errors = result.errors ?? [];

  return (
    <div className="grade" data-testid="campus-grading-result">
      <DegradeBadge level={result.degrade_level} notice={result.notice} />

      <div className="sec">
        <div className="sec-text">
          <span className="sec-title">{t("campus.grading.dimensions")}</span>
        </div>
        <span className="sec-n" data-testid="campus-grading-rubric">
          {t("campus.grading.rubric")}: {result.rubric}
        </span>
      </div>

      <div className="dims">
        {(result.dimensions ?? []).map((dim) => (
          <div
            className="dim-row"
            key={dim.name}
            data-testid="campus-grading-dimension"
            data-name={dim.name}
            data-score={dim.score}
            data-max={dim.max}
          >
            <span className="dim-n">{dim.name}</span>
            <span className="bar dim-bar">
              <i style={{ "--w": dimWidth(dim.score, dim.max) } as Record<string, string>} />
            </span>
            <span className="dim-v">
              {dim.score}/{dim.max}
            </span>
          </div>
        ))}
      </div>

      <div className="sec">
        <div className="sec-text">
          <span className="sec-title">{t("campus.grading.errors")}</span>
        </div>
      </div>

      {errors.length === 0 ? (
        <div className="body-text" data-testid="campus-grading-no-errors">
          {t("campus.grading.no_errors")}
        </div>
      ) : (
        <div className="errs">
          {errors.map((err, index) => (
            <div
              className="err"
              key={`${err.original}-${index}`}
              data-testid="campus-grading-error"
              data-type={err.type}
              data-offset={err.offset ?? ""}
            >
              <span className="err-k">{err.type}</span>
              <span className="err-orig">{err.original}</span>
              <span className="err-fix">
                {t("campus.grading.suggestion")}: {err.suggestion}
              </span>
              {onLocate && err.offset !== null ? (
                <div className="err-acts">
                  <button
                    type="button"
                    className="btn btn--text btn--sm"
                    onClick={() => onLocate(err.offset as number)}
                    data-testid="campus-grading-locate"
                  >
                    <Icon name="eye" size={12} />
                    {t("campus.grading.locate")}
                  </button>
                </div>
              ) : null}
            </div>
          ))}
        </div>
      )}

      <div className="sec">
        <div className="sec-text">
          <span className="sec-title">{t("campus.grading.model_outline")}</span>
        </div>
      </div>
      <p className="body-text" data-testid="campus-grading-outline">
        {result.model_answer_outline}
      </p>

      <div className="mod-foot">
        <span className="ai-note" data-testid="campus-grading-model">
          {t("campus.grading.model_used")}: {result.model_used}
        </span>
        <span className="st-spacer" />
        {onAddToMistake ? (
          <button
            type="button"
            className="btn btn--ghost btn--sm"
            onClick={onAddToMistake}
            data-testid="campus-grading-to-mistake"
          >
            <Icon name="plus" size={12} />
            {t("campus.grading.add_to_mistake")}
          </button>
        ) : null}
      </div>

      <span className="ai-note" data-testid="campus-grading-ai-notice">
        {t("campus.common.ai_notice")}
      </span>
    </div>
  );
}
