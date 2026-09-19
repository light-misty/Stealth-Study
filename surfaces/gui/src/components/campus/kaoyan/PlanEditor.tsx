import { useState } from "react";
import { useTranslation } from "react-i18next";
import { generatePlan, reschedulePlan } from "../../../campus/api";
import type { PlanTask } from "../../../campus/types";
import { campusErrorInfo, campusErrorKey } from "../../../campus/utils";
import { Icon } from "../../Icon";

// 生成与重排是这一屏唯一的主行动，所以橙只给「生成计划」；重排在没有计划时禁用，
// 而不是藏起来 —— 用户看得到这一步存在，只是现在还点不动。

export function PlanEditor({
  profileId,
  tasks,
  onMutated,
}: {
  profileId: string;
  tasks: PlanTask[];
  onMutated?: () => void;
}) {
  const { t } = useTranslation();
  const [examDate, setExamDate] = useState("");
  const [busy, setBusy] = useState<"generate" | "reschedule" | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setErr] = useState<unknown>(null);

  const planId = tasks[0]?.plan_id ?? null;

  const generate = async () => {
    if (busy) return;
    setBusy("generate");
    setNotice(null);
    setErr(null);
    try {
      const result = await generatePlan(profileId);
      setNotice(
        t("campus.kaoyan.plan.generated", { total: result.task_count, date: result.first_date }),
      );
      onMutated?.();
    } catch (err) {
      setErr(err);
    } finally {
      setBusy(null);
    }
  };

  const reschedule = async () => {
    if (busy || !planId) return;
    setBusy("reschedule");
    setNotice(null);
    setErr(null);
    try {
      const result = await reschedulePlan(profileId, planId, examDate || undefined);
      setNotice(
        t("campus.kaoyan.plan.rescheduled", {
          moved: result.rescheduled,
          kept: result.preserved_done,
        }),
      );
      onMutated?.();
    } catch (err) {
      setErr(err);
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="plan-edit" data-testid="campus-plan-editor">
      <div className="field">
        <label className="field-label" htmlFor="campus-plan-date">
          {t("campus.kaoyan.plan.new_exam_date")}
        </label>
        <input
          id="campus-plan-date"
          className="input input--num"
          type="date"
          value={examDate}
          onChange={(e) => setExamDate(e.target.value)}
          data-testid="campus-plan-date"
        />
      </div>
      <button
        type="button"
        className="btn btn--primary"
        onClick={() => void generate()}
        disabled={busy !== null}
        data-testid="campus-plan-generate"
      >
        <Icon name="sparkle" size={13} />
        {busy === "generate" ? t("campus.kaoyan.plan.generating") : t("campus.kaoyan.plan.generate")}
      </button>
      <button
        type="button"
        className="btn btn--ghost"
        onClick={() => void reschedule()}
        disabled={busy !== null || !planId}
        data-testid="campus-plan-reschedule"
      >
        <Icon name="refresh" size={13} />
        {busy === "reschedule"
          ? t("campus.kaoyan.plan.rescheduling")
          : t("campus.kaoyan.plan.reorder")}
      </button>

      {notice || error ? (
        <div className="stack">
          {notice ? (
            <span className="ai-note" data-testid="campus-plan-notice">
              <Icon name="check" size={12} />
              {notice}
            </span>
          ) : null}
          {error ? (
            <span className="field-err" data-testid="campus-plan-error">
              {t(campusErrorKey(campusErrorInfo(error).code), {
                defaultValue: campusErrorInfo(error).message || t("campus.common.error"),
              })}
            </span>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
