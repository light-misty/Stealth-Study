import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { listQuestions, submitAttempt } from "../../../campus/api";
import type { AttemptFeedback, QuestionBankItem } from "../../../campus/types";
import { campusErrorInfo, campusErrorKey } from "../../../campus/utils";
import { Icon } from "../../Icon";

// One question at a time, paper first: the stem and its options are the subject of this
// screen, so the progress, the verdict and the actions sit around them rather than above
// a list. 现状是文本题训练，没有音频播放控件 —— 图标只标识「听力」这一科目，不暗示可播放。

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

  const head = (
    <div className="mod-head">
      <span className="ib ib--brand">
        <Icon name="sound" size={16} />
      </span>
      <div className="mod-head-text">
        <span className="mod-title">{t("campus.cet.listening.title")}</span>
        <span className="mod-desc">{t("campus.cet.listening.hint")}</span>
      </div>
      {current ? (
        <div className="mod-acts">
          <span className="sec-n" data-testid="campus-cet-listening-progress">
            {t("campus.cet.listening.progress", {
              index: index + 1,
              total: questions.length,
            })}
          </span>
        </div>
      ) : null}
    </div>
  );

  if (error) {
    return (
      <section className="mod">
        {head}
        <div className="alert" data-testid="campus-cet-listening-error">
          <Icon name="warning" size={14} />
          <div className="alert-text">
            <span className="alert-title">{t("campus.common.error")}</span>
            <span className="alert-desc">
              {t(campusErrorKey(campusErrorInfo(error).code), {
                defaultValue: campusErrorInfo(error).message || t("campus.common.error"),
              })}
            </span>
          </div>
          <button
            type="button"
            className="btn btn--ghost btn--sm"
            onClick={() => setNonce((n) => n + 1)}
            data-testid="campus-cet-listening-retry"
          >
            {t("campus.common.retry")}
          </button>
        </div>
      </section>
    );
  }

  if (loading) {
    return (
      <section className="mod">
        {head}
        <div className="stack-gap">
          <div className="sk" style={{ width: 140 }} />
          <div className="sk" />
          <div className="sk" style={{ width: "68%" }} />
        </div>
        <span className="body-text">{t("campus.cet.listening.loading")}</span>
      </section>
    );
  }

  if (!current) {
    return (
      <section className="mod">
        {head}
        <div className="empty" data-testid="campus-cet-listening-empty">
          <span className="ib ib--brand">
            <Icon name="sound" size={17} />
          </span>
          <span className="empty-title">{t("campus.cet.listening.empty")}</span>
        </div>
      </section>
    );
  }

  const options = current.options ?? [];
  const graded = feedback?.is_correct === 1 || feedback?.is_correct === 0;
  const answered = feedback ? index + 1 : index;

  return (
    <section className="mod" data-testid="campus-cet-listening">
      {head}

      <div className="stack">
        <div className="bar">
          <i
            style={{ "--w": `${Math.round((answered / questions.length) * 100)}%` } as Record<
              string,
              string
            >}
          />
        </div>

        <div className="fill thin qcol">
          <div
            className="q"
            data-testid="campus-cet-listening-question"
            data-qid={current.id}
          >
            <div className="q-head">
              <span className="tag tag--brand">{t(`campus.common.qtype.${current.qtype}`)}</span>
              <span className="q-no">
                {t("campus.cet.listening.qno", { index: index + 1 })}
              </span>
            </div>
            <p className="q-stem">{current.stem}</p>

            {options.length > 0 ? (
              <div className="opts">
                {options.map((o) => (
                  <button
                    key={o.key}
                    type="button"
                    className={answer === o.key ? "opt is-on" : "opt"}
                    aria-pressed={answer === o.key}
                    data-testid="campus-cet-listening-option"
                    data-key={o.key}
                    onClick={() => setAnswer(o.key)}
                  >
                    <span className="opt-k">{o.key}</span>
                    <span>{o.text}</span>
                  </button>
                ))}
              </div>
            ) : current.qtype === "blank" ? (
              <input
                className="input"
                data-testid="campus-cet-listening-blank"
                value={answer}
                onChange={(e) => setAnswer(e.target.value)}
              />
            ) : (
              <textarea
                className="textarea"
                rows={3}
                data-testid="campus-cet-listening-text"
                value={answer}
                onChange={(e) => setAnswer(e.target.value)}
              />
            )}
          </div>

          {feedback ? (
            <div data-testid="campus-cet-listening-result">
              {graded ? (
                <div className={feedback.is_correct === 1 ? "verdict verdict--right" : "verdict verdict--wrong"}>
                  <Icon name={feedback.is_correct === 1 ? "check" : "x"} size={14} />
                  <div className="verdict-text">
                    <span data-testid="campus-cet-listening-correct" data-correct={feedback.is_correct === 1 ? "true" : "false"}>
                      {feedback.is_correct === 1
                        ? t("campus.cet.listening.correct")
                        : t("campus.cet.listening.wrong")}
                    </span>
                    {feedback.standard_answer ? (
                      <span className="verdict-k">
                        {t("campus.cet.listening.standard_answer")}{" "}
                        <span data-testid="campus-cet-listening-standard-answer">
                          {feedback.standard_answer}
                        </span>
                      </span>
                    ) : null}
                  </div>
                </div>
              ) : null}

              {feedback.is_correct == null && feedback.score != null ? (
                <div className="verdict">
                  <Icon name="activity" size={14} />
                  <div className="verdict-text">
                    <span data-testid="campus-cet-listening-score">
                      {t("campus.cet.listening.score", {
                        score: feedback.score,
                        max: feedback.max_score ?? 0,
                      })}
                    </span>
                    <span className="verdict-k" data-testid="campus-cet-listening-pending">
                      {t("campus.cet.listening.pending")}
                    </span>
                  </div>
                </div>
              ) : null}
            </div>
          ) : null}

          {submitError ? (
            <div className="alert" data-testid="campus-cet-listening-error">
              <Icon name="warning" size={14} />
              <div className="alert-text">
                <span className="alert-title">{t("campus.common.error")}</span>
                <span className="alert-desc">
                  {t(campusErrorKey(campusErrorInfo(submitError).code), {
                    defaultValue:
                      campusErrorInfo(submitError).message || t("campus.common.error"),
                  })}
                </span>
              </div>
              {campusErrorInfo(submitError).retryable ? (
                <button
                  type="button"
                  className="btn btn--ghost btn--sm"
                  onClick={onSubmit}
                  disabled={submitting}
                >
                  {t("campus.common.retry")}
                </button>
              ) : null}
            </div>
          ) : null}
        </div>

        <div className="mod-foot">
          <span className="ai-note">{t("campus.cet.listening.no_audio")}</span>
          <span className="st-spacer" />
          {feedback && index < questions.length - 1 ? (
            <button
              type="button"
              className="btn btn--ghost"
              data-testid="campus-cet-listening-next"
              onClick={onNext}
            >
              {t("campus.cet.listening.next")}
            </button>
          ) : null}
          <button
            type="button"
            className="btn btn--primary"
            data-testid="campus-cet-listening-submit"
            onClick={onSubmit}
            disabled={submitting || !answer.trim()}
          >
            {t("campus.cet.listening.submit")}
          </button>
        </div>
      </div>
    </section>
  );
}
