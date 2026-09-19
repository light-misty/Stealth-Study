import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import type { ExamProfile } from "../../campus/types";
import { Icon } from "../Icon";

// The station's profile header (G-03). Archived profiles are hidden here — the backend
// keeps them for history, the switcher only offers what can be worked on.
// 横向胶囊条而不是下拉：全部档案要一眼可见。改名/归档收进单个 ⋮ 菜单，只作用于
// 当前档案，操作入口不再随档案数量增多。

export function ProfileSwitcher({
  profiles,
  activeId,
  onSwitch,
  onCreate,
  onArchive,
  onRename,
  onDelete,
  onShowArchived,
}: {
  profiles: ExamProfile[];
  activeId: string | null;
  onSwitch: (id: string) => void;
  onCreate: () => void;
  onArchive?: (id: string) => void;
  onRename?: (id: string) => void;
  onDelete?: (id: string) => void;
  onShowArchived?: () => void;
}) {
  const { t } = useTranslation();
  const visible = profiles.filter((p) => p.status !== "archived");
  const archivedCount = profiles.length - visible.length;
  const [manageOpen, setManageOpen] = useState(false);
  const active = visible.find((p) => p.id === activeId) ?? null;
  const finished = active?.status === "finished";
  const canManage =
    active !== null && (finished ? Boolean(onDelete) : Boolean(onRename || onArchive));

  useEffect(() => {
    if (!manageOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setManageOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [manageOpen]);

  const run = (action: (id: string) => void, id: string) => {
    setManageOpen(false);
    action(id);
  };

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
            <button
              key={p.id}
              type="button"
              className={p.id === activeId ? "who-pill is-on" : "who-pill"}
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
          ))
        )}
      </div>

      {active && canManage ? (
        <div className="who-manage">
          <button
            type="button"
            className="icon-btn"
            onClick={() => setManageOpen(true)}
            data-testid="campus-profile-manage"
            title={t("campus.profile.manage")}
            aria-label={t("campus.profile.manage")}
            aria-haspopup="menu"
            aria-expanded={manageOpen}
          >
            <Icon name="moreHorizontal" size={13} />
          </button>
          {manageOpen ? (
            <>
              <div className="who-menu-backdrop" onClick={() => setManageOpen(false)} />
              <div
                className="who-menu"
                role="menu"
                aria-label={active.title}
                data-testid="campus-profile-manage-menu"
              >
                <span className="who-menu-title" title={active.title}>
                  {active.title}
                </span>
                {finished && onDelete ? (
                  <button
                    type="button"
                    role="menuitem"
                    className="who-menu-item who-menu-item--danger"
                    onClick={() => run(onDelete, active.id)}
                    data-testid={`campus-profile-delete-${active.id}`}
                  >
                    <Icon name="trash" size={13} />
                    {t("campus.profile.delete")}
                  </button>
                ) : (
                  <>
                    {onRename ? (
                      <button
                        type="button"
                        role="menuitem"
                        className="who-menu-item"
                        onClick={() => run(onRename, active.id)}
                        data-testid={`campus-profile-rename-${active.id}`}
                      >
                        <Icon name="pencil" size={13} />
                        {t("campus.profile.rename")}
                      </button>
                    ) : null}
                    {onArchive ? (
                      <button
                        type="button"
                        role="menuitem"
                        className="who-menu-item"
                        onClick={() => run(onArchive, active.id)}
                        data-testid={`campus-profile-archive-${active.id}`}
                      >
                        <Icon name="archive" size={13} />
                        {t("campus.profile.archive")}
                      </button>
                    ) : null}
                  </>
                )}
              </div>
            </>
          ) : null}
        </div>
      ) : null}

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
  );
}
