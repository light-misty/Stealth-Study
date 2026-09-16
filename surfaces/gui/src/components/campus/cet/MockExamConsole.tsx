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
import { campusErrorInfo } from "../../../campus/utils";

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
    <div
      className="rounded-xl2 border border-warnInk/40 bg-warnSoft px-4 py-3 text-[13px] text-warnInk"
      data-testid="campus-mock-error"
    >
      {t("campus.common.error")}
      <span className="ml-1 text-faint">{campusErrorInfo(error).message}</span>
    </div>
  ) : null;

  if (phase === "loading") {
    return (
      <div className="rounded-xl2 border border-line bg-panel px-4 py-3.5 text-[12px] text-muted">
        {t("campus.cet.mock.loading")}
      </div>
    );
  }

  if (phase === "idle") {
    return (
      <div className="grid gap-3">
        {errorBox}
        <div className="rounded-xl2 border border-line bg-panel px-4 py-3.5">
          <div className="text-[13px] font-semibold text-ink">
            {t("campus.cet.mock.paper_title")}
          </div>
          <div className="mt-1 text-[12px] text-muted">{t("campus.cet.mock.intro")}</div>
          <button
            type="button"
            className="mt-3 rounded-lg2 bg-accent px-4 py-1.5 text-[12px] font-semibold text-inkOnAccent disabled:opacity-50"
            data-testid="campus-mock-start"
            onClick={onStart}
            disabled={busy}
          >
            {t("campus.cet.mock.start")}
          </button>
        </div>
      </div>
    );
  }

  const exam = view;
  if (!exam) return null;

  const showResult = phase === "result";
  const isOngoing = phase === "ongoing" && exam.status === "ongoing";
  const expired = remaining <= 0 || exam.stage_expired;
  const isLastStage = exam.current_stage === "reading_translation";

  const answerAreas = STAGE_AREA.map((area) => {
    const locked =
      showResult ||
      !isOngoing ||
      area.stage !== exam.current_stage ||
      exam.locked_stages.includes(area.stage);
    return (
      <div key={area.stage} className="rounded-xl2 border border-line bg-panel px-4 py-3">
        <div className="flex items-center justify-between">
          <div className="text-[12px] font-semibold text-ink">{t(area.labelKey)}</div>
          {locked ? (
            <div className="text-[11px] text-faint">{t("campus.cet.mock.locked")}</div>
          ) : null}
        </div>
        <textarea
          className="mt-1.5 w-full rounded-lg2 border border-line bg-panel px-3 py-2 text-[12px] text-ink disabled:opacity-60"
          rows={area.stage === "writing" ? 8 : 6}
          data-testid={area.testid}
          disabled={locked}
          value={drafts[area.stage] ?? ""}
          onChange={(e) => setDraft(exam.id, area.stage, e.target.value)}
        />
      </div>
    );
  });

  const sectionRows = result ? Object.entries(result.by_section) : [];

  return (
    <div
      className="grid gap-3"
      data-testid={showResult ? undefined : "campus-mock-console"}
    >
      {showResult ? (
        <div
          className="rounded-xl2 border border-line bg-panel px-4 py-3.5"
          data-testid="campus-mock-result"
        >
          <div className="text-[13px] font-semibold text-ink">
            {t("campus.cet.mock.result_title")}
          </div>
          <div className="mt-1 text-[12px] text-muted">
            {t("campus.cet.mock.estimate")}
          </div>
          <div
            className="text-[18px] font-semibold text-ink"
            data-testid="campus-mock-estimate"
          >
            {result ? result.estimate_score : exam.estimate_score}
          </div>
          {sectionRows.length > 0 ? (
            <ul className="mt-2 grid gap-1.5">
              {sectionRows.map(([section, row]) => (
                <li
                  key={section}
                  className="flex items-center gap-2 text-[12px]"
                  data-testid="campus-mock-section"
                  data-section={section}
                  data-earned={row.earned}
                  data-max={row.max}
                >
                  <span className="text-ink">
                    {t(`campus.cet.assessment.section_${section}`)}
                  </span>
                  <span className="text-muted">
                    {row.earned} / {row.max}
                  </span>
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : (
        <div className="rounded-xl2 border border-line bg-panel px-4 py-3.5">
          <div className="flex items-baseline justify-between">
            <div
              className="text-[13px] font-semibold text-ink"
              data-testid="campus-mock-stage"
              data-stage={exam.current_stage}
            >
              {t(`campus.cet.mock.stage_${exam.current_stage}`)}
            </div>
            <div
              className={`text-[13px] font-semibold ${expired ? "text-warnInk" : "text-ink"}`}
              data-testid="campus-mock-timer"
              data-remaining={remaining}
            >
              {formatClock(remaining)}
            </div>
          </div>
          <div className="mt-1 text-[12px] text-faint">{t("campus.cet.mock.timer_label")}</div>
          {paused ? (
            <button
              type="button"
              className="mt-2 rounded-lg2 border border-line bg-panel px-3 py-1 text-[12px] text-muted"
              data-testid="campus-mock-resume"
              onClick={onResume}
            >
              {t("campus.cet.mock.resume")}
            </button>
          ) : (
            <button
              type="button"
              className="mt-2 rounded-lg2 border border-line bg-panel px-3 py-1 text-[12px] text-muted"
              data-testid="campus-mock-pause"
              onClick={onPause}
            >
              {t("campus.cet.mock.pause")}
            </button>
          )}
          {import.meta.env.DEV ? (
            <button
              type="button"
              className="mt-2 ml-2 rounded-lg2 border border-dashed border-line px-3 py-1 text-[12px] text-faint"
              data-hook="fast-forward"
              data-testid="fast-forward-hook"
              onClick={() => setRemaining(0)}
            >
              {t("campus.cet.mock.fast_forward")}
            </button>
          ) : null}
          {expired ? (
            <div className="mt-2 grid gap-2">
              <div className="text-[12px] text-warnInk">
                {t("campus.cet.mock.stage_expired_label")}
              </div>
              {isLastStage ? (
                <button
                  type="button"
                  className="rounded-lg2 bg-accent px-4 py-1.5 text-[12px] font-semibold text-inkOnAccent disabled:opacity-50"
                  data-testid="campus-mock-submit"
                  onClick={onSubmit}
                  disabled={busy}
                >
                  {t("campus.cet.mock.submit")}
                </button>
              ) : (
                <button
                  type="button"
                  className="rounded-lg2 bg-accent px-4 py-1.5 text-[12px] font-semibold text-inkOnAccent disabled:opacity-50"
                  data-testid="campus-mock-advance"
                  onClick={onAdvance}
                  disabled={busy}
                >
                  {t("campus.cet.mock.advance")}
                </button>
              )}
            </div>
          ) : null}
          {errorBox}
        </div>
      )}
      {answerAreas}
    </div>
  );
}
