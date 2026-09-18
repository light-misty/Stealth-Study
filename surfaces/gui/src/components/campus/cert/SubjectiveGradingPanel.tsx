import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useGrading } from "../../../campus/hooks";
import { SCORING_KINDS, type ScoringKind, type ScoringState } from "../../../campus/types";
import { campusErrorInfo, campusErrorKey, scoringStateOf } from "../../../campus/utils";
import { Icon } from "../../Icon";
import { GradingResultCard } from "../GradingResultCard";

// 采分点的命中 / 部分 / 未命中走学习侧的绿-黄-红，且始终带文字（PRD §7.4）。
const STATE_CLASS: Record<ScoringState, string> = {
  hit: "cell cell--hit",
  partial: "cell cell--partial",
  miss: "cell cell--miss",
};

export function SubjectiveGradingPanel({ profileId }: { profileId: string }) {
  const { t } = useTranslation();
  const { result, loading, error, retryable, submit: grade } = useGrading(profileId);
  const [kind, setKind] = useState<ScoringKind>("short_answer");
  const [answer, setAnswer] = useState("");
  const [rubric, setRubric] = useState("");
  const [formError, setFormError] = useState<string | null>(null);

  const submit = async () => {
    if (loading) return;
    const trimmed = answer.trim();
    if (!trimmed) {
      setFormError("campus.cert.grading.answer_required");
      return;
    }
    setFormError(null);
    await grade({ kind, answer: trimmed, customRubric: rubric.trim() || undefined });
  };

  const info = error ? campusErrorInfo(error) : null;
  const message = formError
    ? t(formError)
    : info
      ? t(campusErrorKey(info.code), { defaultValue: info.message || t("campus.common.error") })
      : null;

  return (
    <section className="mod" data-testid="campus-cert-grading-panel">
      <div className="mod-head">
        <span className="ib ib--accent">
          <Icon name="pencil" size={16} />
        </span>
        <div className="mod-head-text">
          <span className="mod-title">{t("campus.cert.grading.title")}</span>
          <span className="mod-desc">{t("campus.cert.grading.hint")}</span>
        </div>
        {result ? (
          <div className="mod-acts">
            <span className="rubric-sum" data-testid="campus-cert-grading-kind-label">
              {t(`campus.cert.grading.kind.${kind}`)}
            </span>
          </div>
        ) : null}
      </div>

      <div className="picks">
        {SCORING_KINDS.map((kindOption) => (
          <button
            key={kindOption}
            type="button"
            className={kindOption === kind ? "pick is-on" : "pick"}
            onClick={() => setKind(kindOption)}
            data-testid="campus-cert-grading-kind"
            data-kind={kindOption}
            data-active={kindOption === kind ? "true" : "false"}
          >
            {t(`campus.cert.grading.kind.${kindOption}`)}
          </button>
        ))}
      </div>

      <div className={formError ? "field is-bad" : "field"}>
        <span className="field-label">{t("campus.cert.grading.answer_label")}</span>
        <textarea
          className="textarea"
          value={answer}
          onChange={(e) => {
            setAnswer(e.target.value);
            setFormError(null);
          }}
          data-testid="campus-cert-grading-answer"
        />
        {formError ? (
          <span className="field-err" data-testid="campus-cert-grading-error">
            {message}
          </span>
        ) : null}
      </div>

      <div className="field">
        <span className="field-label">{t("campus.cert.grading.rubric_label")}</span>
        <input
          className="input"
          value={rubric}
          onChange={(e) => setRubric(e.target.value)}
          data-testid="campus-cert-grading-rubric"
        />
      </div>

      {loading ? (
        <div className="stack-gap" data-testid="campus-cert-grading-loading">
          <div className="sk" style={{ width: 220 }} />
          <div className="sk" />
        </div>
      ) : null}

      {info ? (
        <div className="alert" data-testid="campus-cert-grading-error">
          <Icon name="warning" size={14} />
          <div className="alert-text">
            <span className="alert-title">{message}</span>
          </div>
          {retryable ? (
            <button
              type="button"
              className="btn btn--ghost btn--sm"
              onClick={() => void submit()}
              data-testid="campus-cert-grading-retry"
            >
              {t("campus.common.retry")}
            </button>
          ) : null}
        </div>
      ) : null}

      {result ? (
        <>
          <div className="cells">
            {result.dimensions.map((dim) => {
              const state = scoringStateOf(dim.score, dim.max);
              return (
                <span
                  className={STATE_CLASS[state]}
                  key={dim.name}
                  data-testid="campus-cert-grading-state"
                  data-name={dim.name}
                  data-state={state}
                >
                  <span className="cdot" />
                  {dim.name} · {t(`campus.cert.grading.state.${state}`)}
                </span>
              );
            })}
          </div>
          <GradingResultCard result={result} />
        </>
      ) : null}

      <div className="mod-foot">
        <span className="st-spacer" />
        <button
          type="button"
          className="btn btn--primary"
          disabled={loading}
          onClick={() => void submit()}
          data-testid="campus-cert-grading-submit"
        >
          {t("campus.cert.grading.submit")}
        </button>
      </div>
    </section>
  );
}
