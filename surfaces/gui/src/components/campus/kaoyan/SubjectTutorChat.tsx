import { useState } from "react";
import { useTranslation } from "react-i18next";
import { submitGrading } from "../../../campus/api";
import type { GradeResult, GradingKind } from "../../../campus/types";
import { campusErrorInfo, campusErrorKey } from "../../../campus/utils";
import { Icon } from "../../Icon";
import { GradingResultCard } from "../GradingResultCard";

const SUBJECT_KINDS: Record<string, GradingKind> = {
  politics: "essay_material",
  english: "essay",
  math: "short_answer",
  major: "short_answer",
};

const KIND_OPTIONS: GradingKind[] = ["essay_material", "essay", "short_answer", "translation"];

const SUBJECT_OPTIONS = ["politics", "english", "math", "major"] as const;

// 名字里有 Chat，实际是一次性的科目批改：没有会话列表也没有历史，所以这里不画聊天框，
// 版式与 CET 的批改工作坊同一套（题型 + 原文 + 结果）。

export function SubjectTutorChat({ profileId }: { profileId: string }) {
  const { t } = useTranslation();
  const [subject, setSubject] = useState<string>("politics");
  const [kind, setKind] = useState<GradingKind>(SUBJECT_KINDS.politics);
  const [answer, setAnswer] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<GradeResult | null>(null);
  const [error, setError] = useState<unknown>(null);

  const canSubmit = answer.trim().length > 0 && !submitting;

  const changeSubject = (next: string) => {
    setSubject(next);
    setKind(SUBJECT_KINDS[next] ?? KIND_OPTIONS[0]);
  };

  const submit = async () => {
    if (!canSubmit) return;
    setSubmitting(true);
    setError(null);
    try {
      setResult(await submitGrading({ profileId, kind, answer: answer.trim() }));
    } catch (err) {
      setError(err);
      setResult(null);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <section className="mod" data-testid="campus-tutor-chat">
      <div className="mod-head">
        <span className="ib ib--accent">
          <Icon name="chat" size={16} />
        </span>
        <div className="mod-head-text">
          <span className="mod-title">{t("campus.kaoyan.tutor.title")}</span>
          <span className="mod-desc">{t("campus.kaoyan.tutor.hint")}</span>
        </div>
      </div>

      <div className="tutor-kinds">
        <div className="field">
          <span className="field-label">{t("campus.kaoyan.tutor.subject")}</span>
          <div className="sel">
            <select
              data-testid="campus-tutor-subject"
              value={subject}
              onChange={(event) => changeSubject(event.target.value)}
            >
              {SUBJECT_OPTIONS.map((option) => (
                <option key={option} value={option}>
                  {t(`campus.common.subject.${option}`)}
                </option>
              ))}
            </select>
            <Icon name="chevronDown" size={14} className="sel-chev" />
          </div>
        </div>
        <div className="field">
          <span className="field-label">{t("campus.kaoyan.tutor.kind_label")}</span>
          <div className="sel">
            <select
              data-testid="campus-tutor-kind"
              value={kind}
              onChange={(event) => setKind(event.target.value as GradingKind)}
            >
              {KIND_OPTIONS.map((option) => (
                <option key={option} value={option}>
                  {t(`campus.kaoyan.tutor.kind.${option}`)}
                </option>
              ))}
            </select>
            <Icon name="chevronDown" size={14} className="sel-chev" />
          </div>
        </div>
      </div>

      <div className="answer">
        <div className="answer-h">
          <span className="answer-t">{t("campus.cet.grading.input_label")}</span>
        </div>
        <textarea
          className="textarea"
          data-testid="campus-tutor-answer"
          placeholder={t("campus.kaoyan.tutor.answer")}
          value={answer}
          onChange={(event) => setAnswer(event.target.value)}
        />
      </div>

      {error ? (
        <div className="alert" data-testid="campus-tutor-error">
          <Icon name="warning" size={14} />
          <div className="alert-text">
            <span className="alert-title">
              {t(campusErrorKey(campusErrorInfo(error).code), {
                defaultValue: campusErrorInfo(error).message || t("campus.common.error"),
              })}
            </span>
          </div>
        </div>
      ) : null}

      {result ? <GradingResultCard result={result} /> : null}

      <div className="mod-foot">
        <span className="st-spacer" />
        <button
          type="button"
          className="btn btn--primary"
          data-testid="campus-tutor-submit"
          disabled={!canSubmit}
          onClick={() => {
            void submit();
          }}
        >
          {submitting ? t("campus.kaoyan.tutor.submitting") : t("campus.kaoyan.tutor.submit")}
        </button>
      </div>
    </section>
  );
}
