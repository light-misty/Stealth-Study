import { useEffect, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Icon, type IconName } from "../Icon";

interface Props {
  testId: string;
  title: string;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
  icon?: IconName | null;
  wide?: boolean;
}

export function CampusDialog({
  testId,
  title,
  onClose,
  children,
  footer,
  icon = "pencil",
  wide = false,
}: Props) {
  const { t } = useTranslation();

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="gate-overlay" onClick={onClose}>
      <div
        aria-label={title}
        aria-modal="true"
        role="dialog"
        className={wide ? "dlg-card dlg-card--wide" : "dlg-card"}
        data-testid={testId}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="dlg-head">
          {icon ? (
            <span className="ib ib--brand">
              <Icon name={icon} size={16} />
            </span>
          ) : null}
          <h3 className="dlg-title">{title}</h3>
          <button
            type="button"
            className="icon-btn"
            onClick={onClose}
            data-testid={`${testId}-close`}
            aria-label={t("campus.profile.dialog_close")}
          >
            <Icon name="x" size={14} />
          </button>
        </div>
        <div className="dlg-body">{children}</div>
        {footer ? <div className="dlg-foot">{footer}</div> : null}
      </div>
    </div>
  );
}
