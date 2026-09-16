import { useState } from "react";
import { useTranslation } from "react-i18next";
import { generatePlan, reschedulePlan } from "../../../campus/api";
import type { PlanTask } from "../../../campus/types";
import { campusErrorInfo, campusErrorKey } from "../../../campus/utils";

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
    <div className="rounded-xl2 border border-line bg-panel px-4 py-3.5" data-testid="campus-plan-editor">
      <div className="flex flex-wrap items-center gap-2">
        <label className="text-[12px] text-muted" htmlFor="campus-plan-date">
          {t("campus.kaoyan.plan.new_exam_date")}
        </label>
        <input
          id="campus-plan-date"
          type="date"
          className="rounded-lg border border-line bg-transparent px-2.5 py-1.5 text-[13px] text-ink outline-none"
          value={examDate}
          onChange={(e) => setExamDate(e.target.value)}
          data-testid="campus-plan-date"
        />
        <button
          type="button"
          className="px-3 py-1.5 rounded-lg bg-accent text-white text-[13px] disabled:opacity-40"
          onClick={() => void generate()}
          disabled={busy !== null}
          data-testid="campus-plan-generate"
        >
          {busy === "generate" ? t("campus.kaoyan.plan.generating") : t("campus.kaoyan.plan.generate")}
        </button>
        <button
          type="button"
          className="px-3 py-1.5 rounded-lg text-[13px] text-ink border border-line disabled:opacity-40"
          onClick={() => void reschedule()}
          disabled={busy !== null || !planId}
          data-testid="campus-plan-reschedule"
        >
          {busy === "reschedule"
            ? t("campus.kaoyan.plan.rescheduling")
            : t("campus.kaoyan.plan.reorder")}
        </button>
      </div>

      {notice ? (
        <div className="pt-2 text-[12px] text-ok" data-testid="campus-plan-notice">
          {notice}
        </div>
      ) : null}
      {error ? (
        <div className="pt-2 text-[12px] text-warnInk" data-testid="campus-plan-error">
          {t(campusErrorKey(campusErrorInfo(error).code), {
            defaultValue: campusErrorInfo(error).message || t("campus.common.error"),
          })}
        </div>
      ) : null}
    </div>
  );
}
