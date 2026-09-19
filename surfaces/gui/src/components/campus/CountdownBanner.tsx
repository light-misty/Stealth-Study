import { useTranslation } from "react-i18next";
import { daysUntil, isCountdownHighlight } from "../../campus/utils";
import { Icon } from "../Icon";

// Exam countdown shared by the tracks that carry an exam date. Days come from the
// calendar, not from a running clock — the same number all day long.
// 右栏首卡（设计稿的 .hero）：日期与剩余天数是主角，计划完成率与目标分只是脚注；
// 只有 30/7/1/0 天这一档才升到 warn，平时保持安静。
// 没设考试日期也要把卡留在原位（设计稿的右栏是三张定高卡，缺一张就塌成半屏），
// 但数字一律留白：没有日期就没有倒计时，这里不拿 0 天冒充。

const NO_DATE = "--";

export function CountdownBanner({
  examDate,
  targetScore,
  currentEstimate,
  planRate,
  now,
}: {
  examDate: string | null;
  targetScore?: number | null;
  currentEstimate?: number | null;
  planRate?: number | null;
  now?: Date;
}) {
  const { t } = useTranslation();
  const daysLeft = daysUntil(examDate, now ?? new Date());
  const passed = daysLeft !== null && daysLeft < 0;
  const highlight = daysLeft !== null && isCountdownHighlight(daysLeft);
  const meta = [
    planRate == null
      ? null
      : t("campus.station.hero_plan_rate", { rate: Math.round(planRate * 100) }),
    targetScore == null ? null : t("campus.station.hero_target", { score: targetScore }),
    currentEstimate == null
      ? null
      : t("campus.station.hero_estimate", { score: currentEstimate }),
  ].filter((row): row is string => Boolean(row));

  return (
    <div
      className={highlight ? "hero is-near" : "hero"}
      role="status"
      data-testid="campus-countdown-banner"
      data-days-left={daysLeft ?? ""}
      data-highlight={highlight ? "true" : "false"}
      data-passed={passed ? "true" : "false"}
    >
      <div className="hero-kicker">
        <Icon name="calendar" size={13} />
        <span>
          {examDate
            ? t("campus.station.countdown_kicker", { date: examDate })
            : t("campus.station.countdown_no_date")}
        </span>
      </div>

      {daysLeft === null ? (
        <div className="hero-num-row">
          <span className="hero-num">{NO_DATE}</span>
          <span className="hero-unit">{t("campus.station.countdown_unit", { count: 0 })}</span>
        </div>
      ) : passed ? (
        <div className="hero-num-row">
          <span className="hero-unit">{t("campus.common.exam_passed")}</span>
        </div>
      ) : (
        <div className="hero-num-row">
          <span className="hero-num">{daysLeft}</span>
          <span className="hero-unit">
            {t("campus.station.countdown_unit", { count: daysLeft })}
          </span>
        </div>
      )}

      <div className="bar bar--brand">
        <i style={{ "--w": `${Math.round((planRate ?? 0) * 100)}%` } as Record<string, string>} />
      </div>

      <div className="hero-meta">
        {meta.length > 0
          ? meta.join(" · ")
          : t(examDate ? "campus.station.hero_nothing_yet" : "campus.station.hero_set_exam_date")}
      </div>
    </div>
  );
}
