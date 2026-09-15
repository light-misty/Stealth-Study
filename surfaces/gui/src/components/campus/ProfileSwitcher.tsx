import { useTranslation } from "react-i18next";
import type { ExamProfile } from "../../campus/types";
import { Icon } from "../Icon";

// The station's profile header (G-03). Archived profiles are hidden here — the backend
// keeps them for history, the switcher only offers what can be worked on.

export function ProfileSwitcher({
  profiles,
  activeId,
  onSwitch,
  onCreate,
  onArchive,
}: {
  profiles: ExamProfile[];
  activeId: string | null;
  onSwitch: (id: string) => void;
  onCreate: () => void;
  onArchive?: (id: string) => void;
}) {
  const { t } = useTranslation();
  const visible = profiles.filter((p) => p.status !== "archived");

  return (
    <div
      className="flex flex-wrap items-center gap-2"
      data-testid="campus-profile-switcher"
    >
      <span className="text-[12px] text-faint">{t("campus.profile.switch")}</span>

      {visible.length === 0 ? (
        <span className="text-[12px] text-muted" data-testid="campus-profile-empty">
          {t("campus.profile.empty")}
        </span>
      ) : (
        visible.map((p) => (
          <div key={p.id} className="flex items-center">
            <button
              type="button"
              className={
                p.id === activeId
                  ? "px-2.5 py-1 rounded-lg text-[13px] bg-accent text-white"
                  : "px-2.5 py-1 rounded-lg text-[13px] text-muted hover:text-ink border border-line"
              }
              onClick={() => onSwitch(p.id)}
              data-testid="campus-profile-item"
              data-profile-id={p.id}
              data-active={p.id === activeId ? "true" : "false"}
              title={p.id === activeId ? t("campus.profile.active_badge") : p.title}
            >
              {p.title}
            </button>
            {onArchive && (
              <button
                type="button"
                className="ml-1 p-1 text-faint hover:text-muted"
                onClick={() => onArchive(p.id)}
                data-testid={`campus-profile-archive-${p.id}`}
                title={t("campus.profile.archive")}
                aria-label={t("campus.profile.archive")}
              >
                <Icon name="archive" size={14} />
              </button>
            )}
          </div>
        ))
      )}

      <button
        type="button"
        className="px-2.5 py-1 rounded-lg text-[13px] text-muted hover:text-ink border border-dashed border-line"
        onClick={onCreate}
        data-testid="campus-profile-create"
      >
        {t("campus.profile.create")}
      </button>
    </div>
  );
}
