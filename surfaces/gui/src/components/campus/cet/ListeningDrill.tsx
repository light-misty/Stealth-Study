import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { listQuestions, submitAttempt } from "../../../campus/api";
import type { AttemptFeedback, QuestionBankItem } from "../../../campus/types";
import { campusErrorInfo } from "../../../campus/utils";

export function ListeningDrill({ profileId }: { profileId: string }) {
  const { t } = useTranslation();
  const [questions, setQuestions] = useState<QuestionBankItem[]>([]);
  const [index, setIndex] = useState(0);
  const [answer, setAnswer] = useState("");
  const [feedback, setFeedback] = useState<AttemptFeedback | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<unknown>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    if (!profileId) {
      setLoading(false);
      return;
    }
    let alive = true;
    setLoading(true);
    listQuestions(profileId, { subject: "listening" }).then(
      (res) => {
        if (!alive) return;
        setQuestions(res?.items ?? []);
        setError(null);
        setLoading(false);
      },
      (err) => {
        if (!alive) return;
        setError(err);
        setLoading(false);
      },
    );
    return () => {
      alive = false;
    };
  }, [profileId, nonce]);

  const current = questions[index] ?? null;

  const onSubmit = () => {
    if (!current || !answer.trim() || submitting) return;
    setSubmitting(true);
    setSubmitError(null);
    submitAttempt({
      profileId,
      questionId: current.id,
      sessionType: "practice",
      answer,
    }).then(
      (res) => {
        setFeedback(res as AttemptFeedback);
        setSubmitting(false);
      },
      (err) => {
        setSubmitError(err);
        setSubmitting(false);
      },
    );
  };

  const onNext = () => {
    setIndex((i) => i + 1);
    setAnswer("");
    setFeedback(null);
    setSubmitError(null);
  };

  if (error) {
    return (
      <div
        className="rounded-xl2 border border-warnInk/40 bg-warnSoft px-4 py-3 text-[13px] text-warnInk"
        data-testid="campus-cet-listening-error"
      >
        {t("campus.common.error")}
        <span className="ml-1 text-faint">{campusErrorInfo(error).message}</span>
        <button
          type="button"
          className="ml-2 text-accent"
          onClick={() => setNonce((n) => n + 1)}
          data-testid="campus-cet-listening-retry"
        >
          {t("campus.common.retry")}
        </button>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="rounded-xl2 border border-line bg-panel px-4 py-3.5 text-[12px] text-muted">
        {t("campus.cet.listening.loading")}
      </div>
    );
  }

  if (!current) {
    return (
      <div
        className="rounded-xl2 border border-line bg-panel px-4 py-3.5 text-[12px] text-faint"
        data-testid="campus-cet-listening-empty"
      >
        {t("campus.cet.listening.empty")}
      </div>
    );
  }

  const options = current.options ?? [];

  return (
    <div className="grid gap-3" data-testid="campus-cet-listening">
      <div
        className="text-[12px] text-faint"
        data-testid="campus-cet-listening-progress"
      >
        {t("campus.cet.listening.progress", {
          index: index + 1,
          total: questions.length,
        })}
      </div>
      <div
        className="rounded-xl2 border border-line bg-panel px-4 py-3"
        data-testid="campus-cet-listening-question"
        data-qid={current.id}
      >
        <div className="text-[13px] text-ink">{current.stem}</div>
        {options.length > 0 ? (
          <div className="mt-2 grid gap-1.5">
            {options.map((o) => (
              <button
                key={o.key}
                type="button"
                className={`rounded-lg2 border px-3 py-1.5 text-left text-[12px] ${
                  answer === o.key
                    ? "border-accent bg-accentSoft text-ink"
                    : "border-line bg-panel text-muted"
                }`}
                aria-pressed={answer === o.key}
                data-testid="campus-cet-listening-option"
                data-key={o.key}
                onClick={() => setAnswer(o.key)}
              >
                <span className="mr-2 font-semibold text-ink">{o.key}</span>
                <span>{o.text}</span>
              </button>
            ))}
          </div>
        ) : current.qtype === "blank" ? (
          <input
            className="mt-2 w-full rounded-lg2 border border-line bg-panel px-3 py-1.5 text-[12px] text-ink"
            data-testid="campus-cet-listening-blank"
            value={answer}
            onChange={(e) => setAnswer(e.target.value)}
          />
        ) : (
          <textarea
            className="mt-2 w-full rounded-lg2 border border-line bg-panel px-3 py-1.5 text-[12px] text-ink"
            rows={3}
            data-testid="campus-cet-listening-text"
            value={answer}
            onChange={(e) => setAnswer(e.target.value)}
          />
        )}
        {submitError ? (
          <div
            className="mt-2 rounded-xl2 border border-warnInk/40 bg-warnSoft px-3 py-2 text-[12px] text-warnInk"
            data-testid="campus-cet-listening-error"
          >
            {t("campus.common.error")}
            <span className="ml-1 text-faint">{campusErrorInfo(submitError).message}</span>
            {campusErrorInfo(submitError).retryable ? (
              <button
                type="button"
                className="ml-2 text-accent"
                onClick={onSubmit}
                disabled={submitting}
              >
                {t("campus.common.retry")}
              </button>
            ) : null}
          </div>
        ) : null}
        <div className="mt-3">
          <button
            type="button"
            className="rounded-lg2 bg-accent px-4 py-1.5 text-[12px] font-semibold text-inkOnAccent disabled:opacity-50"
            data-testid="campus-cet-listening-submit"
            onClick={onSubmit}
            disabled={submitting || !answer.trim()}
          >
            {t("campus.cet.listening.submit")}
          </button>
        </div>
      </div>
      {feedback ? (
        <div
          className="rounded-xl2 border border-line bg-panel px-4 py-3"
          data-testid="campus-cet-listening-result"
        >
          {feedback.is_correct === 1 || feedback.is_correct === 0 ? (
            <>
              <div
                className={`text-[13px] font-semibold ${
                  feedback.is_correct === 1 ? "text-okInk" : "text-warnInk"
                }`}
                data-testid="campus-cet-listening-correct"
                data-correct={feedback.is_correct === 1 ? "true" : "false"}
              >
                {feedback.is_correct === 1
                  ? t("campus.cet.listening.correct")
                  : t("campus.cet.listening.wrong")}
              </div>
              {feedback.standard_answer ? (
                <div className="mt-1 text-[12px] text-muted">
                  <span className="text-faint">
                    {t("campus.cet.listening.standard_answer")}
                  </span>
                  <span
                    className="ml-1 text-ink"
                    data-testid="campus-cet-listening-standard-answer"
                  >
                    {feedback.standard_answer}
                  </span>
                </div>
              ) : null}
            </>
          ) : null}
          {feedback.is_correct == null && feedback.score != null ? (
            <>
              <div className="text-[13px] text-ink" data-testid="campus-cet-listening-score">
                {t("campus.cet.listening.score", {
                  score: feedback.score,
                  max: feedback.max_score ?? 0,
                })}
              </div>
              <div className="mt-1 text-[12px] text-faint" data-testid="campus-cet-listening-pending">
                {t("campus.cet.listening.pending")}
              </div>
            </>
          ) : null}
          {index < questions.length - 1 ? (
            <button
              type="button"
              className="mt-2 rounded-lg2 border border-line bg-panel px-3 py-1 text-[12px] text-muted"
              data-testid="campus-cet-listening-next"
              onClick={onNext}
            >
              {t("campus.cet.listening.next")}
            </button>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
