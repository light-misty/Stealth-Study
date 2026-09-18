import { useTranslation } from "react-i18next";
import { daysUntil, isCountdownHighlight } from "../../campus/utils";
import { Icon } from "../Icon";

// Exam countdown shared by the tracks that carry an exam date. Days come from the
// calendar, not from a running clock — the same number all day long.
// 右栏首卡（设计稿的 .hero）：日期与剩余天数是主角，计划完成率与目标分只是脚注；
// 只有 30/7/1/0 天这一档才升到 warn，平时保持安静。

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
  if (daysLeft === null) return null;

  const passed = daysLeft < 0;
  const highlight = isCountdownHighlight(daysLeft);
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
      data-days-left={daysLeft}
      data-highlight={highlight ? "true" : "false"}
      data-passed={passed ? "true" : "false"}
    >
      <div className="hero-kicker">
        <Icon name="calendar" size={13} />
        <span>{t("campus.station.countdown_kicker", { date: examDate })}</span>
      </div>

      {passed ? (
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

      {planRate != null ? (
        <div className="bar bar--brand">
          <i style={{ "--w": `${Math.round(planRate * 100)}%` } as Record<string, string>} />
        </div>
      ) : null}

      {meta.length > 0 ? <div className="hero-meta">{meta.join(" · ")}</div> : null}
    </div>
  );
}
