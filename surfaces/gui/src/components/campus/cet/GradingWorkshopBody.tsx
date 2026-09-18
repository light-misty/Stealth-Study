import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { getAttempt, listGradingHistory, submitGrading } from "../../../campus/api";
import type { Attempt, GradeResult, GradingKind } from "../../../campus/types";
import { campusErrorInfo } from "../../../campus/utils";
import { CommonErrorsCard } from "./CommonErrorsCard";
import { GradingResultCard } from "../GradingResultCard";
import { Icon, type IconName } from "../../Icon";

const HISTORY_PAGE_SIZE = 10;

// One grading workshop = one module card: 原文 → 结果 → 老毛病 → 历史, in that order, so the
// answer you just wrote stays the thing you see first. The station renders one workshop per
// grading domain (essay, translation), so the testid prefix is a parameter: sharing
// `campus-cet-grading-*` between two panels put duplicate data-testid values in one document
// (04 §2.2 reads a testid as campus-<domain>-<action>).

export function GradingWorkshopBody({
  profileId,
  kind,
  historySubject,
  title,
  desc,
  icon = "pencil",
  testIdPrefix = "campus-cet-grading",
}: {
  profileId: string;
  kind: GradingKind;
  historySubject?: string;
  title: string;
  desc: string;
  icon?: IconName;
  testIdPrefix?: string;
}) {
  const { t } = useTranslation();
  const [text, setText] = useState("");
  const [result, setResult] = useState<GradeResult | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<unknown>(null);
  const [history, setHistory] = useState<Attempt[]>([]);
  const [historyTotal, setHistoryTotal] = useState(0);
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
        setHistoryTotal(res?.total ?? 0);
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
      setHistoryTotal(res?.total ?? 0);
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
    <section className="mod">
      <div className="mod-head">
        <span className="ib ib--accent">
          <Icon name={icon} size={16} />
        </span>
        <div className="mod-head-text">
          <span className="mod-title">{title}</span>
          <span className="mod-desc">{desc}</span>
        </div>
        <div className="mod-acts">
          {historyTotal > 0 ? (
            <span className="sec-n" data-testid={`${testIdPrefix}-graded-count`}>
              {t("campus.cet.grading.graded_count", { count: historyTotal })}
            </span>
          ) : null}
        </div>
      </div>

      <div className="fill thin qcol">
        <div className="field">
          <span className="field-label">{t("campus.cet.grading.input_label")}</span>
          <textarea
            ref={textRef}
            className="textarea"
            rows={6}
            data-testid={`${testIdPrefix}-text`}
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
          <div className="word-foot">
            <span className="st-spacer" />
            <button
              type="button"
              className="btn btn--primary"
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

        {submitError ? (
          <div className="alert" data-testid={`${testIdPrefix}-error`}>
            <Icon name="warning" size={14} />
            <div className="alert-text">
              <span className="alert-title">{t("campus.common.error")}</span>
              <span className="alert-desc">{campusErrorInfo(submitError).message}</span>
            </div>
            <button
              type="button"
              className="btn btn--ghost btn--sm"
              onClick={onSubmit}
              disabled={submitting}
              data-testid={`${testIdPrefix}-retry`}
            >
              {t("campus.common.retry")}
            </button>
          </div>
        ) : null}

        {result ? (
          <div className="qcol" data-testid={`${testIdPrefix}-result`}>
            <GradingResultCard result={result} onLocate={locate} />
            <CommonErrorsCard
              profileId={profileId}
              kind={kind}
              testIdPrefix={testIdPrefix.replace(/-grading$/, "")}
            />
          </div>
        ) : null}

        <div className="sec">
          <div className="sec-text">
            <span className="sec-title">{t("campus.cet.grading.history_title")}</span>
          </div>
          {historyLoaded && history.length > 0 ? (
            <span className="sec-n">
              {t("campus.cet.grading.history_recent", { count: history.length })}
            </span>
          ) : null}
        </div>

        {!historyLoaded ? (
          <div className="stack-gap">
            <div className="sk" />
            <div className="sk" style={{ width: "64%" }} />
          </div>
        ) : history.length === 0 ? (
          <div className="body-text" data-testid={`${testIdPrefix}-history-empty`}>
            {t("campus.cet.grading.history_empty")}
          </div>
        ) : (
          <div className="rows">
            {history.map((item) => (
              <button
                key={item.id}
                type="button"
                className="lrow lrow--link"
                data-testid={`${testIdPrefix}-history-item`}
                data-attempt={item.id}
                onClick={() => openDetail(item.id)}
              >
                <div className="lrow-text">
                  <span className="lrow-title">{item.created_at.slice(0, 10)}</span>
                  <span className="lrow-meta">{item.user_answer}</span>
                </div>
                <div className="lrow-acts">
                  <span className="sec-n">{item.score ?? "—"}</span>
                  <Icon name="chevronRight" size={13} />
                </div>
              </button>
            ))}
          </div>
        )}

        {detail ? (
          <div className="sub" data-testid={`${testIdPrefix}-history-detail`} data-attempt={detail.id}>
            <div className="kv">
              <div className="kv-row">
                <span className="kv-k">{t("campus.cet.grading.detail_score")}</span>
                <span className="kv-v kv-v--mono">
                  {detail.score ?? "—"}
                  {detail.max_score != null ? ` / ${detail.max_score}` : ""}
                </span>
              </div>
              <div className="kv-row">
                <span className="kv-k">{t("campus.cet.grading.detail_answer")}</span>
                <span className="kv-v">{detail.user_answer}</span>
              </div>
            </div>
          </div>
        ) : null}
      </div>
    </section>
  );
}
