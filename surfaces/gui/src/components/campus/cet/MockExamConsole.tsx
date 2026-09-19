import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  advanceMockStage,
  createMockExam,
  getMockExam,
  pauseMockExam,
  submitMockExam,
} from "../../../campus/api";
import type {
  MockExamView,
  MockStage,
  MockSubmitResult,
} from "../../../campus/types";
import { campusErrorInfo, campusErrorKey } from "../../../campus/utils";
import { Icon } from "../../Icon";

// 三阶段计时模考：阶段条说「现在能写哪张卡」，计时器是这一屏最重要的数字，收卡锁定
// 比「还没写」更明确 —— 保留正文但压暗并挂锁标。快进只在 DEV 下出现，样卷名也照实
// 标注为调试用（设计稿 campus-cet.css 的说明）。

const draftKeyFor = (profileId: string) => `ss.campus.cet.mock.${profileId}`;
const stageDraftKey = (examId: string, stage: MockStage) =>
  `ss.campus.cet.mock.${examId}.${stage}`;

const STAGE_AREA: { stage: MockStage; testid: string; labelKey: string }[] = [
  { stage: "writing", testid: "campus-mock-essay", labelKey: "campus.cet.mock.answer_writing" },
  {
    stage: "listening",
    testid: "campus-mock-listening",
    labelKey: "campus.cet.mock.answer_listening",
  },
  {
    stage: "reading_translation",
    testid: "campus-mock-reading",
    labelKey: "campus.cet.mock.answer_reading",
  },
];

function formatClock(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

export function MockExamConsole({ profileId }: { profileId: string }) {
  const { t } = useTranslation();
  const [phase, setPhase] = useState<"loading" | "idle" | "ongoing" | "result">(() =>
    window.localStorage.getItem(draftKeyFor(profileId)) ? "loading" : "idle",
  );
  const [view, setView] = useState<MockExamView | null>(null);
  const [result, setResult] = useState<MockSubmitResult | null>(null);
  const [remaining, setRemaining] = useState(0);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [paused, setPaused] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const pausedAtRef = useRef<number | null>(null);

  useEffect(() => {
    const key = draftKeyFor(profileId);
    const savedId = window.localStorage.getItem(key);
    if (!savedId) {
      setPhase("idle");
      return;
    }
    let alive = true;
    getMockExam(profileId, savedId).then(
      (res) => {
        if (!alive) return;
        setView(res);
        setRemaining(res.remaining_seconds);
        setDrafts({
          writing: window.localStorage.getItem(stageDraftKey(res.id, "writing")) ?? "",
          listening: window.localStorage.getItem(stageDraftKey(res.id, "listening")) ?? "",
          reading_translation:
            window.localStorage.getItem(stageDraftKey(res.id, "reading_translation")) ?? "",
        });
        setPhase(res.status === "ongoing" ? "ongoing" : "result");
      },
      () => {
        if (!alive) return;
        window.localStorage.removeItem(key);
        setPhase("idle");
      },
    );
    return () => {
      alive = false;
    };
  }, [profileId]);

  useEffect(() => {
    if (phase !== "ongoing" || paused || !view) return;
    const timer = window.setInterval(() => {
      setRemaining((r) => (r > 0 ? r - 1 : 0));
    }, 1000);
    return () => window.clearInterval(timer);
  }, [phase, paused, view]);

  const loadDrafts = useCallback((examId: string) => {
    setDrafts({
      writing: window.localStorage.getItem(stageDraftKey(examId, "writing")) ?? "",
      listening: window.localStorage.getItem(stageDraftKey(examId, "listening")) ?? "",
      reading_translation:
        window.localStorage.getItem(stageDraftKey(examId, "reading_translation")) ?? "",
    });
  }, []);

  const onStart = () => {
    if (busy) return;
    setBusy(true);
    setError(null);
    createMockExam(profileId, t("campus.cet.mock.paper_title")).then(
      (res) => {
        window.localStorage.setItem(draftKeyFor(profileId), res.id);
        loadDrafts(res.id);
        return getMockExam(profileId, res.id).then((fresh) => {
          setView(fresh);
          setRemaining(fresh.remaining_seconds);
          setPhase("ongoing");
          setBusy(false);
        });
      },
      (err) => {
        setError(err);
        setBusy(false);
      },
    );
  };

  const setDraft = (examId: string, stage: MockStage, value: string) => {
    setDrafts((prev) => ({ ...prev, [stage]: value }));
    window.localStorage.setItem(stageDraftKey(examId, stage), value);
  };

  const onPause = () => {
    pausedAtRef.current = Date.now();
    setPaused(true);
  };

  const onResume = () => {
    if (!view) return;
    const seconds = Math.max(
      0,
      Math.round((Date.now() - (pausedAtRef.current ?? Date.now())) / 1000),
    );
    pausedAtRef.current = null;
    setPaused(false);
    pauseMockExam(profileId, view.id, seconds).then((fresh) => {
      setView(fresh);
      setRemaining(fresh.remaining_seconds);
    });
  };

  const onAdvance = () => {
    if (!view || busy) return;
    const next: MockStage =
      view.current_stage === "writing" ? "listening" : "reading_translation";
    setBusy(true);
    setError(null);
    advanceMockStage(profileId, view.id, next).then(
      () =>
        getMockExam(profileId, view.id).then((fresh) => {
          setView(fresh);
          setRemaining(fresh.remaining_seconds);
          loadDrafts(fresh.id);
          setBusy(false);
        }),
      (err) => {
        setError(err);
        setBusy(false);
      },
    );
  };

  const onSubmit = () => {
    if (!view || busy) return;
    setBusy(true);
    setError(null);
    submitMockExam(profileId, view.id).then(
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

  const errorBox = error ? (
    <div className="alert" data-testid="campus-mock-error">
      <Icon name="warning" size={14} />
      <div className="alert-text">
        <span className="alert-title">{t("campus.common.error")}</span>
        <span className="alert-desc">
          {t(campusErrorKey(campusErrorInfo(error).code), {
            defaultValue: campusErrorInfo(error).message || t("campus.common.error"),
          })}
        </span>
      </div>
    </div>
  ) : null;

  const head = (
    <div className="mod-head">
      <span className="ib ib--accent">
        <Icon name="timer" size={16} />
      </span>
      <div className="mod-head-text">
        <span className="mod-title">{t("campus.cet.mock.paper_title")}</span>
        <span className="mod-desc">{t("campus.cet.mock.intro")}</span>
      </div>
    </div>
  );

  if (phase === "loading") {
    return (
      <section className="mod">
        {head}
        <div className="stack-gap">
          <div className="sk" />
          <div className="sk" style={{ width: "66%" }} />
        </div>
        <span className="body-text">{t("campus.cet.mock.loading")}</span>
      </section>
    );
  }

  if (phase === "idle") {
    return (
      <section className="mod">
        {head}
        <div className="empty">
          <span className="ib ib--brand">
            <Icon name="timer" size={17} />
          </span>
          <span className="empty-title">{t("campus.cet.mock.idle_title")}</span>
          <span className="empty-desc">{t("campus.cet.mock.intro")}</span>
          <button
            type="button"
            className="btn btn--primary"
            data-testid="campus-mock-start"
            onClick={onStart}
            disabled={busy}
          >
            {t("campus.cet.mock.start")}
          </button>
        </div>
        {errorBox}
      </section>
    );
  }

  const exam = view;
  if (!exam) return null;

  const showResult = phase === "result";
  const isOngoing = phase === "ongoing" && exam.status === "ongoing";
  const expired = remaining <= 0 || exam.stage_expired;
  const isLastStage = exam.current_stage === "reading_translation";
  const stageIndex = STAGE_AREA.findIndex((area) => area.stage === exam.current_stage);

  const stageCells = STAGE_AREA.map((area) => {
    const current = area.stage === exam.current_stage && !showResult;
    const done = showResult || exam.locked_stages.includes(area.stage);
    const lockedButNotCurrent = !current && done;
    return (
      <div
        key={area.stage}
        className={current ? "mstage is-on" : lockedButNotCurrent ? "mstage is-done" : "mstage"}
        data-testid="campus-mock-stage-cell"
        data-stage={area.stage}
        data-state={current ? "on" : lockedButNotCurrent ? "done" : "todo"}
      >
        <span className="mstage-k">
          <Icon name={current ? "pencil" : lockedButNotCurrent ? "check" : "lock"} size={12} />
          {current
            ? t("campus.cet.mock.stage_running")
            : lockedButNotCurrent
              ? t("campus.cet.mock.stage_done")
              : t("campus.cet.mock.stage_todo")}
        </span>
        <span className="mstage-t">{t(`campus.cet.mock.stage_${area.stage}`)}</span>
        {current ? <span className="mstage-n">{formatClock(remaining)}</span> : null}
        {lockedButNotCurrent ? (
          <span className="mstage-n">{t("campus.cet.mock.locked")}</span>
        ) : null}
      </div>
    );
  });

  const answerAreas = STAGE_AREA.map((area) => {
    const locked =
      showResult ||
      !isOngoing ||
      area.stage !== exam.current_stage ||
      exam.locked_stages.includes(area.stage);
    return (
      <div key={area.stage} className={locked ? "answer is-locked" : "answer"}>
        <div className="answer-h">
          <span className="answer-t">{t(area.labelKey)}</span>
          {locked ? (
            <span className="tag tag--muted">
              <Icon name="lock" size={11} />
              {t("campus.cet.mock.locked")}
            </span>
          ) : (
            <span
              className="tag tag--accent"
              data-testid="campus-mock-stage"
              data-stage={exam.current_stage}
            >
              {t("campus.cet.mock.current_stage")}
            </span>
          )}
        </div>
        <textarea
          className="textarea"
          rows={area.stage === "writing" ? 8 : 5}
          placeholder={locked ? t("campus.cet.mock.locked_note") : undefined}
          data-testid={area.testid}
          disabled={locked}
          value={drafts[area.stage] ?? ""}
          onChange={(e) => setDraft(exam.id, area.stage, e.target.value)}
        />
      </div>
    );
  });

  const sectionRows = result ? Object.entries(result.by_section) : [];
  const estimateScore = result ? result.estimate_score : exam.estimate_score;

  const resultBlock = showResult ? (
    <div className="sub" data-testid="campus-mock-result">
      <div className="sec">
        <div className="sec-text">
          <span className="sec-title">{t("campus.cet.mock.result_title")}</span>
          <span className="sec-desc">{t("campus.cet.mock.result_hint")}</span>
        </div>
      </div>
      <div className="stat">
        <span className="stat-k">{t("campus.cet.mock.estimate")}</span>
        <div className="score">
          <span className="score-n" data-testid="campus-mock-estimate">
            {estimateScore ?? "—"}
          </span>
          <span className="score-u">{t("campus.cet.assessment.estimate_unit")}</span>
        </div>
      </div>
      {sectionRows.length > 0 ? (
        <div className="sec-cells">
          {sectionRows.map(([section, row]) => (
            <div
              className="sec-cell"
              key={section}
              data-testid="campus-mock-section"
              data-section={section}
              data-earned={row.earned}
              data-max={row.max}
            >
              <span className="sec-cell-k">{t(`campus.cet.assessment.section_${section}`)}</span>
              <span className="sec-cell-v">
                {row.earned} / {row.max}
              </span>
            </div>
          ))}
        </div>
      ) : null}
      <span className="ai-note">
        <Icon name="sparkle" size={12} />
        {t("campus.common.ai_notice")}
      </span>
    </div>
  ) : null;

  const timerBlock = isOngoing ? (
    <div className="sub sub--ring">
      <div className="timer-row">
        <div className="stack">
          <span className="timer-k">
            {expired
              ? t("campus.cet.mock.stage_expired_label")
              : t("campus.cet.mock.timer_label")}
          </span>
          <span
            className={expired ? "timer is-over" : "timer"}
            data-testid="campus-mock-timer"
            data-remaining={remaining}
          >
            {formatClock(remaining)}
          </span>
        </div>
        <span className="st-spacer" />
        <div className="mod-acts">
          {paused ? (
            <button
              type="button"
              className="btn btn--ghost btn--sm"
              data-testid="campus-mock-resume"
              onClick={onResume}
            >
              <Icon name="play" size={12} />
              {t("campus.cet.mock.resume")}
            </button>
          ) : (
            <button
              type="button"
              className="btn btn--ghost btn--sm"
              data-testid="campus-mock-pause"
              onClick={onPause}
            >
              <Icon name="pause" size={12} />
              {t("campus.cet.mock.pause")}
            </button>
          )}
          {import.meta.env.DEV ? (
            <button
              type="button"
              className="btn btn--text btn--sm"
              data-hook="fast-forward"
              data-testid="fast-forward-hook"
              onClick={() => setRemaining(0)}
            >
              <Icon name="forward" size={12} />
              {t("campus.cet.mock.fast_forward")}
            </button>
          ) : null}
        </div>
      </div>
    </div>
  ) : null;

  return (
    <section className="mod" data-testid="campus-mock">
      {head}
      <div className="stack" data-testid={showResult ? undefined : "campus-mock-console"}>
        {resultBlock}
        <div className="mstages">{stageCells}</div>
        {timerBlock}

        <div className="fill thin qcol">{answerAreas}</div>
        {errorBox}

        <div className="mod-foot">
          <span className="sec-n">
            {t("campus.cet.mock.stage_of", {
              index: stageIndex + 1,
              total: STAGE_AREA.length,
            })}
          </span>
          <span className="st-spacer" />
          {expired && isOngoing ? (
            isLastStage ? (
              <button
                type="button"
                className="btn btn--primary"
                data-testid="campus-mock-submit"
                onClick={onSubmit}
                disabled={busy}
              >
                {t("campus.cet.mock.submit")}
              </button>
            ) : (
              <button
                type="button"
                className="btn btn--primary"
                data-testid="campus-mock-advance"
                onClick={onAdvance}
                disabled={busy}
              >
                {t("campus.cet.mock.advance")}
              </button>
            )
          ) : null}
        </div>
      </div>
    </section>
  );
}
