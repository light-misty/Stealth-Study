import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { getCommonErrors } from "../../../campus/api";
import type { GradingKind } from "../../../campus/types";
import { campusErrorInfo } from "../../../campus/utils";

interface CommonErrorRow {
  type: string;
  count: number;
  samples: string[];
}

export function CommonErrorsCard({
  profileId,
  kind,
  testIdPrefix = "campus-cet",
}: {
  profileId: string;
  kind?: GradingKind;
  /** The card sits on the station AND inside both grading workshops, so its testid needs a
   * per-instance prefix — three copies of `campus-cet-common-errors` in one document is exactly
   * the ambiguity 04 §2.2's `campus-<domain>-<action>` rule exists to prevent. */
  testIdPrefix?: string;
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

  if (error) {
    return (
      <div
        className="rounded-xl2 border border-warnInk/40 bg-warnSoft px-4 py-3 text-[13px] text-warnInk"
        data-testid={`${testIdPrefix}-common-errors-error`}
      >
        {t("campus.common.error")}
        {campusErrorInfo(error).retryable ? (
          <button
            type="button"
            className="ml-2 text-accent"
            onClick={() => setNonce((n) => n + 1)}
            data-testid={`${testIdPrefix}-common-errors-retry`}
          >
            {t("campus.common.retry")}
          </button>
        ) : null}
      </div>
    );
  }

  return (
    <div className="rounded-xl2 border border-line bg-panel px-4 py-3.5" data-testid={`${testIdPrefix}-common-errors`}>
      <div className="text-[13px] font-semibold text-ink">{t("campus.cet.errors.title")}</div>
      {loading ? null : rows.length === 0 ? (
        <div className="mt-1 text-[12px] text-faint" data-testid={`${testIdPrefix}-common-errors-empty`}>
          {t("campus.cet.errors.empty")}
        </div>
      ) : (
        <ol className="mt-2 grid gap-1.5">
          {rows.map((row, index) => (
            <li
              key={`${row.type}-${index}`}
              className="flex items-start gap-2 text-[12px]"
              data-testid={`${testIdPrefix}-common-error`}
              data-type={row.type}
              data-count={row.count}
            >
              <span className="text-faint w-4 shrink-0">{index + 1}</span>
              <span className="text-ink">{row.type}</span>
              <span className="text-muted">
                {t("campus.cet.errors.times_other", { count: row.count })}
              </span>
              {(row.samples ?? []).length > 0 ? (
                <span className="text-faint truncate">{(row.samples ?? []).join(" / ")}</span>
              ) : null}
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
