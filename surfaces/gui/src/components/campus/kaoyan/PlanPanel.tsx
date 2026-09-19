import { useTranslation } from "react-i18next";
import { usePlanProgress, usePlanTasks } from "../../../campus/hooks";
import { campusErrorInfo, campusErrorKey } from "../../../campus/utils";
import { Icon } from "../../Icon";
import { PlanBoard } from "./PlanBoard";
import { PlanEditor } from "./PlanEditor";

// One module card for the whole plan: 生成 / 重排在上，四轨完成率与按周任务在下。
// 计划板是只读的（真实实现就没有拖拽与状态切换），所以不给它任何「看起来可拖」的把手。

export function PlanPanel({ profileId }: { profileId: string }) {
  const { t } = useTranslation();
  const tasks = usePlanTasks(profileId);
  const progressState = usePlanProgress(profileId);

  const reloadAll = () => {
    tasks.reload();
    progressState.reload();
  };

  const error = tasks.error ?? progressState.error;
  const done = tasks.items.filter((task) => task.status === "done").length;

  return (
    <section className="mod" data-testid="campus-kaoyan-plan-panel">
      <div className="mod-head">
        <span className="ib ib--accent">
          <Icon name="calendar" size={16} />
        </span>
        <div className="mod-head-text">
          <span className="mod-title">{t("campus.kaoyan.plan.title")}</span>
          <span className="mod-desc">{t("campus.kaoyan.plan.hint")}</span>
        </div>
        <div className="mod-acts">
          {tasks.items.length > 0 ? (
            <span className="sec-n" data-testid="campus-kaoyan-plan-summary">
              {t("campus.kaoyan.board.group_summary", { total: tasks.items.length, done })}
            </span>
          ) : null}
        </div>
      </div>

      <PlanEditor profileId={profileId} tasks={tasks.items} onMutated={reloadAll} />

      {error ? (
        <div className="alert" data-testid="campus-kaoyan-plan-error">
          <Icon name="warning" size={14} />
          <div className="alert-text">
            <span className="alert-title">
              {t(campusErrorKey(campusErrorInfo(error).code), {
                defaultValue: campusErrorInfo(error).message || t("campus.common.error"),
              })}
            </span>
          </div>
          <button
            type="button"
            className="btn btn--ghost btn--sm"
            onClick={reloadAll}
            data-testid="campus-kaoyan-plan-retry"
          >
            {t("campus.common.retry")}
          </button>
        </div>
      ) : null}

      {tasks.loading ? (
        <div className="stack-gap">
          <div className="sk" style={{ width: 200 }} />
          <div className="sk" />
          <div className="sk" style={{ width: "80%" }} />
          <span className="body-text">{t("campus.common.loading")}</span>
        </div>
      ) : (
        <PlanBoard tasks={tasks.items} progress={progressState.progress} />
      )}
    </section>
  );
}
