import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { getCommonErrors } from "../../../campus/api";
import type { GradingKind } from "../../../campus/types";
import { campusErrorInfo } from "../../../campus/utils";
import { Icon } from "../../Icon";

interface CommonErrorRow {
  type: string;
  count: number;
  samples: string[];
}

// The card lives in two frames: embedded under a grading workshop (.sub) and as the CET
// station's own module (.mod). Same rows, different head weight — the pane gets the icon
// block and the sample-size footnote because there it is the whole screen.
// 卡片会同时出现在站点与两个批改工作坊里，所以 testid 前缀是参数：一份文档里三张同名
// 卡片正是 04 §2.2 的 campus-<domain>-<action> 规则要避免的歧义。

export function CommonErrorsCard({
  profileId,
  kind,
  testIdPrefix = "campus-cet",
  framed = false,
  onGotoTab,
}: {
  profileId: string;
  kind?: GradingKind;
  testIdPrefix?: string;
  framed?: boolean;
  onGotoTab?: (key: string) => void;
}) {
  const { t } = useTranslation();
  const [rows, setRows] = useState<CommonErrorRow[]>([]);
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
    getCommonErrors(profileId, kind).then(
      (res) => {
        if (!alive) return;
        setRows(res?.top3 ?? []);
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
  }, [profileId, kind, nonce]);

  const head = (
    <div className={framed ? "mod-head" : "sec"}>
      {framed ? (
        <span className="ib ib--brand">
          <Icon name="warning" size={16} />
        </span>
      ) : null}
      <div className={framed ? "mod-head-text" : "sec-text"}>
        <span className={framed ? "mod-title" : "sec-title"}>{t("campus.cet.errors.title")}</span>
        {framed ? <span className="mod-desc">{t("campus.cet.errors.hint")}</span> : null}
      </div>
      {framed && rows.length > 0 ? (
        <div className="mod-acts">
          <span className="sec-n">{t("campus.cet.errors.rank_note")}</span>
        </div>
      ) : null}
    </div>
  );

  if (error) {
    return (
      <div className="alert" data-testid={`${testIdPrefix}-common-errors-error`}>
        <Icon name="warning" size={14} />
        <div className="alert-text">
          <span className="alert-title">{t("campus.common.error")}</span>
        </div>
        {campusErrorInfo(error).retryable ? (
          <button
            type="button"
            className="btn btn--ghost btn--sm"
            onClick={() => setNonce((n) => n + 1)}
            data-testid={`${testIdPrefix}-common-errors-retry`}
          >
            {t("campus.common.retry")}
          </button>
        ) : null}
      </div>
    );
  }

  const body = loading ? (
    <div className="stack-gap">
      <div className="sk" />
      <div className="sk" style={{ width: "70%" }} />
    </div>
  ) : rows.length === 0 ? (
    <div className="body-text" data-testid={`${testIdPrefix}-common-errors-empty`}>
      {t("campus.cet.errors.empty")}
    </div>
  ) : (
    <>
      <ol className="rank-list">
        {rows.map((row, index) => (
          <li key={`${row.type}-${index}`}>
            <div
              className={index === 0 ? "rank rank--1" : "rank"}
              data-testid={`${testIdPrefix}-common-error`}
              data-type={row.type}
              data-count={row.count}
            >
              <span className="rank-n">{index + 1}</span>
              <div className="rank-body">
                <div className="rank-t">
                  <span className="rank-name">{row.type}</span>
                  <span className="rank-times">
                    {t("campus.cet.errors.times_other", { count: row.count })}
                  </span>
                </div>
                {(row.samples ?? []).length > 0 ? (
                  <span className="rank-x">{(row.samples ?? []).join(" / ")}</span>
                ) : null}
              </div>
            </div>
          </li>
        ))}
      </ol>
      {framed && onGotoTab ? (
        <div className="mod-foot">
          <span className="body-text">{t("campus.cet.errors.rank_note")}</span>
          <span className="st-spacer" />
          <button
            type="button"
            className="btn btn--soft btn--sm"
            onClick={() => onGotoTab("essay")}
            data-testid={`${testIdPrefix}-common-errors-goto`}
          >
            {t("campus.cet.errors.goto")}
            <Icon name="chevronRight" size={12} />
          </button>
        </div>
      ) : null}
    </>
  );

  if (framed) {
    return (
      <section className="mod" data-testid={`${testIdPrefix}-common-errors`}>
        {head}
        <div className="fill thin qcol">{body}</div>
      </section>
    );
  }

  return (
    <div className="sub" data-testid={`${testIdPrefix}-common-errors`}>
      {head}
      <div className="qcol">{body}</div>
    </div>
  );
}
