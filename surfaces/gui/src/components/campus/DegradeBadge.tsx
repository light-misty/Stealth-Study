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
    <div
      className="rounded-lg border border-warnInk/40 bg-warnSoft px-3 py-2 text-[12px] text-warnInk"
      role="status"
      data-testid="campus-degrade-badge"
      data-degrade-level={shown}
    >
      <div className="flex items-center gap-1.5">
        <Icon name="warning" size={13} />
        <span>{t(key)}</span>
      </div>
      {notice ? (
        <div className="mt-1 text-[12px] text-muted" data-testid="campus-degrade-notice-detail">
          {notice}
        </div>
      ) : null}
    </div>
  );
}
