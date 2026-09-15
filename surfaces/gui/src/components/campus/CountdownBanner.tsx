import { useTranslation } from "react-i18next";
import { daysUntil, isCountdownHighlight } from "../../campus/utils";
import { Icon } from "../Icon";

// Exam countdown shared by the tracks that carry an exam date. Days come from the
// calendar, not from a running clock — the same number all day long.

export function CountdownBanner({
  examDate,
  now,
}: {
  examDate: string | null;
  now?: Date;
}) {
  const { t } = useTranslation();
  const daysLeft = daysUntil(examDate, now ?? new Date());
  if (daysLeft === null) return null;

  const passed = daysLeft < 0;
  const highlight = isCountdownHighlight(daysLeft);

  return (
    <div
      className={
        highlight
          ? "rounded-xl2 border border-warnInk/50 bg-warnSoft px-4 py-2.5"
          : "rounded-xl2 border border-line bg-panel px-4 py-2.5"
      }
      role="status"
      data-testid="campus-countdown-banner"
      data-days-left={daysLeft}
      data-highlight={highlight ? "true" : "false"}
      data-passed={passed ? "true" : "false"}
    >
      <div className="flex items-center gap-1.5">
        <Icon name="clock" size={14} />
        <span className="text-[13px] text-ink">
          {passed
            ? t("campus.common.exam_passed")
            : t("campus.common.days_left", { count: daysLeft })}
        </span>
      </div>
    </div>
  );
}
