import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { getAttempt, listGradingHistory, submitGrading } from "../../../campus/api";
import type { Attempt, GradeResult, GradingKind } from "../../../campus/types";
import { campusErrorInfo } from "../../../campus/utils";
import { CommonErrorsCard } from "./CommonErrorsCard";
import { GradingResultCard } from "../GradingResultCard";

const HISTORY_PAGE_SIZE = 10;

export function GradingWorkshopBody({
  profileId,
  kind,
  historySubject,
  testIdPrefix = "campus-cet-grading",
}: {
  profileId: string;
  kind: GradingKind;
  historySubject?: string;
  /** The station renders one workshop per grading domain (essay, translation), so the testid
   * prefix is a parameter: sharing `campus-cet-grading-*` between two panels put duplicate
   * `data-testid` values in one document (04 §2.2 reads a testid as campus-<domain>-<action>). */
  testIdPrefix?: string;
}) {
  const { t } = useTranslation();
  const [text, setText] = useState("");
  const [result, setResult] = useState<GradeResult | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<unknown>(null);
  const [history, setHistory] = useState<Attempt[]>([]);
  const [historyLoaded, setHistoryLoaded] = useState(false);
  const [detail, setDetail] = useState<Attempt | null>(null);
  const textRef = useRef<HTMLTextAreaElement | null>(null);

  useEffect(() => {
    if (!profileId) return;
    let alive = true;
    listGradingHistory(profileId, { kind, page: 1, pageSize: HISTORY_PAGE_SIZE }).then(
      (res) => {
        if (!alive) return;
        setHistory(res?.items ?? []);
        setHistoryLoaded(true);
      },
      () => {
        if (!alive) return;
        setHistoryLoaded(true);
      },
    );
    return () => {
      alive = false;
    };
  }, [profileId, kind, historySubject, result]);

  const refreshHistory = () => {
    listGradingHistory(profileId, { kind, page: 1, pageSize: HISTORY_PAGE_SIZE }).then((res) => {
      setHistory(res?.items ?? []);
      setHistoryLoaded(true);
    });
  };

  const onSubmit = () => {
    if (!text.trim() || submitting) return;
    setSubmitting(true);
    setSubmitError(null);
    submitGrading({ profileId, kind, answer: text }).then(
      (res) => {
        setResult(res);
        setSubmitting(false);
        refreshHistory();
      },
      (err) => {
        setSubmitError(err);
        setSubmitting(false);
      },
    );
  };

  const locate = (offset: number) => {
    const el = textRef.current;
    if (!el) return;
    const original = result?.errors.find((e) => e.offset === offset)?.original ?? "";
    el.focus();
    el.setSelectionRange(offset, offset + original.length);
  };

  const openDetail = (attemptId: string) => {
    getAttempt(profileId, attemptId).then((res) => setDetail(res));
  };

  return (
    <div className="grid gap-3">
      <div className="rounded-xl2 border border-line bg-panel px-4 py-3.5">
        <div className="text-[13px] font-semibold text-ink">
          {t("campus.cet.grading.input_label")}
        </div>
        <textarea
          ref={textRef}
          className="mt-2 w-full rounded-lg2 border border-line bg-panel px-3 py-2 text-[12px] text-ink"
          rows={8}
          data-testid={`${testIdPrefix}-text`}
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
        {submitError ? (
          <div
            className="mt-2 rounded-xl2 border border-warnInk/40 bg-warnSoft px-3 py-2 text-[12px] text-warnInk"
            data-testid={`${testIdPrefix}-error`}
          >
            {t("campus.common.error")}
            <span className="ml-1 text-faint">{campusErrorInfo(submitError).message}</span>
            <button
              type="button"
              className="ml-2 text-accent"
              onClick={onSubmit}
              disabled={submitting}
              data-testid={`${testIdPrefix}-retry`}
            >
              {t("campus.common.retry")}
            </button>
          </div>
        ) : null}
        <div className="mt-3">
          <button
            type="button"
            className="rounded-lg2 bg-accent px-4 py-1.5 text-[12px] font-semibold text-inkOnAccent disabled:opacity-50"
            data-testid={`${testIdPrefix}-submit`}
            onClick={onSubmit}
            disabled={submitting || !text.trim()}
          >
            {submitting
              ? t("campus.cet.grading.submitting")
              : t("campus.cet.grading.submit")}
          </button>
        </div>
      </div>

      {result ? (
        <div className="grid gap-3" data-testid={`${testIdPrefix}-result`}>
          <GradingResultCard result={result} onLocate={locate} />
          <CommonErrorsCard
            profileId={profileId}
            kind={kind}
            testIdPrefix={testIdPrefix.replace(/-grading$/, "")}
          />
        </div>
      ) : null}

      <div className="rounded-xl2 border border-line bg-panel px-4 py-3.5">
        <div className="text-[13px] font-semibold text-ink">
          {t("campus.cet.grading.history_title")}
        </div>
        {!historyLoaded ? null : history.length === 0 ? (
          <div
            className="mt-1 text-[12px] text-faint"
            data-testid={`${testIdPrefix}-history-empty`}
          >
            {t("campus.cet.grading.history_empty")}
          </div>
        ) : (
          <ul className="mt-2 grid gap-1.5">
            {history.map((item) => (
              <li key={item.id}>
                <button
                  type="button"
                  className="flex w-full items-center justify-between rounded-lg2 border border-line px-3 py-1.5 text-left text-[12px] text-muted"
                  data-testid={`${testIdPrefix}-history-item`}
                  data-attempt={item.id}
                  onClick={() => openDetail(item.id)}
                >
                  <span className="text-ink">{item.created_at.slice(0, 10)}</span>
                  <span>{item.score ?? "—"}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
        {detail ? (
          <div
            className="mt-2 rounded-lg2 border border-line px-3 py-2 text-[12px]"
            data-testid={`${testIdPrefix}-history-detail`}
            data-attempt={detail.id}
          >
            <div className="text-muted">
              <span className="text-faint">{t("campus.cet.grading.detail_score")}</span>
              <span className="ml-1 text-ink">
                {detail.score ?? "—"}
                {detail.max_score != null ? ` / ${detail.max_score}` : ""}
              </span>
            </div>
            <div className="mt-1 text-muted">
              <span className="text-faint">{t("campus.cet.grading.detail_answer")}</span>
              <span className="ml-1 text-ink">{detail.user_answer}</span>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}
