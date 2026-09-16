import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import {
  CampusApiError,
  createAssessment,
  finishAssessment,
  getAssessment,
  patchAssessment,
} from "../../../campus/api";
import type {
  Assessment,
  AssessmentFinishResult,
  AssessmentQuestion,
} from "../../../campus/types";
import { campusErrorInfo } from "../../../campus/utils";

const draftKeyFor = (profileId: string) => `ss.campus.cet.assessment.${profileId}`;
const AUTOSAVE_DELAY_MS = 400;
const SUBJECTIVE_TYPES = ["short_answer", "essay", "material", "lesson_plan", "practical"];
const SCORE_SECTIONS = ["listening", "reading", "writing_translation"] as const;

type Phase = "idle" | "loading" | "paper" | "result";

function hasPayload(q: AssessmentQuestion): boolean {
  if (!q.qtype || !q.stem) return false;
  if ((q.options ?? []).length > 0) return true;
  return q.qtype === "blank" || SUBJECTIVE_TYPES.includes(q.qtype);
}

function isDraftGone(err: unknown): boolean {
  return (
    err instanceof CampusApiError &&
    (err.code === "ASSESSMENT_NOT_FOUND" || err.status === 404)
  );
}

export function AssessmentFlow({ profileId }: { profileId: string }) {
  const { t } = useTranslation();
  const [phase, setPhase] = useState<Phase>(() =>
    window.localStorage.getItem(draftKeyFor(profileId)) ? "loading" : "idle",
  );
  const [assessment, setAssessment] = useState<Assessment | null>(null);
  const [result, setResult] = useState<AssessmentFinishResult | null>(null);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [error, setError] = useState<unknown>(null);
  const [saveError, setSaveError] = useState(false);
  const [savedAt, setSavedAt] = useState(0);
  const [busy, setBusy] = useState(false);
  const [nonce, setNonce] = useState(0);

  const dirtyRef = useRef<Record<string, string>>({});
  const timerRef = useRef<number | null>(null);
  const assessmentRef = useRef<Assessment | null>(null);
  assessmentRef.current = assessment;

  useEffect(() => {
    const key = draftKeyFor(profileId);
    const savedId = window.localStorage.getItem(key);
    if (!savedId) {
      setPhase("idle");
      return;
    }
    let alive = true;
    setPhase("loading");
    setError(null);
    getAssessment(savedId).then(
      (res) => {
        if (!alive) return;
        if (res.status === "finished" && res.scores) {
          setResult(null);
          setAnswers({});
          setAssessment(res);
          setPhase("result");
        } else {
          setResult(null);
          setAnswers(res.answers ?? {});
          setAssessment(res);
          setPhase("paper");
        }
      },
      (err) => {
        if (!alive) return;
        if (isDraftGone(err)) {
          window.localStorage.removeItem(key);
          setAssessment(null);
          setPhase("idle");
        } else {
          setError(err);
          setPhase("idle");
        }
      },
    );
    return () => {
      alive = false;
    };
  }, [profileId, nonce]);

  useEffect(
    () => () => {
      if (timerRef.current !== null) window.clearTimeout(timerRef.current);
    },
    [],
  );

  const flushSaves = useCallback(() => {
    const payload = dirtyRef.current;
    const current = assessmentRef.current;
    if (!Object.keys(payload).length || !current) return;
    dirtyRef.current = {};
    patchAssessment(current.id, current.profile_id, payload).then(
      () => {
        setSaveError(false);
        setSavedAt(Date.now());
      },
      () => {
        setSaveError(true);
        dirtyRef.current = { ...payload, ...dirtyRef.current };
      },
    );
  }, []);

  const scheduleSave = useCallback(() => {
    if (timerRef.current !== null) window.clearTimeout(timerRef.current);
    timerRef.current = window.setTimeout(() => {
      timerRef.current = null;
      flushSaves();
    }, AUTOSAVE_DELAY_MS);
  }, [flushSaves]);

  const setAnswer = (qid: string, value: string) => {
    setAnswers((prev) => (prev[qid] === value ? prev : { ...prev, [qid]: value }));
    dirtyRef.current[qid] = value;
    scheduleSave();
  };

  const onStart = () => {
    if (busy) return;
    setBusy(true);
    setError(null);
    createAssessment(profileId).then(
      (res) => {
        setResult(null);
        setAnswers(res.answers ?? {});
        setAssessment(res);
        window.localStorage.setItem(draftKeyFor(profileId), res.id);
        setPhase("paper");
        setBusy(false);
      },
      (err) => {
        setError(err);
        setBusy(false);
      },
    );
  };

  const onFinish = () => {
    const current = assessmentRef.current;
    if (!current || busy) return;
    if (timerRef.current !== null) {
      window.clearTimeout(timerRef.current);
      timerRef.current = null;
    }
    setBusy(true);
    setError(null);
    finishAssessment(current.id).then(
      (res) => {
        setResult(res);
        window.localStorage.removeItem(draftKeyFor(profileId));
        setPhase("result");
        setBusy(false);
      },
      (err) => {
        setError(err);
        setBusy(false);
      },
    );
  };

  const onRetry = () => {
    if (phase === "paper") {
      onFinish();
      return;
    }
    if (window.localStorage.getItem(draftKeyFor(profileId))) {
      setNonce((n) => n + 1);
    } else {
      onStart();
    }
  };

  const onAgain = () => {
    setResult(null);
    setAssessment(null);
    setAnswers({});
    setError(null);
    setPhase("idle");
  };

  const questions = useMemo(() => assessment?.questions ?? [], [assessment]);
  const answeredCount = useMemo(
    () => questions.filter((q) => (answers[q.id] ?? "").trim() !== "").length,
    [questions, answers],
  );
  const resumeTargetId = useMemo(
    () =>
      questions.find((q) => (answers[q.id] ?? "").trim() === "" && hasPayload(q))?.id ?? null,
    [questions, answers],
  );

  const errorBox = error ? (
    <div
      className="rounded-xl2 border border-warnInk/40 bg-warnSoft px-4 py-3 text-[13px] text-warnInk"
      data-testid="campus-cet-assessment-error"
    >
      {t("campus.common.error")}
      <span className="ml-1 text-faint">{campusErrorInfo(error).message}</span>
      {campusErrorInfo(error).retryable ? (
        <button type="button" className="ml-2 text-accent" onClick={onRetry}>
          {t("campus.common.retry")}
        </button>
      ) : null}
    </div>
  ) : null;

  const renderQuestion = (q: AssessmentQuestion): ReactNode => {
    const value = answers[q.id] ?? "";
    const options = q.options ?? [];
    let body: ReactNode;
    if (!hasPayload(q)) {
      body = (
        <div
          className="mt-1 text-[12px] text-faint"
          data-testid="campus-cet-assessment-question-missing"
        >
          {t("campus.cet.assessment.question_missing")}
        </div>
      );
    } else if (options.length > 0) {
      body = (
        <div className="mt-2 grid gap-1.5">
          {options.map((o) => (
            <button
              key={o.key}
              type="button"
              className={`rounded-lg2 border px-3 py-1.5 text-left text-[12px] ${
                value === o.key
                  ? "border-accent bg-accentSoft text-ink"
                  : "border-line bg-panel text-muted"
              }`}
              aria-pressed={value === o.key}
              data-testid="campus-cet-assessment-option"
              onClick={() => setAnswer(q.id, o.key)}
            >
              <span className="mr-2 font-semibold text-ink">{o.key}</span>
              <span>{o.text}</span>
            </button>
          ))}
        </div>
      );
    } else if (q.qtype === "blank") {
      body = (
        <input
          className="mt-2 w-full rounded-lg2 border border-line bg-panel px-3 py-1.5 text-[12px] text-ink"
          data-testid="campus-cet-assessment-blank"
          value={value}
          onChange={(e) => setAnswer(q.id, e.target.value)}
        />
      );
    } else {
      body = (
        <textarea
          className="mt-2 w-full rounded-lg2 border border-line bg-panel px-3 py-1.5 text-[12px] text-ink"
          rows={3}
          data-testid="campus-cet-assessment-text"
          value={value}
          onChange={(e) => setAnswer(q.id, e.target.value)}
        />
      );
    }
    return (
      <div
        key={q.id}
        className="rounded-xl2 border border-line bg-panel px-4 py-3"
        data-testid="campus-cet-assessment-question"
        data-qid={q.id}
        data-resume-target={resumeTargetId === q.id ? "true" : undefined}
      >
        {q.stem ? <div className="text-[13px] text-ink">{q.stem}</div> : null}
        {body}
      </div>
    );
  };

  const estimate = result
    ? result.estimate_total
    : assessment?.scores?.estimate_total ?? null;
  const scores = result?.scores ?? assessment?.scores ?? null;
  const gapRows = result?.gap_table ?? [];

  let content: ReactNode;
  if (phase === "loading") {
    content = (
      <div className="rounded-xl2 border border-line bg-panel px-4 py-3.5 text-[12px] text-muted">
        {t("campus.cet.assessment.loading")}
      </div>
    );
  } else if (phase === "idle") {
    content = (
      <div className="grid gap-3">
        {errorBox}
        <div className="rounded-xl2 border border-line bg-panel px-4 py-3.5">
          <div className="text-[13px] font-semibold text-ink">
            {t("campus.cet.assessment.title")}
          </div>
          <div className="mt-1 text-[12px] text-muted">
            {t("campus.cet.assessment.intro")}
          </div>
          <button
            type="button"
            className="mt-3 rounded-lg2 bg-accent px-4 py-1.5 text-[12px] font-semibold text-inkOnAccent disabled:opacity-50"
            data-testid="campus-cet-assessment-start"
            onClick={onStart}
            disabled={busy}
          >
            {t("campus.cet.assessment.start")}
          </button>
        </div>
      </div>
    );
  } else if (phase === "paper") {
    content = (
      <div className="grid gap-3" data-testid="campus-cet-assessment-paper">
        <div className="rounded-xl2 border border-line bg-panel px-4 py-3.5">
          <div className="text-[13px] font-semibold text-ink">
            {t("campus.cet.assessment.title")}
          </div>
          <div
            className="mt-1 text-[12px] text-muted"
            data-testid="campus-cet-assessment-progress"
            data-answered={answeredCount}
            data-total={questions.length}
          >
            {t("campus.cet.assessment.progress", {
              answered: answeredCount,
              total: questions.length,
            })}
          </div>
          {savedAt > 0 && !saveError ? (
            <div className="mt-1 text-[12px] text-faint">
              {t("campus.cet.assessment.saved")}
            </div>
          ) : null}
          {saveError ? (
            <div className="mt-1 text-[12px] text-warnInk">
              {t("campus.cet.assessment.save_error")}
            </div>
          ) : null}
        </div>
        {questions.map((q) => renderQuestion(q))}
        {errorBox}
        <button
          type="button"
          className="rounded-lg2 bg-accent px-4 py-1.5 text-[12px] font-semibold text-inkOnAccent disabled:opacity-50"
          data-testid="campus-cet-assessment-finish"
          onClick={onFinish}
          disabled={busy}
        >
          {t("campus.cet.assessment.finish")}
        </button>
      </div>
    );
  } else {
    content = (
      <div className="grid gap-3" data-testid="campus-cet-assessment-result">
        <div className="rounded-xl2 border border-line bg-panel px-4 py-3.5">
          <div className="text-[12px] text-muted">{t("campus.cet.assessment.estimate")}</div>
          <div
            className="text-[18px] font-semibold text-ink"
            data-testid="campus-cet-assessment-estimate"
          >
            {estimate}
          </div>
        </div>
        {scores ? (
          <div className="grid grid-cols-3 gap-2">
            {SCORE_SECTIONS.map((s) => (
              <div key={s} className="rounded-xl2 border border-line bg-panel px-3 py-2">
                <div className="text-[12px] text-faint">
                  {t(`campus.cet.assessment.section_${s}`)}
                </div>
                <div className="text-[13px] text-ink">{scores[s]}</div>
              </div>
            ))}
          </div>
        ) : null}
        {gapRows.length > 0 ? (
          <div className="rounded-xl2 border border-line bg-panel px-4 py-3.5">
            <div className="text-[13px] font-semibold text-ink">
              {t("campus.cet.assessment.gap_title")}
            </div>
            <table className="mt-2 w-full text-[12px]">
              <thead>
                <tr className="text-faint">
                  <th className="text-left font-normal" />
                  <th className="text-right font-normal">
                    {t("campus.cet.assessment.col_current")}
                  </th>
                  <th className="text-right font-normal">
                    {t("campus.cet.assessment.col_target")}
                  </th>
                  <th className="text-right font-normal">
                    {t("campus.cet.assessment.col_gap")}
                  </th>
                </tr>
              </thead>
              <tbody>
                {gapRows.map((row) => (
                  <tr
                    key={row.section}
                    className="border-t border-line"
                    data-testid="campus-cet-assessment-gap"
                    data-section={row.section}
                    data-gap={row.gap}
                  >
                    <td className="py-1 text-ink">
                      {t(`campus.cet.assessment.section_${row.section}`)}
                    </td>
                    <td className="py-1 text-right text-muted">{row.current}</td>
                    <td className="py-1 text-right text-muted">{row.target}</td>
                    <td className="py-1 text-right text-ink">{row.gap}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
        <button
          type="button"
          className="rounded-lg2 border border-line bg-panel px-4 py-1.5 text-[12px] text-muted"
          onClick={onAgain}
        >
          {t("campus.cet.assessment.again")}
        </button>
      </div>
    );
  }

  return <div className="grid gap-3">{content}</div>;
}
