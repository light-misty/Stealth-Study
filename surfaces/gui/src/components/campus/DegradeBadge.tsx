import { useTranslation } from "react-i18next";
import { degradeNoticeKey } from "../../campus/utils";
import type { DegradeLevel } from "../../campus/types";
import { Icon } from "../Icon";

// Acceptance ② of 07 §5 T16: a degraded result must never travel silently — the badge
// is rendered whenever degrade_level >= 1 (03 §5-3), on top of the result card.

export function DegradeBadge({
  level,
  notice,
}: {
  level: DegradeLevel | number | null;
  notice?: string | null;
}) {
  const { t } = useTranslation();
  const key = degradeNoticeKey(level);
  if (!key) return null;
  const shown = Math.min(Math.floor(level ?? 0), 3);

  return (
    <div className="alert" role="status" data-testid="campus-degrade-badge" data-degrade-level={shown}>
      <Icon name="warning" size={14} />
      <div className="alert-text">
        <span className="alert-title">{t(key)}</span>
        {notice ? <span className="alert-desc" data-testid="campus-degrade-notice-detail">{notice}</span> : null}
      </div>
    </div>
  );
}
