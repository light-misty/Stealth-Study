import { useTranslation } from "react-i18next";
import type { DeadlineView } from "../../campus/types";
import { deadlineTier, isCountdownHighlight } from "../../campus/utils";
import { Icon } from "../Icon";

// Deadline feed for the certificate track (CERT-13 / ADR-12): an in-app banner, never an
// OS notification. Rows carry the `deadline_snapshot` tier (D-30/D-7/D-1 bands), graded
// visually from the strongest (D-1) to the plain tier; when the feed omits the tier it is
// re-derived from days_left with the same rules. Reference dates carry the "official
// announcement wins" badge, because a guessed date shown without that caveat reads as
// fact (CERT-12).
// 事务侧的临期语义（warn / danger）与学习侧的掌握度语义（绿黄红）互不借用。
// 设计稿的证书 hero 是「一个主数字 + 最近节点 + 节点表」：主数字取最近一个还没过去的节点，
// 全部节点都过期时退回最后一个，没有节点时整张卡留在原位但数字留白。

const NO_DATE = "--";

function shortDate(date: string): string {
  return date.length >= 10 ? date.slice(5) : date;
}

export function DeadlineBanner({ views }: { views: DeadlineView[] }) {
  const { t } = useTranslation();
  const ordered = [...(views ?? [])].sort((a, b) => a.date.localeCompare(b.date));
  const upcoming = ordered.find((node) => node.days_left >= 0);
  const nearest = upcoming ?? ordered[ordered.length - 1] ?? null;
  const highlight = nearest !== null && isCountdownHighlight(nearest.days_left);

  const left = (daysLeft: number): string => {
    if (daysLeft < 0) return t("campus.station.dl_overdue");
    if (daysLeft === 0) return t("campus.station.dl_today");
    return t("campus.station.dl_days", { count: daysLeft });
  };

  return (
    <div
      className={highlight && upcoming ? "hero is-near" : "hero"}
      role="status"
      data-testid="campus-deadline-banner"
      data-empty={nearest ? "false" : "true"}
    >
      <div className="hero-kicker">
        <Icon name="flag" size={13} />
        <span>{t("campus.cert.deadline.banner")}</span>
      </div>

      {nearest ? (
        <>
          <div className="hero-num-row">
            {nearest.days_left >= 0 ? (
              <>
                <span className="hero-num">{nearest.days_left}</span>
                <span className="hero-unit">
                  {t("campus.station.countdown_unit", { count: nearest.days_left })}
                </span>
              </>
            ) : (
              <span className="hero-unit">{t("campus.station.dl_overdue")}</span>
            )}
          </div>
          <div className="hero-meta">
            {t("campus.station.dl_nearest", {
              node: t(`campus.cert.deadline.node.${nearest.node_type}`),
              date: nearest.date,
            })}
          </div>
        </>
      ) : (
        <>
          <div className="hero-num-row">
            <span className="hero-num">{NO_DATE}</span>
            <span className="hero-unit">
              {t("campus.station.countdown_unit", { count: 0 })}
            </span>
          </div>
          <div className="hero-meta">{t("campus.station.dl_none")}</div>
        </>
      )}

      <div className="dl">
        {ordered.map((node) => {
          const tier = node.tier ?? deadlineTier(node.days_left);
          return (
            <div
              key={node.id}
              className="dl-row"
              data-testid="campus-deadline-row"
              data-id={node.id}
              data-node-type={node.node_type}
              data-days-left={node.days_left}
              data-tier={tier}
              data-highlight={isCountdownHighlight(node.days_left) ? "true" : "false"}
            >
              <span className="dl-name">
                {t(`campus.cert.deadline.node.${node.node_type}`)}
              </span>
              <span className="dl-date">{shortDate(node.date)}</span>
              <span className="dl-left">{left(node.days_left)}</span>
              {node.is_reference ? (
                <span
                  className="tag tag--warn dl-ref"
                  data-testid="campus-deadline-reference"
                  title={t("campus.cert.deadline.reference_notice")}
                >
                  {t("campus.cert.deadline.reference_notice")}
                </span>
              ) : null}
            </div>
          );
        })}
      </div>
    </div>
  );
}
