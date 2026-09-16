import { useTranslation } from "react-i18next";
import { usePlanProgress, usePlanTasks } from "../../../campus/hooks";
import { campusErrorInfo, campusErrorKey } from "../../../campus/utils";
import { PlanBoard } from "./PlanBoard";
import { PlanEditor } from "./PlanEditor";

export function PlanPanel({ profileId }: { profileId: string }) {
  const { t } = useTranslation();
  const tasks = usePlanTasks(profileId);
  const progressState = usePlanProgress(profileId);

  const reloadAll = () => {
    tasks.reload();
    progressState.reload();
  };

  const error = tasks.error ?? progressState.error;

  return (
    <div className="flex flex-col gap-3" data-testid="campus-kaoyan-plan-panel">
      <PlanEditor profileId={profileId} tasks={tasks.items} onMutated={reloadAll} />
      {error ? (
        <div
          className="flex items-center gap-2 rounded-xl2 border border-line bg-panel px-3 py-2 text-[12px] text-warnInk"
          data-testid="campus-kaoyan-plan-error"
        >
          <span>
            {t(campusErrorKey(campusErrorInfo(error).code), {
              defaultValue: campusErrorInfo(error).message || t("campus.common.error"),
            })}
          </span>
          <button
            type="button"
            className="rounded-full border border-line px-2 py-[1px] text-[11px] text-ink hover:bg-chromeHover"
            onClick={reloadAll}
            data-testid="campus-kaoyan-plan-retry"
          >
            {t("campus.common.retry")}
          </button>
        </div>
      ) : null}
      {tasks.loading ? (
        <div className="rounded-xl2 border border-dashed border-line p-4 text-center text-[13px] text-muted">
          {t("campus.common.loading")}
        </div>
      ) : (
        <PlanBoard tasks={tasks.items} progress={progressState.progress} />
      )}
    </div>
  );
}
