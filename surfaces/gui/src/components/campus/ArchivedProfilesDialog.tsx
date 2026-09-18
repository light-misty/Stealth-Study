import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import type { ExamProfile } from "../../campus/types";
import { daysSince, formatTimestamp } from "../../campus/utils";
import { CampusDialog } from "./CampusDialog";
import { Icon } from "../Icon";

type ArchiveFilter = "all" | "recent_7d" | "recent_30d" | "older";
type ArchiveSort = "archived_desc" | "created_desc";

const NO_TIME = "--";

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
    <div className="stack-gap" data-testid="campus-archived-toolbar">
      <input
        className="input"
        value={query}
        placeholder={t("campus.archived.search_placeholder")}
        onChange={(e) => setQuery(e.target.value)}
        data-testid="campus-archived-search"
        aria-label={t("campus.archived.search_placeholder")}
      />
      <div className="field-rows">
        <div className="field">
          <div className="sel">
            <select
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
            <Icon name="chevronDown" size={14} className="sel-chev" />
          </div>
        </div>
        <div className="field">
          <div className="sel">
            <select
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
            <Icon name="chevronDown" size={14} className="sel-chev" />
          </div>
        </div>
      </div>
    </div>
  );

  return (
    <CampusDialog
      testId="campus-archived-dialog"
      title={t("campus.archived.title")}
      icon="archive"
      wide
      onClose={onClose}
    >
      {archived.length === 0 ? (
        <div className="empty" data-testid="campus-archived-empty">
          <span className="ib ib--brand">
            <Icon name="archive" size={17} />
          </span>
          <span className="empty-title">{t("campus.archived.empty")}</span>
        </div>
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
            <p className="dlg-note" data-testid="campus-archived-nomatch">
              {t("campus.archived.nomatch")}
            </p>
          ) : (
            <div className="arch-list" data-testid="campus-archived-list">
              <div className="rows">
                {visible.map((p) => (
                  <div key={p.id} className="lrow" data-testid={`campus-archived-row-${p.id}`}>
                    <div className="lrow-text">
                      <span className="lrow-title" data-testid={`campus-archived-title-${p.id}`}>
                        {p.title}
                      </span>
                      <span className="lrow-meta">
                        {t("campus.archived.created")}{" "}
                        <span data-testid={`campus-archived-created-${p.id}`}>
                          {formatTimestamp(p.created_at) || NO_TIME}
                        </span>
                        {" · "}
                        {t("campus.archived.archived")}{" "}
                        <span data-testid={`campus-archived-at-${p.id}`}>
                          {formatTimestamp(p.archived_at) || NO_TIME}
                        </span>
                      </span>
                    </div>
                    <div className="lrow-acts">
                      <button
                        type="button"
                        className="btn btn--text btn--sm"
                        onClick={() => setDetailId(p.id)}
                        data-testid={`campus-archived-detail-${p.id}`}
                      >
                        {t("campus.archived.detail")}
                      </button>
                      <button
                        type="button"
                        className="btn btn--text btn--sm"
                        onClick={() => onRename(p.id)}
                        data-testid={`campus-archived-rename-${p.id}`}
                      >
                        {t("campus.profile.rename")}
                      </button>
                      <button
                        type="button"
                        className="btn btn--soft btn--sm"
                        onClick={() => onRestore(p.id)}
                        data-testid={`campus-archived-restore-${p.id}`}
                      >
                        {t("campus.archived.restore")}
                      </button>
                    </div>
                  </div>
                ))}
              </div>
              <div className="alert alert--info">
                <Icon name="warning" size={14} />
                <div className="alert-text">
                  <span className="alert-desc">{t("campus.archived.restore_hint")}</span>
                </div>
              </div>
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
    [
      t("campus.profile.target_score_label"),
      profile.target_score == null ? NO_TIME : String(profile.target_score),
    ],
    [t("campus.profile.daily_minutes_label"), String(profile.daily_minutes)],
    [t("campus.archived.created"), formatTimestamp(profile.created_at) || NO_TIME],
    [t("campus.archived.archived"), formatTimestamp(profile.archived_at) || NO_TIME],
  ];

  return (
    <div className="arch-detail" data-testid="campus-archived-detail">
      <div className="kv">
        {rows.map(([label, value]) => (
          <div className="kv-row" key={label}>
            <span className="kv-k">{label}</span>
            <span className="kv-v">{value}</span>
          </div>
        ))}
      </div>
      <p className="dlg-note">{t("campus.archived.restore_hint")}</p>
      <div className="mod-foot">
        <button
          type="button"
          className="btn btn--ghost btn--sm"
          onClick={onBack}
          data-testid="campus-archived-detail-back"
        >
          {t("campus.archived.back")}
        </button>
        <span className="st-spacer" />
        <button
          type="button"
          className="btn btn--ghost btn--sm"
          onClick={onRename}
          data-testid="campus-archived-detail-rename"
        >
          {t("campus.profile.rename")}
        </button>
        <button
          type="button"
          className="btn btn--primary btn--sm"
          onClick={onRestore}
          data-testid="campus-archived-detail-restore"
        >
          {t("campus.archived.restore")}
        </button>
      </div>
    </div>
  );
}
