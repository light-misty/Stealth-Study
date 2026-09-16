import { useState } from "react";
import { useTranslation } from "react-i18next";
import { submitGrading } from "../../../campus/api";
import type { GradeResult, GradingKind } from "../../../campus/types";
import { campusErrorInfo, campusErrorKey } from "../../../campus/utils";
import { GradingResultCard } from "../GradingResultCard";

const SUBJECT_KINDS: Record<string, GradingKind> = {
  politics: "essay_material",
  english: "essay",
  math: "short_answer",
  major: "short_answer",
};

const KIND_OPTIONS: GradingKind[] = ["essay_material", "essay", "short_answer", "translation"];

const SUBJECT_OPTIONS = ["politics", "english", "math", "major"] as const;

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
    <div className="flex flex-col gap-3" data-testid="campus-tutor-chat">
      <div className="flex flex-wrap items-center gap-2 text-[12px] text-muted">
        <label className="flex items-center gap-1">
          {t("campus.kaoyan.tutor.subject")}
          <select
            className="rounded-lg border border-line bg-panel px-2 py-1 text-[12px] text-ink"
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
        </label>
        <label className="flex items-center gap-1">
          {t("campus.kaoyan.tutor.kind")}
          <select
            className="rounded-lg border border-line bg-panel px-2 py-1 text-[12px] text-ink"
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
        </label>
      </div>

      <textarea
        className="min-h-[120px] rounded-xl2 border border-line bg-panel px-3 py-2 text-[13px] text-ink"
        data-testid="campus-tutor-answer"
        placeholder={t("campus.kaoyan.tutor.answer")}
        value={answer}
        onChange={(event) => setAnswer(event.target.value)}
      />

      <div className="flex items-center gap-2">
        <button
          type="button"
          className="rounded-full bg-solid px-3 py-1 text-[12px] text-onSolid disabled:opacity-60"
          data-testid="campus-tutor-submit"
          disabled={!canSubmit}
          onClick={() => {
            void submit();
          }}
        >
          {submitting ? t("campus.kaoyan.tutor.submitting") : t("campus.kaoyan.tutor.submit")}
        </button>
        {error ? (
          <span className="text-[12px] text-warnInk" data-testid="campus-tutor-error">
            {t(campusErrorKey(campusErrorInfo(error).code), {
              defaultValue: campusErrorInfo(error).message || t("campus.common.error"),
            })}
          </span>
        ) : null}
      </div>

      {result ? <GradingResultCard result={result} /> : null}
    </div>
  );
}
