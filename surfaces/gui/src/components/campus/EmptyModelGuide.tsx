import { useTranslation } from "react-i18next";
import type { CapabilitiesReport } from "../../campus/types";
import { Icon } from "../Icon";

// PRD §7.6: an unconfigured or too-weak model is stated out loud, never swallowed.
// DataSource A8 — only the tasks the current model cannot handle are listed.

export function EmptyModelGuide({ capabilities }: { capabilities: CapabilitiesReport | null }) {
  const { t } = useTranslation();
  if (!capabilities) return null;

  const unsupported = capabilities.tasks.filter((row) => !row.supported);
  const noModel = !capabilities.current_model;
  if (!noModel && unsupported.length === 0) return null;

  return (
    <div
      className="rounded-xl2 border border-warnInk/40 bg-warnSoft px-4 py-3"
      data-testid="campus-empty-model-guide"
      data-reason={noModel ? "no_model" : "unsupported"}
    >
      <div className="flex items-center gap-1.5 text-[13px] font-semibold text-warnInk">
        <Icon name="warning" size={14} />
        <span>{noModel ? t("campus.model.empty_title") : t("campus.model.partial_title")}</span>
      </div>
      <div className="text-[12px] text-muted mt-1">
        {noModel ? t("campus.model.empty_hint") : t("campus.model.partial_hint")}
      </div>
      <ul className="mt-2 grid gap-1">
        {unsupported.map((row) => (
          <li
            key={row.task}
            className="text-[12px] text-muted"
            data-testid="campus-empty-model-task"
            data-task={row.task}
          >
            {t("campus.model.unavailable", { task: t(`campus.model.task.${row.task}`) })}
            {row.reason ? <span className="text-faint"> · {row.reason}</span> : null}
          </li>
        ))}
      </ul>
    </div>
  );
}
