import { useTranslation } from "react-i18next";
import type { CapabilitiesReport } from "../../campus/types";
import { Icon } from "../Icon";

// PRD §7.6: an unconfigured or too-weak model is stated out loud, never swallowed.
// DataSource A8 — only the tasks the current model cannot handle are listed.
// 整行提示条钉在页头下方：不可用的模块不静默消失，也不因为切到某个页签才看得见。

export function EmptyModelGuide({ capabilities }: { capabilities: CapabilitiesReport | null }) {
  const { t } = useTranslation();
  if (!capabilities) return null;

  const unsupported = capabilities.tasks.filter((row) => !row.supported);
  const noModel = !capabilities.current_model;
  if (!noModel && unsupported.length === 0) return null;

  return (
    <div
      className="alert"
      data-testid="campus-empty-model-guide"
      data-reason={noModel ? "no_model" : "unsupported"}
    >
      <Icon name="warning" size={15} />
      <div className="alert-text">
        <span className="alert-title">
          {noModel ? t("campus.model.empty_title") : t("campus.model.partial_title")}
        </span>
        <span className="alert-desc">
          {noModel ? t("campus.model.empty_hint") : t("campus.model.partial_hint")}
        </span>
        {unsupported.map((row) => (
          <span className="alert-desc" key={row.task} data-testid="campus-empty-model-task" data-task={row.task}>
            {t("campus.model.unavailable", { task: t(`campus.model.task.${row.task}`) })}
            {row.reason ? ` · ${row.reason}` : ""}
          </span>
        ))}
      </div>
    </div>
  );
}
