import { useTranslation } from "react-i18next";
import { useDueReviews } from "../../campus/hooks";
import type { ReviewDueItem } from "../../campus/types";
import { campusErrorInfo, campusErrorKey, nextIntervalDays } from "../../campus/utils";
import { Icon } from "../Icon";

// Today's review queue (D5/D6). Answering a card removes it straight away — the queue is
// a work list, not a log — and the next interval is previewed from the SM-2 ladder so the
// user can see what answering correctly buys them.
// 判卷按钮不给橙：一次判卷不算模块的主行动，绿/红描边即语义（设计稿 .btn--right/--wrong）。

export function ReviewQueuePanel({
  profileId,
  dueItems,
  onResult,
  loading: loadingProp,
}: {
  profileId: string;
  dueItems?: ReviewDueItem[];
  onResult?: (reviewId: string, correct: boolean) => void | Promise<void>;
  loading?: boolean;
}) {
  const { t } = useTranslation();
  const fetched = useDueReviews(dueItems ? null : profileId);
  const items = dueItems ?? fetched.items;
  const loading = loadingProp ?? (dueItems ? false : fetched.loading);
  const error = dueItems ? null : fetched.error;
  const submit = onResult ?? fetched.submit;

  const label = (item: ReviewDueItem): string => {
    const payload = item.payload ?? {};
    return String(payload.word ?? payload.title ?? payload.id ?? item.item_id ?? item.id);
  };

  return (
    <section className="mod" data-testid="campus-review-queue">
      <div className="mod-head">
        <span className="ib ib--accent">
          <Icon name="refresh" size={16} />
        </span>
        <div className="mod-head-text">
          <span className="mod-title">{t("campus.review.due_today")}</span>
          <span className="mod-desc">{t("campus.review.hint")}</span>
        </div>
        <div className="mod-acts">
          <span className="sec-n" data-testid="campus-review-count">
            {items.length}
          </span>
        </div>
      </div>

      {loading ? (
        <div className="stack-gap" data-testid="campus-review-loading">
          <div className="sk" />
          <div className="sk" style={{ width: "72%" }} />
          <span className="body-text">{t("campus.common.loading")}</span>
        </div>
      ) : null}

      {error ? (
        <div className="alert" data-testid="campus-review-error">
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

      {!loading && items.length === 0 ? (
        <div className="empty" data-testid="campus-review-empty">
          <span className="ib ib--brand">
            <Icon name="check" size={17} />
          </span>
          <span className="empty-title">{t("campus.review.empty")}</span>
        </div>
      ) : null}

      {items.length > 0 ? (
        <div className="rows fill thin">
          {items.map((item) => (
            <div
              key={item.id}
              className="lrow"
              data-testid="campus-review-item"
              data-id={item.id}
              data-item-type={item.item_type}
            >
              <div className="lrow-text">
                <span className="lrow-title">{label(item)}</span>
                <span className="lrow-meta" data-testid="campus-review-interval">
                  {t("campus.review.interval", { days: nextIntervalDays(item.streak_right + 1) })}
                </span>
              </div>
              <div className="lrow-acts">
                <button
                  type="button"
                  className="btn btn--right btn--sm"
                  onClick={() => void submit(item.id, true)}
                  data-testid="campus-review-correct"
                >
                  <Icon name="check" size={13} />
                  {t("campus.review.correct")}
                </button>
                <button
                  type="button"
                  className="btn btn--wrong btn--sm"
                  onClick={() => void submit(item.id, false)}
                  data-testid="campus-review-wrong"
                >
                  <Icon name="x" size={13} />
                  {t("campus.review.wrong")}
                </button>
              </div>
            </div>
          ))}
        </div>
      ) : null}
    </section>
  );
}
