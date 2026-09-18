import { useTranslation } from "react-i18next";
import type { PlanTask, ProgressReport, TaskStatus } from "../../../campus/types";
import { Icon } from "../../Icon";

const RING_RADIUS = 26;
const RING_CIRCUMFERENCE = 2 * Math.PI * RING_RADIUS;

export const TRACK_LABEL_KEYS: Record<string, string> = {
  overall: "campus.kaoyan.board.overall",
  politics: "campus.common.subject.politics",
  english: "campus.common.subject.english",
  math: "campus.common.subject.math",
  major: "campus.common.subject.major",
};

const STATUS_LABEL_KEYS: Record<TaskStatus, string> = {
  todo: "campus.kaoyan.board.status.todo",
  doing: "campus.kaoyan.board.status.doing",
  review: "campus.kaoyan.board.status.review",
  done: "campus.kaoyan.board.status.done",
  skipped: "campus.kaoyan.board.status.skipped",
};

// 状态胶囊：颜色 + 文字双通道，进行中 / 复核中走 teal 与「已完成」的绿区分开
const TAG_CLASS: Record<TaskStatus, string> = {
  todo: "tag tag--muted",
  doing: "tag tag--teal",
  review: "tag tag--teal",
  done: "tag tag--ok",
  skipped: "tag tag--muted",
};

function mondayOf(dateStr: string): string {
  const date = new Date(`${dateStr}T00:00:00Z`);
  const shift = (date.getUTCDay() + 6) % 7;
  date.setUTCDate(date.getUTCDate() - shift);
  return date.toISOString().slice(0, 10);
}

function TrackRing({ track, done, total, rate }: { track: string; done: number; total: number; rate: number }) {
  const { t } = useTranslation();
  const offset = RING_CIRCUMFERENCE * (1 - Math.min(Math.max(rate, 0), 1));
  return (
    <div className="dial-c" data-testid="campus-kaoyan-ring" data-track={track}>
      <svg className="dial" width="56" height="56" viewBox="0 0 64 64" aria-hidden>
        <circle className="dial-track" cx="32" cy="32" r={RING_RADIUS} strokeWidth="6" />
        <circle
          className="dial-val"
          cx="32"
          cy="32"
          r={RING_RADIUS}
          strokeWidth="6"
          strokeDasharray={RING_CIRCUMFERENCE}
          strokeDashoffset={offset}
          transform="rotate(-90 32 32)"
        />
      </svg>
      <span className="dial-n">{Math.round(Math.min(Math.max(rate, 0), 1) * 100)}%</span>
      <span className="dial-l">
        {t(TRACK_LABEL_KEYS[track] ?? "", { defaultValue: track })}
      </span>
      <span className="dial-l">
        {done}/{total}
      </span>
    </div>
  );
}

export function PlanBoard({ tasks, progress }: { tasks: PlanTask[]; progress: ProgressReport | null }) {
  const { t } = useTranslation();

  const weeks: { monday: string; tasks: PlanTask[] }[] = [];
  for (const item of [...tasks].sort((a, b) =>
    a.scheduled_date === b.scheduled_date ? a.id.localeCompare(b.id) : a.scheduled_date.localeCompare(b.scheduled_date),
  )) {
    const monday = mondayOf(item.scheduled_date);
    const bucket = weeks[weeks.length - 1];
    if (bucket && bucket.monday === monday) {
      bucket.tasks.push(item);
    } else {
      weeks.push({ monday, tasks: [item] });
    }
  }

  const tracks = progress ? Object.entries(progress.by_track) : [];
  const total = tracks.reduce((sum, [, stat]) => sum + stat.total, 0);
  const done = tracks.reduce((sum, [, stat]) => sum + stat.done, 0);

  return (
    <div className="stack" data-testid="campus-kaoyan-board">
      {tracks.length > 0 ? (
        <div className="rings">
          {tracks.map(([track, stat]) => (
            <TrackRing key={track} track={track} done={stat.done} total={stat.total} rate={stat.rate} />
          ))}
          {/* 连续打卡与打卡热图在右栏常驻，这里不再重复一遍，只留计划总体的完成率 */}
          <div className="rings-end">
            <span className="rings-note" data-testid="campus-kaoyan-overall">
              {t("campus.kaoyan.board.overall")}{" "}
              {total ? Math.round((done / total) * 100) : 0}% · {done}/{total}
            </span>
          </div>
        </div>
      ) : null}

      {weeks.length === 0 ? (
        <div className="empty" data-testid="campus-kaoyan-no-plan">
          <span className="ib ib--brand">
            <Icon name="calendar" size={17} />
          </span>
          <span className="empty-title">{t("campus.kaoyan.board.no_plan")}</span>
        </div>
      ) : (
        <div className="fill thin">
          {weeks.map((week) => (
            <div
              key={week.monday}
              className="wk"
              data-testid="campus-kaoyan-week"
              data-week={week.monday}
            >
              <div className="wk-h">
                <span className="wk-d">{week.monday.slice(5)}</span>
                <span className="sec-title">{t("campus.kaoyan.board.week_of", { date: week.monday })}</span>
                <span className="wk-n">
                  {t("campus.kaoyan.board.group_summary", {
                    total: week.tasks.length,
                    done: week.tasks.filter((item) => item.status === "done").length,
                  })}
                </span>
              </div>
              <div className="rows">
                {week.tasks.map((item) => (
                  <div
                    key={item.id}
                    className="lrow"
                    data-testid={`campus-kaoyan-task-${item.id}`}
                    data-status={item.status}
                    data-date={item.scheduled_date}
                  >
                    <span className="trow-d">{item.scheduled_date.slice(5)}</span>
                    <div className="lrow-text">
                      <span className="lrow-title">{item.title}</span>
                    </div>
                    <span className={TAG_CLASS[item.status]}>{t(STATUS_LABEL_KEYS[item.status])}</span>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
