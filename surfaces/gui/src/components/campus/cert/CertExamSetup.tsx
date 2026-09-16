import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useCertDeadlines } from "../../../campus/hooks";
import { DEADLINE_NODE_TYPES, type DeadlineNodeType } from "../../../campus/types";
import { campusErrorInfo, campusErrorKey, deadlineTier } from "../../../campus/utils";

export function CertExamSetup({ profileId }: { profileId: string }) {
  const { t } = useTranslation();
  const { items, loading, error, retryable, reload, createNode, createReminders } =
    useCertDeadlines(profileId);
  const [nodeType, setNodeType] = useState<DeadlineNodeType>("registration_open");
  const [date, setDate] = useState("");
  const [formError, setFormError] = useState<string | null>(null);
  const [remindBusy, setRemindBusy] = useState<string | null>(null);

  const submit = async () => {
    if (loading) return;
    if (!date) {
      setFormError("campus.cert.setup.date_required");
      return;
    }
    setFormError(null);
    await createNode({ profileId, nodeType, date });
  };

  const remind = async (deadlineId: string) => {
    if (remindBusy) return;
    setRemindBusy(deadlineId);
    await createReminders(deadlineId);
    setRemindBusy(null);
  };

  const info = error ? campusErrorInfo(error) : null;
  const message = formError
    ? t(formError)
    : info
      ? t(campusErrorKey(info.code), { defaultValue: info.message || t("campus.common.error") })
      : null;

  return (
    <div className="rounded-xl2 border border-line bg-panel" data-testid="campus-cert-setup-panel">
      <div className="px-4 pt-3.5 text-[13px] font-semibold text-ink">
        {t("campus.cert.setup.title")}
      </div>

      <div className="flex flex-wrap items-center gap-2 px-4 pt-2.5">
        <select
          className="rounded-lg border border-line bg-panel px-2 py-1 text-[12px] text-ink"
          value={nodeType}
          onChange={(e) => setNodeType(e.target.value as DeadlineNodeType)}
          data-testid="campus-cert-setup-type"
        >
          {DEADLINE_NODE_TYPES.map((option) => (
            <option key={option} value={option}>
              {t(`campus.cert.deadline.node.${option}`)}
            </option>
          ))}
        </select>
        <input
          type="date"
          className="rounded-lg border border-line bg-panel px-2 py-1 text-[12px] text-ink"
          value={date}
          placeholder={t("campus.cert.setup.date_label")}
          onChange={(e) => {
            setDate(e.target.value);
            setFormError(null);
          }}
          data-testid="campus-cert-setup-date"
        />
        <button
          type="button"
          className="rounded-lg border border-accent px-2.5 py-1 text-[12px] text-accent disabled:opacity-50"
          disabled={loading}
          onClick={() => void submit()}
          data-testid="campus-cert-setup-create"
        >
          {t("campus.cert.setup.create")}
        </button>
      </div>

      {loading ? (
        <div className="px-4 py-3 text-[12px] text-faint" data-testid="campus-cert-setup-loading">
          {t("campus.common.loading")}
        </div>
      ) : null}

      {message ? (
        <div
          className="flex items-center gap-2 px-4 py-2 text-[12px] text-warnInk"
          data-testid="campus-cert-setup-error"
        >
          <span className="min-w-0 truncate">{message}</span>
          {retryable ? (
            <button
              type="button"
              className="shrink-0 rounded-lg border border-line px-2 py-0.5 text-[11px] text-muted"
              onClick={() => reload()}
              data-testid="campus-cert-setup-retry"
            >
              {t("campus.common.retry")}
            </button>
          ) : null}
        </div>
      ) : null}

      {!loading && items.length === 0 && !info ? (
        <div className="px-4 py-3 text-[12px] text-faint" data-testid="campus-cert-setup-empty">
          {t("campus.cert.setup.empty")}
        </div>
      ) : null}

      {items.length > 0 ? (
        <ul className="mt-2 grid gap-1.5 px-4 pb-3.5">
          {items.map((node) => (
            <li
              key={node.id}
              className="flex items-center gap-2 rounded-lg border border-line px-2.5 py-2"
              data-testid="campus-cert-setup-node"
              data-id={node.id}
              data-type={node.node_type}
              data-days={node.days_left}
              data-tier={deadlineTier(node.days_left)}
            >
              <span className="min-w-0 flex-1 truncate text-[12px] text-ink">
                {t(`campus.cert.deadline.node.${node.node_type}`)}
              </span>
              <span className="shrink-0 text-[11px] text-muted">{node.date}</span>
              <span className="shrink-0 text-[11px] text-faint">
                {t("campus.common.days_left", { count: node.days_left })}
              </span>
              {node.automation_ids.length > 0 ? (
                <span
                  className="shrink-0 text-[11px] text-ok"
                  data-testid="campus-cert-setup-reminders"
                >
                  {t("campus.cert.setup.reminders_done")}
                </span>
              ) : (
                <button
                  type="button"
                  className="shrink-0 rounded-lg border border-line px-2 py-0.5 text-[11px] text-accent disabled:opacity-50"
                  disabled={remindBusy !== null}
                  onClick={() => void remind(node.id)}
                  data-testid="campus-cert-setup-remind"
                >
                  {t("campus.cert.deadline.create_reminders")}
                </button>
              )}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
