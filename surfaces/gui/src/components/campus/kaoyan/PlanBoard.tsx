import { useTranslation } from "react-i18next";
import type { PlanTask, ProgressReport, TaskStatus } from "../../../campus/types";

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
    <div className="flex w-16 flex-col items-center gap-1" data-testid="campus-kaoyan-ring" data-track={track}>
      <svg width="64" height="64" viewBox="0 0 64 64" className="text-accent">
        <circle cx="32" cy="32" r={RING_RADIUS} fill="none" strokeWidth="6" className="stroke-line" />
        <circle
          cx="32"
          cy="32"
          r={RING_RADIUS}
          fill="none"
          strokeWidth="6"
          strokeLinecap="round"
          strokeDasharray={RING_CIRCUMFERENCE}
          strokeDashoffset={offset}
          transform="rotate(-90 32 32)"
          className="stroke-current"
        />
      </svg>
      <span className="text-[12px] text-ink">
        {t(TRACK_LABEL_KEYS[track] ?? "", { defaultValue: track })}
      </span>
      <span className="text-[11px] text-muted">{done}/{total}</span>
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

  return (
    <div className="flex flex-col gap-3" data-testid="campus-kaoyan-board">
      {tracks.length > 0 ? (
        <div className="flex flex-wrap items-start gap-3 rounded-xl2 border border-line bg-panel p-3">
          {tracks.map(([track, stat]) => (
            <TrackRing key={track} track={track} done={stat.done} total={stat.total} rate={stat.rate} />
          ))}
          <div className="ml-auto flex flex-col items-end gap-1 text-[12px] text-muted">
            {progress ? (
              <span data-testid="campus-kaoyan-streak">
                {t("campus.kaoyan.progress.streak", { count: progress.streak_days })}
              </span>
            ) : null}
            {progress && progress.heatmap.length > 0 ? (
              <div className="flex items-center gap-[2px]" data-testid="campus-kaoyan-heatmap">
                {progress.heatmap.map((cell) => (
                  <span
                    key={cell.date}
                    title={cell.date}
                    data-count={cell.count}
                    data-testid="campus-kaoyan-heatmap-cell"
                    className={`h-3 w-3 rounded-sm ${cell.count >= 4 ? "bg-accent" : cell.count >= 2 ? "bg-accentSoft" : "bg-line"}`}
                  />
                ))}
              </div>
            ) : null}
          </div>
        </div>
      ) : null}

      {weeks.length === 0 ? (
        <div className="rounded-xl2 border border-dashed border-line p-4 text-center text-[13px] text-muted">
          {t("campus.kaoyan.board.no_plan")}
        </div>
      ) : (
        weeks.map((week) => (
          <div
            key={week.monday}
            className="rounded-xl2 border border-line bg-panel"
            data-testid="campus-kaoyan-week"
            data-week={week.monday}
          >
            <div className="flex items-center justify-between border-b border-line px-3 py-2 text-[12px] text-muted">
              <span>{t("campus.kaoyan.board.week_of", { date: week.monday })}</span>
              <span>
                {t("campus.kaoyan.board.group_summary", {
                  total: week.tasks.length,
                  done: week.tasks.filter((item) => item.status === "done").length,
                })}
              </span>
            </div>
            <ul>
              {week.tasks.map((item) => (
                <li
                  key={item.id}
                  data-testid={`campus-kaoyan-task-${item.id}`}
                  className="flex items-center gap-2 px-3 py-2 text-[13px] text-ink odd:bg-canvas"
                >
                  <span className="font-mono text-[12px] text-faint">{item.scheduled_date}</span>
                  <span className="flex-1 truncate">{item.title}</span>
                  <span
                    className={`rounded-full px-2 py-[1px] text-[11px] ${
                      item.status === "done"
                        ? "bg-okSoft text-ok"
                        : item.status === "doing" || item.status === "review"
                          ? "bg-tealSoft text-tealInk"
                          : "bg-line text-muted"
                    }`}
                  >
                    {t(STATUS_LABEL_KEYS[item.status])}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        ))
      )}
    </div>
  );
}
