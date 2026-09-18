import { useEffect, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Icon } from "../Icon";

interface Props {
  testId: string;
  title: string;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
  width?: string;
}

export function CampusDialog({
  testId,
  title,
  onClose,
  children,
  footer,
  width = "w-[440px]",
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
        className={`${width} max-h-[80vh] max-w-[92vw] overflow-y-auto rounded-xl2 border border-line bg-panel p-4 shadow-2xl`}
        data-testid={testId}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start gap-2">
          <h3 className="text-[14px] font-semibold leading-[20px] text-ink">{title}</h3>
          <button
            type="button"
            className="ml-auto p-1 text-faint hover:text-muted"
            onClick={onClose}
            data-testid={`${testId}-close`}
            aria-label={t("campus.profile.dialog_close")}
          >
            <Icon name="x" size={14} />
          </button>
        </div>
        <div className="mt-2">{children}</div>
        {footer ? <div className="mt-3.5 flex items-center justify-end gap-2">{footer}</div> : null}
      </div>
    </div>
  );
}
