import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import type { ExamProfile } from "../../campus/types";
import { daysSince, formatTimestamp } from "../../campus/utils";
import { CampusDialog } from "./CampusDialog";

type ArchiveFilter = "all" | "recent_7d" | "recent_30d" | "older";
type ArchiveSort = "archived_desc" | "created_desc";

const NO_TIME = "--";

const CONTROL =
  "rounded-lg border border-line bg-transparent px-2 py-1 text-[12.5px] text-ink outline-none";

const FILTERS: readonly ArchiveFilter[] = ["all", "recent_7d", "recent_30d", "older"];
const SORTS: readonly ArchiveSort[] = ["archived_desc", "created_desc"];

function inFilter(archivedAt: string | null, filter: ArchiveFilter): boolean {
  if (filter === "all") return true;
  const days = daysSince(archivedAt);
  if (filter === "older") return days === null || days > 30;
  if (filter === "recent_30d") return days !== null && days <= 30;
  return days !== null && days <= 7;
}

function timeValue(value: string | null): number {
  if (!value) return 0;
  const at = new Date(value).getTime();
  return Number.isNaN(at) ? 0 : at;
}

interface Props {
  profiles: ExamProfile[];
  onRestore: (id: string) => void;
  onRename: (id: string) => void;
  onClose: () => void;
}

export function ArchivedProfilesDialog({ profiles, onRestore, onRename, onClose }: Props) {
  const { t } = useTranslation();
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<ArchiveFilter>("all");
  const [sort, setSort] = useState<ArchiveSort>("archived_desc");
  const [detailId, setDetailId] = useState<string | null>(null);

  const archived = useMemo(() => profiles.filter((p) => p.status === "archived"), [profiles]);
  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const kept = archived.filter(
      (p) =>
        (!needle || p.title.toLowerCase().includes(needle)) && inFilter(p.archived_at, filter),
    );
    const key: ArchiveSort = sort;
    return [...kept].sort((a, b) =>
      key === "created_desc"
        ? timeValue(b.created_at) - timeValue(a.created_at)
        : timeValue(b.archived_at) - timeValue(a.archived_at),
    );
  }, [archived, query, filter, sort]);

  const detail = detailId ? archived.find((p) => p.id === detailId) ?? null : null;

  const toolbar = (
    <div className="grid gap-2" data-testid="campus-archived-toolbar">
      <input
        className={CONTROL}
        value={query}
        placeholder={t("campus.archived.search_placeholder")}
        onChange={(e) => setQuery(e.target.value)}
        data-testid="campus-archived-search"
        aria-label={t("campus.archived.search_placeholder")}
      />
      <div className="flex items-center gap-2">
        <select
          className={CONTROL}
          value={filter}
          onChange={(e) => setFilter(e.target.value as ArchiveFilter)}
          data-testid="campus-archived-filter"
          aria-label={t("campus.archived.filter_aria")}
        >
          {FILTERS.map((option) => (
            <option key={option} value={option}>
              {t(`campus.archived.filter_${option}`)}
            </option>
          ))}
        </select>
        <select
          className={CONTROL}
          value={sort}
          onChange={(e) => setSort(e.target.value as ArchiveSort)}
          data-testid="campus-archived-sort"
          aria-label={t("campus.archived.sort_aria")}
        >
          {SORTS.map((option) => (
            <option key={option} value={option}>
              {t(`campus.archived.sort_${option}`)}
            </option>
          ))}
        </select>
      </div>
    </div>
  );

  return (
    <CampusDialog testId="campus-archived-dialog" title={t("campus.archived.title")} onClose={onClose} width="w-[520px]">
      {archived.length === 0 ? (
        <p className="py-3 text-[13px] text-muted" data-testid="campus-archived-empty">
          {t("campus.archived.empty")}
        </p>
      ) : (
        <>
          {toolbar}
          {detail ? (
            <ProfileDetail
              profile={detail}
              onBack={() => setDetailId(null)}
              onRename={() => onRename(detail.id)}
              onRestore={() => onRestore(detail.id)}
            />
          ) : visible.length === 0 ? (
            <p className="py-3 text-[13px] text-muted" data-testid="campus-archived-nomatch">
              {t("campus.archived.nomatch")}
            </p>
          ) : (
            <div className="mt-1" data-testid="campus-archived-list">
              {visible.map((p) => (
                <div
                  key={p.id}
                  className="flex items-center gap-2 border-t border-line py-2"
                  data-testid={`campus-archived-row-${p.id}`}
                >
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-[13px] text-ink" data-testid={`campus-archived-title-${p.id}`}>
                      {p.title}
                    </div>
                    <div className="mt-0.5 flex flex-wrap gap-x-2 text-[11.5px] text-faint">
                      <span>{t("campus.archived.created")}</span>
                      <span data-testid={`campus-archived-created-${p.id}`}>
                        {formatTimestamp(p.created_at) || NO_TIME}
                      </span>
                      <span>{t("campus.archived.archived")}</span>
                      <span data-testid={`campus-archived-at-${p.id}`}>
                        {formatTimestamp(p.archived_at) || NO_TIME}
                      </span>
                    </div>
                  </div>
                  <button
                    type="button"
                    className="px-2 py-1 text-[12.5px] text-muted hover:text-ink"
                    onClick={() => setDetailId(p.id)}
                    data-testid={`campus-archived-detail-${p.id}`}
                  >
                    {t("campus.archived.detail")}
                  </button>
                  <button
                    type="button"
                    className="px-2 py-1 text-[12.5px] text-muted hover:text-ink"
                    onClick={() => onRename(p.id)}
                    data-testid={`campus-archived-rename-${p.id}`}
                  >
                    {t("campus.profile.rename")}
                  </button>
                  <button
                    type="button"
                    className="px-2.5 py-1 rounded-lg text-[12.5px] bg-accent text-white"
                    onClick={() => onRestore(p.id)}
                    data-testid={`campus-archived-restore-${p.id}`}
                  >
                    {t("campus.archived.restore")}
                  </button>
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </CampusDialog>
  );
}

function ProfileDetail({
  profile,
  onBack,
  onRename,
  onRestore,
}: {
  profile: ExamProfile;
  onBack: () => void;
  onRename: () => void;
  onRestore: () => void;
}) {
  const { t } = useTranslation();
  const rows: readonly [string, string][] = [
    [t("campus.profile.title_label"), profile.title],
    [t("campus.profile.exam_date_label"), profile.exam_date || NO_TIME],
    [t("campus.profile.target_score_label"), profile.target_score == null ? NO_TIME : String(profile.target_score)],
    [t("campus.profile.daily_minutes_label"), String(profile.daily_minutes)],
    [t("campus.archived.created"), formatTimestamp(profile.created_at) || NO_TIME],
    [t("campus.archived.archived"), formatTimestamp(profile.archived_at) || NO_TIME],
  ];

  return (
    <div className="mt-3" data-testid="campus-archived-detail">
      <dl className="grid gap-1.5">
        {rows.map(([label, value]) => (
          <div key={label} className="flex items-baseline gap-2 text-[12.5px]">
            <dt className="w-[92px] shrink-0 text-faint">{label}</dt>
            <dd className="min-w-0 flex-1 break-words text-ink">{value}</dd>
          </div>
        ))}
      </dl>
      <p className="mt-2.5 text-[11.5px] leading-[18px] text-faint">
        {t("campus.archived.restore_hint")}
      </p>
      <div className="mt-2.5 flex items-center gap-2">
        <button
          type="button"
          className="px-2.5 py-1.5 rounded-lg text-[13px] text-muted border border-line hover:text-ink"
          onClick={onBack}
          data-testid="campus-archived-detail-back"
        >
          {t("campus.archived.back")}
        </button>
        <button
          type="button"
          className="px-2.5 py-1.5 rounded-lg text-[13px] text-muted border border-line hover:text-ink"
          onClick={onRename}
          data-testid="campus-archived-detail-rename"
        >
          {t("campus.profile.rename")}
        </button>
        <button
          type="button"
          className="px-3 py-1.5 rounded-lg bg-accent text-white text-[13px]"
          onClick={onRestore}
          data-testid="campus-archived-detail-restore"
        >
          {t("campus.archived.restore")}
        </button>
      </div>
    </div>
  );
}
