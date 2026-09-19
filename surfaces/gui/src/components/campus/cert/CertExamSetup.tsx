import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useCertDeadlines } from "../../../campus/hooks";
import { DEADLINE_NODE_TYPES, type DeadlineNodeType } from "../../../campus/types";
import { campusErrorInfo, campusErrorKey, deadlineTier } from "../../../campus/utils";
import { Icon } from "../../Icon";

// 考试节点是一条与学习无关、但会决定节奏的外部时间线，所以它走事务侧的临期语义
// （warn / danger），与知识点的掌握度绿黄红不互相借用。

export function CertExamSetup({
  profileId,
  onDeadlinesChanged,
}: {
  profileId: string;
  onDeadlinesChanged?: () => void;
}) {
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
    if (await createNode({ profileId, nodeType, date })) onDeadlinesChanged?.();
  };

  const remind = async (deadlineId: string) => {
    if (remindBusy) return;
    setRemindBusy(deadlineId);
    if (await createReminders(deadlineId)) onDeadlinesChanged?.();
    setRemindBusy(null);
  };

  const info = error ? campusErrorInfo(error) : null;
  const message = formError
    ? t(formError)
    : info
      ? t(campusErrorKey(info.code), { defaultValue: info.message || t("campus.common.error") })
      : null;
  const filled = items.length;

  return (
    <section className="mod" data-testid="campus-cert-setup-panel">
      <div className="mod-head">
        <span className="ib ib--brand">
          <Icon name="flag" size={16} />
        </span>
        <div className="mod-head-text">
          <span className="mod-title">{t("campus.cert.setup.title")}</span>
          <span className="mod-desc">{t("campus.cert.setup.hint")}</span>
        </div>
        <div className="mod-acts">
          <span className="sec-n" data-testid="campus-cert-setup-count">
            {filled} / {DEADLINE_NODE_TYPES.length}
          </span>
        </div>
      </div>

      <div className="node-form">
        <div className="field">
          <span className="field-label">{t("campus.cert.setup.node_type")}</span>
          <div className="sel">
            <select
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
            <Icon name="chevronDown" size={14} className="sel-chev" />
          </div>
        </div>
        <div className={formError ? "field node-date is-bad" : "field node-date"}>
          <span className="field-label">{t("campus.cert.setup.date_label")}</span>
          <input
            className="input input--num"
            type="date"
            value={date}
            onChange={(e) => {
              setDate(e.target.value);
              setFormError(null);
            }}
            data-testid="campus-cert-setup-date"
          />
          {formError ? (
            <span className="field-err" data-testid="campus-cert-setup-error">
              {message}
            </span>
          ) : null}
        </div>
        <button
          type="button"
          className="btn btn--primary"
          disabled={loading}
          onClick={() => void submit()}
          data-testid="campus-cert-setup-create"
        >
          {t("campus.cert.setup.create")}
        </button>
      </div>

      {info ? (
        <div className="alert" data-testid="campus-cert-setup-error">
          <Icon name="warning" size={14} />
          <div className="alert-text">
            <span className="alert-title">{message}</span>
          </div>
          {retryable ? (
            <button
              type="button"
              className="btn btn--ghost btn--sm"
              onClick={() => reload()}
              data-testid="campus-cert-setup-retry"
            >
              {t("campus.common.retry")}
            </button>
          ) : null}
        </div>
      ) : null}

      {loading ? (
        <div className="stack-gap" data-testid="campus-cert-setup-loading">
          <div className="sk" />
          <div className="sk" style={{ width: "70%" }} />
        </div>
      ) : null}

      {!loading && items.length === 0 && !info ? (
        <div className="empty" data-testid="campus-cert-setup-empty">
          <span className="ib ib--brand">
            <Icon name="flag" size={17} />
          </span>
          <span className="empty-title">{t("campus.cert.setup.empty")}</span>
        </div>
      ) : null}

      {items.length > 0 ? (
        <div className="rows fill thin">
          {items.map((node) => (
            <div
              key={node.id}
              className="lrow nrow"
              data-testid="campus-cert-setup-node"
              data-id={node.id}
              data-type={node.node_type}
              data-days={node.days_left}
              data-tier={deadlineTier(node.days_left)}
            >
              <div className="lrow-text">
                <span className="lrow-title">
                  {t(`campus.cert.deadline.node.${node.node_type}`)}
                </span>
                <span className="lrow-meta">{node.date}</span>
              </div>
              <span className="nrow-left">
                {node.days_left < 0
                  ? t("campus.station.dl_overdue")
                  : node.days_left === 0
                    ? t("campus.station.dl_today")
                    : t("campus.station.dl_days", { count: node.days_left })}
              </span>
              <div className="remind">
                {node.automation_ids.length > 0 ? (
                  <span className="tag tag--ok" data-testid="campus-cert-setup-reminders">
                    <Icon name="check" size={11} />
                    {t("campus.cert.setup.reminders_done")}
                  </span>
                ) : (
                  <button
                    type="button"
                    className="btn btn--ghost btn--sm"
                    disabled={remindBusy !== null}
                    onClick={() => void remind(node.id)}
                    data-testid="campus-cert-setup-remind"
                  >
                    <Icon name="bell" size={12} />
                    {t("campus.cert.deadline.create_reminders")}
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      ) : null}
    </section>
  );
}
