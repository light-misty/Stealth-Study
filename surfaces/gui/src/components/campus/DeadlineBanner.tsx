import { useTranslation } from "react-i18next";
import type { DeadlineView } from "../../campus/types";
import { isCountdownHighlight } from "../../campus/utils";
import { Icon } from "../Icon";

// Deadline feed for the certificate track (CERT-13 / ADR-12): an in-app banner, never an
// OS notification. Reference dates carry the "official announcement wins" badge, because
// a guessed date shown without that caveat reads as fact (CERT-12).

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
          const highlight = isCountdownHighlight(node.days_left);
          return (
            <li
              key={node.id}
              className={
                highlight
                  ? "flex items-center gap-2 rounded-lg bg-warnSoft px-2 py-1"
                  : "flex items-center gap-2 px-2 py-1"
              }
              data-testid="campus-deadline-row"
              data-id={node.id}
              data-node-type={node.node_type}
              data-days-left={node.days_left}
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
