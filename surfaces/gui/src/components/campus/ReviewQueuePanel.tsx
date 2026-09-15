import { useTranslation } from "react-i18next";
import { useDueReviews } from "../../campus/hooks";
import type { ReviewDueItem } from "../../campus/types";
import { campusErrorInfo, campusErrorKey, nextIntervalDays } from "../../campus/utils";

// Today's review queue (D5/D6). Answering a card removes it straight away — the queue is
// a work list, not a log — and the next interval is previewed from the SM-2 ladder so the
// user can see what answering correctly buys them.

export function ReviewQueuePanel({
  profileId,
  dueItems,
  onResult,
}: {
  profileId: string;
  dueItems?: ReviewDueItem[];
  onResult?: (reviewId: string, correct: boolean) => void | Promise<void>;
}) {
  const { t } = useTranslation();
  const fetched = useDueReviews(dueItems ? null : profileId);
  const items = dueItems ?? fetched.items;
  const loading = dueItems ? false : fetched.loading;
  const error = dueItems ? null : fetched.error;
  const submit = onResult ?? fetched.submit;

  const label = (item: ReviewDueItem): string => {
    const payload = item.payload ?? {};
    return String(payload.word ?? payload.title ?? payload.id ?? item.item_id ?? item.id);
  };

  return (
    <div className="rounded-xl2 border border-line bg-panel" data-testid="campus-review-queue">
      <div className="flex items-center justify-between px-4 pt-3.5">
        <div className="text-[13px] font-semibold text-ink">{t("campus.review.due_today")}</div>
        <div className="text-[11px] text-faint" data-testid="campus-review-count">
          {items.length}
        </div>
      </div>

      {loading ? (
        <div className="px-4 py-3 text-[12px] text-faint" data-testid="campus-review-loading">
          {t("campus.common.loading")}
        </div>
      ) : null}

      {error ? (
        <div className="px-4 py-2 text-[12px] text-warnInk" data-testid="campus-review-error">
          {t(campusErrorKey(campusErrorInfo(error).code), {
            defaultValue: campusErrorInfo(error).message || t("campus.common.error"),
          })}
        </div>
      ) : null}

      {!loading && items.length === 0 ? (
        <div className="px-4 py-3 text-[12px] text-faint" data-testid="campus-review-empty">
          {t("campus.review.empty")}
        </div>
      ) : null}

      <ul className="mt-2 grid gap-2 px-4 pb-3.5">
        {items.map((item) => (
          <li
            key={item.id}
            className="flex items-center justify-between gap-2 rounded-lg border border-line px-3 py-2"
            data-testid="campus-review-item"
            data-id={item.id}
            data-item-type={item.item_type}
          >
            <div className="min-w-0">
              <div className="text-[12px] text-ink truncate">{label(item)}</div>
              <div className="text-[11px] text-faint" data-testid="campus-review-interval">
                {t("campus.review.interval", { days: nextIntervalDays(item.streak_right + 1) })}
              </div>
            </div>
            <div className="flex items-center gap-1.5">
              <button
                type="button"
                className="px-2.5 py-1 rounded-lg text-[12px] text-ok border border-okLine"
                onClick={() => void submit(item.id, true)}
                data-testid="campus-review-correct"
              >
                {t("campus.review.correct")}
              </button>
              <button
                type="button"
                className="px-2.5 py-1 rounded-lg text-[12px] text-danger border border-line"
                onClick={() => void submit(item.id, false)}
                data-testid="campus-review-wrong"
              >
                {t("campus.review.wrong")}
              </button>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
