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
import { Icon } from "../../Icon";

// 定级测评在真实实现里是整卷一次铺开的长卷，所以卷面本身就是滚动区，卡头钉住
// 「已答 X/N + 自动保存」，滚到最后一题也看得见进度（设计稿 campus-cet.css 的说明）。

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

export function AssessmentFlow({
  profileId,
  onGotoTab,
}: {
  profileId: string;
  onGotoTab?: (key: string) => void;
}) {
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
    getAssessment(profileId, savedId).then(
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
    finishAssessment(profileId, current.id).then(
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
    <div className="alert" data-testid="campus-cet-assessment-error">
      <Icon name="warning" size={14} />
      <div className="alert-text">
        <span className="alert-title">{t("campus.common.error")}</span>
        <span className="alert-desc">{campusErrorInfo(error).message}</span>
      </div>
      {campusErrorInfo(error).retryable ? (
        <button type="button" className="btn btn--ghost btn--sm" onClick={onRetry}>
          {t("campus.common.retry")}
        </button>
      ) : null}
    </div>
  ) : null;

  const renderQuestion = (q: AssessmentQuestion, position: number): ReactNode => {
    const value = answers[q.id] ?? "";
    const options = q.options ?? [];
    let body: ReactNode;
    if (!hasPayload(q)) {
      body = (
        <span className="q-tip" data-testid="campus-cet-assessment-question-missing">
          {t("campus.cet.assessment.question_missing")}
        </span>
      );
    } else if (options.length > 0) {
      body = (
        <div className="opts">
          {options.map((o) => (
            <button
              key={o.key}
              type="button"
              className={value === o.key ? "opt is-on" : "opt"}
              aria-pressed={value === o.key}
              data-testid="campus-cet-assessment-option"
              onClick={() => setAnswer(q.id, o.key)}
            >
              <span className="opt-k">{o.key}</span>
              <span>{o.text}</span>
            </button>
          ))}
        </div>
      );
    } else if (q.qtype === "blank") {
      body = (
        <input
          className="input"
          data-testid="campus-cet-assessment-blank"
          value={value}
          onChange={(e) => setAnswer(q.id, e.target.value)}
        />
      );
    } else {
      body = (
        <textarea
          className="textarea"
          rows={4}
          data-testid="campus-cet-assessment-text"
          value={value}
          onChange={(e) => setAnswer(q.id, e.target.value)}
        />
      );
    }
    return (
      <div
        key={q.id}
        className="q"
        data-testid="campus-cet-assessment-question"
        data-qid={q.id}
        data-resume-target={resumeTargetId === q.id ? "true" : undefined}
      >
        <div className="q-head">
          {q.qtype ? <span className="tag tag--brand">{t(`campus.common.qtype.${q.qtype}`)}</span> : null}
          {!hasPayload(q) ? (
            <span className="tag tag--muted">{t("campus.cet.assessment.missing_tag")}</span>
          ) : null}
          <span className="q-no">{t("campus.cet.assessment.qno", { index: position + 1 })}</span>
        </div>
        {q.stem ? <p className="q-stem">{q.stem}</p> : null}
        {body}
        {hasPayload(q) && SUBJECTIVE_TYPES.includes(q.qtype ?? "") ? (
          <span className="q-tip">{t("campus.cet.assessment.subjective_tip")}</span>
        ) : null}
      </div>
    );
  };

  const estimate = result
    ? result.estimate_total
    : assessment?.scores?.estimate_total ?? null;
  const scores = result?.scores ?? assessment?.scores ?? null;
  const gapRows = result?.gap_table ?? [];

  const head = (
    <div className="mod-head">
      <span className="ib ib--accent">
        <Icon name="activity" size={16} />
      </span>
      <div className="mod-head-text">
        <span className="mod-title">{t("campus.cet.assessment.title")}</span>
        <span className="mod-desc">{t("campus.cet.assessment.intro")}</span>
      </div>
      {phase === "paper" ? (
        <div className="mod-acts">
          <span
            className="sec-n"
            data-testid="campus-cet-assessment-progress"
            data-answered={answeredCount}
            data-total={questions.length}
          >
            {t("campus.cet.assessment.progress", {
              answered: answeredCount,
              total: questions.length,
            })}
          </span>
        </div>
      ) : null}
    </div>
  );

  let body: ReactNode;
  if (phase === "loading") {
    body = (
      <div className="stack-gap">
        <div className="sk" style={{ width: 140 }} />
        <div className="sk" />
        <div className="sk" style={{ width: "68%" }} />
        <span className="body-text">{t("campus.cet.assessment.loading")}</span>
      </div>
    );
  } else if (phase === "idle") {
    body = (
      <>
        {errorBox}
        <div className="empty">
          <span className="ib ib--brand">
            <Icon name="activity" size={17} />
          </span>
          <span className="empty-title">{t("campus.cet.assessment.idle_title")}</span>
          <span className="empty-desc">{t("campus.cet.assessment.intro")}</span>
          <button
            type="button"
            className="btn btn--primary"
            data-testid="campus-cet-assessment-start"
            onClick={onStart}
            disabled={busy}
          >
            {window.localStorage.getItem(draftKeyFor(profileId))
              ? t("campus.cet.assessment.resume")
              : t("campus.cet.assessment.start")}
          </button>
        </div>
      </>
    );
  } else if (phase === "paper") {
    body = (
      <div className="stack" data-testid="campus-cet-assessment-paper">
        <div className="bar">
          <i
            style={{
              "--w": `${questions.length ? Math.round((answeredCount / questions.length) * 100) : 0}%`,
            } as Record<string, string>}
          />
        </div>
        <div className="fill thin qcol">{questions.map((q, i) => renderQuestion(q, i))}</div>
        {errorBox}
        <div className="mod-foot">
          {saveError ? (
            <span className="field-err" data-testid="campus-cet-assessment-save-error">
              {t("campus.cet.assessment.save_error")}
            </span>
          ) : savedAt > 0 ? (
            <span className="ai-note" data-testid="campus-cet-assessment-saved">
              <Icon name="check" size={12} />
              {t("campus.cet.assessment.saved")}
            </span>
          ) : null}
          <span className="st-spacer" />
          <button
            type="button"
            className="btn btn--primary"
            data-testid="campus-cet-assessment-finish"
            onClick={onFinish}
            disabled={busy}
          >
            {t("campus.cet.assessment.finish")}
          </button>
        </div>
      </div>
    );
  } else {
    body = (
      <>
        <div className="fill thin qcol" data-testid="campus-cet-assessment-result">
          <div className="stat">
            <span className="stat-k">{t("campus.cet.assessment.estimate")}</span>
            <div className="score">
              <span className="score-n" data-testid="campus-cet-assessment-estimate">
                {estimate}
              </span>
              <span className="score-u">{t("campus.cet.assessment.estimate_unit")}</span>
            </div>
          </div>
          {scores ? (
            <div className="sec-cells">
              {SCORE_SECTIONS.map((s) => (
                <div className="sec-cell" key={s}>
                  <span className="sec-cell-k">{t(`campus.cet.assessment.section_${s}`)}</span>
                  <span className="sec-cell-v">{scores[s]}</span>
                </div>
              ))}
            </div>
          ) : null}
          {gapRows.length > 0 ? (
            <>
              <div className="sec">
                <div className="sec-text">
                  <span className="sec-title">{t("campus.cet.assessment.gap_title")}</span>
                </div>
              </div>
              <table className="tbl">
                <thead>
                  <tr>
                    <th />
                    <th>{t("campus.cet.assessment.col_current")}</th>
                    <th>{t("campus.cet.assessment.col_target")}</th>
                    <th>{t("campus.cet.assessment.col_gap")}</th>
                  </tr>
                </thead>
                <tbody>
                  {gapRows.map((row) => (
                    <tr
                      key={row.section}
                      data-testid="campus-cet-assessment-gap"
                      data-section={row.section}
                      data-gap={row.gap}
                    >
                      <td>{t(`campus.cet.assessment.section_${row.section}`)}</td>
                      <td className="n">{row.current}</td>
                      <td className="n">{row.target}</td>
                      <td className="n">{Number(row.gap) > 0 ? <span className="neg">+{row.gap}</span> : row.gap}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          ) : null}
          <span className="ai-note">
            <Icon name="sparkle" size={12} />
            {t("campus.common.ai_notice")}
          </span>
          {errorBox}
        </div>
        <div className="mod-foot">
          <button type="button" className="btn btn--ghost" onClick={onAgain} data-testid="campus-cet-assessment-again">
            {t("campus.cet.assessment.again")}
          </button>
          <span className="st-spacer" />
          {onGotoTab ? (
            <button
              type="button"
              className="btn btn--soft btn--sm"
              onClick={() => onGotoTab("vocab")}
              data-testid="campus-cet-assessment-goto-vocab"
            >
              {t("campus.cet.assessment.goto_vocab")}
              <Icon name="chevronRight" size={12} />
            </button>
          ) : null}
        </div>
      </>
    );
  }

  return (
    <section className="mod" data-testid="campus-cet-assessment">
      {head}
      {body}
    </section>
  );
}
