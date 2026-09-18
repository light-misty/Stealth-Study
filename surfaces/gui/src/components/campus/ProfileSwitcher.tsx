import { useTranslation } from "react-i18next";
import type { ExamProfile } from "../../campus/types";
import { Icon } from "../Icon";

// The station's profile header (G-03). Archived profiles are hidden here — the backend
// keeps them for history, the switcher only offers what can be worked on.
// 横向胶囊条而不是下拉：全部档案要一眼可见。改名 / 归档是低频动作，hover 才现形，
// 常驻会把条挤乱（设计稿 campus.css 的 .who 一节）。

export function ProfileSwitcher({
  profiles,
  activeId,
  onSwitch,
  onCreate,
  onArchive,
  onRename,
  onShowArchived,
}: {
  profiles: ExamProfile[];
  activeId: string | null;
  onSwitch: (id: string) => void;
  onCreate: () => void;
  onArchive?: (id: string) => void;
  onRename?: (id: string) => void;
  onShowArchived?: () => void;
}) {
  const { t } = useTranslation();
  const visible = profiles.filter((p) => p.status !== "archived");
  const archivedCount = profiles.length - visible.length;

  return (
    <div className="who" data-testid="campus-profile-switcher">
      <span className="who-l">{t("campus.profile.switch")}</span>

      <div className="who-list">
        {visible.length === 0 ? (
          <span className="who-l" data-testid="campus-profile-empty">
            {t("campus.profile.empty")}
          </span>
        ) : (
          visible.map((p) => (
            <div key={p.id} className={p.id === activeId ? "who-item is-on" : "who-item"}>
              <button
                type="button"
                className="who-pill"
                onClick={() => onSwitch(p.id)}
                data-testid="campus-profile-item"
                data-profile-id={p.id}
                data-active={p.id === activeId ? "true" : "false"}
                title={p.id === activeId ? t("campus.profile.active_badge") : p.title}
                aria-pressed={p.id === activeId}
              >
                {p.id === activeId ? <span className="dot" /> : null}
                {p.title}
              </button>
              <span className="who-tools">
                {onRename ? (
                  <button
                    type="button"
                    className="icon-btn"
                    onClick={() => onRename(p.id)}
                    data-testid={`campus-profile-rename-${p.id}`}
                    title={t("campus.profile.rename")}
                    aria-label={t("campus.profile.rename")}
                  >
                    <Icon name="pencil" size={13} />
                  </button>
                ) : null}
                {onArchive ? (
                  <button
                    type="button"
                    className="icon-btn icon-btn--danger"
                    onClick={() => onArchive(p.id)}
                    data-testid={`campus-profile-archive-${p.id}`}
                    title={t("campus.profile.archive")}
                    aria-label={t("campus.profile.archive")}
                  >
                    <Icon name="archive" size={13} />
                  </button>
                ) : null}
              </span>
            </div>
          ))
        )}

        <button
          type="button"
          className="btn btn--ghost btn--sm"
          onClick={onCreate}
          data-testid="campus-profile-create"
        >
          <Icon name="plus" size={13} />
          {t("campus.profile.create")}
        </button>

        {onShowArchived && archivedCount > 0 ? (
          <button
            type="button"
            className="btn btn--text btn--sm"
            onClick={onShowArchived}
            data-testid="campus-profile-archived-entry"
          >
            <Icon name="archive" size={13} />
            {t("campus.archived.title")}
            <span className="num" data-testid="campus-profile-archived-count">
              {archivedCount}
            </span>
          </button>
        ) : null}
      </div>
    </div>
  );
}
