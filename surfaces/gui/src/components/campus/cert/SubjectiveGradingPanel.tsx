import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useGrading } from "../../../campus/hooks";
import { SCORING_KINDS, type ScoringKind, type ScoringState } from "../../../campus/types";
import { campusErrorInfo, campusErrorKey, scoringStateOf } from "../../../campus/utils";
import { GradingResultCard } from "../GradingResultCard";

const STATE_CLASS: Record<ScoringState, string> = {
  hit: "border-okLine text-ok",
  partial: "border-warnSoft text-warnInk",
  miss: "border-dangerSoft text-danger",
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
    <div className="rounded-xl2 border border-line bg-panel" data-testid="campus-cert-grading-panel">
      <div className="px-4 pt-3.5 text-[13px] font-semibold text-ink">
        {t("campus.cert.grading.title")}
      </div>

      <div className="flex flex-wrap items-center gap-1.5 px-4 pt-2.5">
        {SCORING_KINDS.map((kindOption) => (
          <button
            key={kindOption}
            type="button"
            className={`rounded-lg border px-2 py-1 text-[12px] ${
              kindOption === kind ? "border-accent text-accent" : "border-line text-muted"
            }`}
            onClick={() => setKind(kindOption)}
            data-testid="campus-cert-grading-kind"
            data-kind={kindOption}
            data-active={kindOption === kind ? "true" : "false"}
          >
            {t(`campus.cert.grading.kind.${kindOption}`)}
          </button>
        ))}
      </div>

      <div className="px-4 pt-2.5">
        <textarea
          className="min-h-24 w-full rounded-lg border border-line bg-panel px-2 py-1.5 text-[12px] text-ink"
          value={answer}
          placeholder={t("campus.cert.grading.answer_label")}
          onChange={(e) => {
            setAnswer(e.target.value);
            setFormError(null);
          }}
          data-testid="campus-cert-grading-answer"
        />
        <input
          className="mt-1.5 w-full rounded-lg border border-line bg-panel px-2 py-1 text-[12px] text-ink"
          value={rubric}
          placeholder={t("campus.cert.grading.rubric_label")}
          onChange={(e) => setRubric(e.target.value)}
          data-testid="campus-cert-grading-rubric"
        />
      </div>

      <div className="flex items-center gap-2 px-4 pt-2.5">
        <button
          type="button"
          className="rounded-lg border border-accent px-2.5 py-1 text-[12px] text-accent disabled:opacity-50"
          disabled={loading}
          onClick={() => void submit()}
          data-testid="campus-cert-grading-submit"
        >
          {t("campus.cert.grading.submit")}
        </button>
        {loading ? (
          <span className="text-[12px] text-faint" data-testid="campus-cert-grading-loading">
            {t("campus.common.loading")}
          </span>
        ) : null}
      </div>

      {message ? (
        <div
          className="flex items-center gap-2 px-4 py-2 text-[12px] text-warnInk"
          data-testid="campus-cert-grading-error"
        >
          <span className="min-w-0 truncate">{message}</span>
          {retryable ? (
            <button
              type="button"
              className="shrink-0 rounded-lg border border-line px-2 py-0.5 text-[11px] text-muted"
              onClick={() => void submit()}
              data-testid="campus-cert-grading-retry"
            >
              {t("campus.common.retry")}
            </button>
          ) : null}
        </div>
      ) : null}

      {result ? (
        <div className="px-4 pb-3.5">
          <ul className="mt-2 flex flex-wrap gap-1.5">
            {result.dimensions.map((dim) => {
              const state = scoringStateOf(dim.score, dim.max);
              return (
                <li
                  key={dim.name}
                  className={`rounded-lg border px-2 py-0.5 text-[11px] ${STATE_CLASS[state]}`}
                  data-testid="campus-cert-grading-state"
                  data-name={dim.name}
                  data-state={state}
                >
                  {t(`campus.cert.grading.state.${state}`)}
                </li>
              );
            })}
          </ul>
          <div className="mt-2">
            <GradingResultCard result={result} />
          </div>
        </div>
      ) : null}
    </div>
  );
}
