import { useTranslation } from "react-i18next";
import type { DeadlineTier, DeadlineView } from "../../campus/types";
import { deadlineTier, isCountdownHighlight } from "../../campus/utils";
import { Icon } from "../Icon";

// Deadline feed for the certificate track (CERT-13 / ADR-12): an in-app banner, never an
// OS notification. Rows carry the `deadline_snapshot` tier (D-30/D-7/D-1 bands), graded
// visually from the strongest (D-1) to the plain tier; when the feed omits the tier it is
// re-derived from days_left with the same rules. Reference dates carry the "official
// announcement wins" badge, because a guessed date shown without that caveat reads as
// fact (CERT-12).

const TIER_CLASS: Record<DeadlineTier, string> = {
  d1: "bg-warnInk/15 font-semibold",
  d7: "bg-warnSoft font-medium",
  d30: "text-warnInk",
  today: "bg-danger/15 font-semibold",
  overdue: "opacity-60",
  normal: "",
};

export function DeadlineBanner({ views }: { views: DeadlineView[] }) {
  const { t } = useTranslation();
  if (!views || views.length === 0) return null;

  const ordered = [...views].sort((a, b) => a.date.localeCompare(b.date));

  return (
    <div
      className="rounded-xl2 border border-line bg-panel px-4 py-2.5"
      role="status"
      data-testid="campus-deadline-banner"
    >
      <div className="flex items-center gap-1.5 text-[13px] font-semibold text-ink">
        <Icon name="clock" size={14} />
        <span>{t("campus.cert.deadline.banner")}</span>
      </div>

      <ul className="mt-1.5 grid gap-1">
        {ordered.map((node) => {
          const tier = node.tier ?? deadlineTier(node.days_left);
          const highlight = isCountdownHighlight(node.days_left);
          return (
            <li
              key={node.id}
              className={`flex items-center gap-2 rounded-lg px-2 py-1 ${TIER_CLASS[tier] ?? ""}`}
              data-testid="campus-deadline-row"
              data-id={node.id}
              data-node-type={node.node_type}
              data-days-left={node.days_left}
              data-tier={tier}
              data-highlight={highlight ? "true" : "false"}
            >
              <span className="text-[12px] text-ink">
                {t(`campus.cert.deadline.node.${node.node_type}`)}
              </span>
              <span className="text-[11px] text-faint">{node.date}</span>
              <span className="text-[11px] text-muted">
                {t("campus.common.days_left", { count: node.days_left })}
              </span>
              {node.is_reference ? (
                <span
                  className="text-[11px] text-warnInk"
                  data-testid="campus-deadline-reference"
                  title={t("campus.cert.deadline.reference_notice")}
                >
                  {t("campus.cert.deadline.reference_notice")}
                </span>
              ) : null}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
