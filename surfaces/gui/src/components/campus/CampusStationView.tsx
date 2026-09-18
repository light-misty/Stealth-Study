import { useEffect, useRef, useState, type KeyboardEvent, type ReactElement } from "react";
import { useTranslation } from "react-i18next";
import type { ProfileAction, ProfileActionError } from "./CampusProfileContext";
import {
  useCapabilities,
  useDeadlineViews,
  useDueReviews,
  usePlanProgress,
} from "../../campus/hooks";
import type { CampusTrack, ExamProfile } from "../../campus/types";
import {
  campusErrorInfo,
  campusErrorKey,
  profileTitleTaken,
  suggestProfileTitle,
} from "../../campus/utils";
import { CampusProfileProvider, useCampusProfile } from "./CampusProfileContext";
import { ProfileRenameDialog } from "./ProfileRenameDialog";
import { ArchivedProfilesDialog } from "./ArchivedProfilesDialog";
import { CampusDialog } from "./CampusDialog";
import { Icon } from "../Icon";
import { CountdownBanner } from "./CountdownBanner";
import { DeadlineBanner } from "./DeadlineBanner";
import { EmptyModelGuide } from "./EmptyModelGuide";
import { LibraryPanel } from "./LibraryPanel";
import { MistakeBookPanel } from "./MistakeBookPanel";
import { ProfileCreateCard } from "./ProfileCreateCard";
import { ProfileSwitcher } from "./ProfileSwitcher";
import { MajorQAView } from "./kaoyan/MajorQAView";
import { PlanPanel } from "./kaoyan/PlanPanel";
import { TRACK_LABEL_KEYS } from "./kaoyan/PlanBoard";
import { SubjectTutorChat } from "./kaoyan/SubjectTutorChat";
import { WeeklyReportView } from "./kaoyan/WeeklyReportView";
import { ReviewQueuePanel } from "./ReviewQueuePanel";
import { AssessmentFlow } from "./cet/AssessmentFlow";
import { CommonErrorsCard } from "./cet/CommonErrorsCard";
import { EssayGradingPanel } from "./cet/EssayGradingPanel";
import { ListeningDrill } from "./cet/ListeningDrill";
import { MockExamConsole } from "./cet/MockExamConsole";
import { TranslationGradingPanel } from "./cet/TranslationGradingPanel";
import { VocabPanel } from "./cet/VocabPanel";
import { CertExamSetup } from "./cert/CertExamSetup";
import { KnowledgeTreePanel } from "./cert/KnowledgeTreePanel";
import { SubjectiveGradingPanel } from "./cert/SubjectiveGradingPanel";

// The station shell the three tracks share (04 §3.1), built against the design mock in
// ui-mocks/stealth-study-redesign — the mock's css/campus.css header carries the rationale
// (one module per screen; a pinned shell that scrolls only inside the current module). The
// tab strip IS TRACK_PANELS, so everything track-specific still lives in these lookup tables
// and the component never branches on the track (01 §4: a new station panel is a new row
// here, not an `if`).

interface PanelContext {
  profileId: string;
  selectedDocId: string | null;
  onSelectDoc: (docId: string) => void;
  reviewItems: ReturnType<typeof useDueReviews>["items"];
  reviewLoading: boolean;
  onReviewResult: (reviewId: string, correct: boolean) => void;
  onGotoTab: (key: string) => void;
}

interface PanelSpec {
  key: string;
  /** Suffix of the campus.station.tab.* label this panel's tab carries. */
  tab: string;
  render: (ctx: PanelContext) => ReactElement;
}

const SHARED_PANELS: readonly PanelSpec[] = [
  {
    key: "mistake",
    tab: "mistake",
    render: ({ profileId }) => <MistakeBookPanel profileId={profileId} />,
  },
  {
    key: "review",
    tab: "review",
    // The station owns the due queue, so the tab's badge and the panel can never disagree.
    render: ({ profileId, reviewItems, reviewLoading, onReviewResult }) => (
      <ReviewQueuePanel
        profileId={profileId}
        dueItems={reviewItems}
        loading={reviewLoading}
        onResult={onReviewResult}
      />
    ),
  },
];

// 04 §2.1 puts the library and its Q&A on the kaoyan track. The kaoyan Q&A slot is the
// T18 MajorQAView (document picker + clickable page citations) rather than the shared
// QAChatPanel. Tracks get their own entry so T17/T18/T19 can append their business panels
// without touching this file's logic.
const LIBRARY_PANELS: readonly PanelSpec[] = [
  {
    key: "library",
    tab: "library",
    render: ({ profileId, selectedDocId, onSelectDoc }) => (
      <LibraryPanel profileId={profileId} selectedDocId={selectedDocId} onSelectDoc={onSelectDoc} />
    ),
  },
  { key: "qa", tab: "qa", render: ({ profileId, onSelectDoc, onGotoTab }) => (
      <MajorQAView
        profileId={profileId}
        onCite={(docId) => {
          onSelectDoc(docId);
          onGotoTab("library");
        }}
      />
    ) },
];

const CERT_PANELS: readonly PanelSpec[] = [
  {
    key: "cert_tree",
    tab: "cert_tree",
    render: ({ profileId }) => <KnowledgeTreePanel profileId={profileId} />,
  },
  {
    key: "cert_grading",
    tab: "cert_grading",
    render: ({ profileId }) => <SubjectiveGradingPanel profileId={profileId} />,
  },
  {
    key: "cert_setup",
    tab: "cert_setup",
    render: ({ profileId }) => <CertExamSetup profileId={profileId} />,
  },
];

// T18 kaoyan business panels: the combined plan editor + read-only board (KY-01/03,
// ADR-11), the weekly report view (KY-12) and the per-subject grading chat (KY-05/06).
const KAOYAN_PANELS: readonly PanelSpec[] = [
  { key: "plan", tab: "plan", render: ({ profileId }) => <PlanPanel profileId={profileId} /> },
  { key: "weekly", tab: "weekly", render: ({ profileId }) => <WeeklyReportView profileId={profileId} /> },
  { key: "tutor", tab: "tutor", render: ({ profileId }) => <SubjectTutorChat profileId={profileId} /> },
];

// CET-01 … CET-13 in track order: placement, vocabulary, listening, essay/translation
// grading, the mock-exam console and the common-mistakes summary.
const CET_PANELS: readonly PanelSpec[] = [
  {
    key: "assessment",
    tab: "assessment",
    render: ({ profileId, onGotoTab }) => (
      <AssessmentFlow profileId={profileId} onGotoTab={onGotoTab} />
    ),
  },
  { key: "vocab", tab: "vocab", render: ({ profileId }) => <VocabPanel profileId={profileId} /> },
  { key: "listening", tab: "listening", render: ({ profileId }) => <ListeningDrill profileId={profileId} /> },
  { key: "essay", tab: "essay", render: ({ profileId }) => <EssayGradingPanel profileId={profileId} /> },
  {
    key: "translation",
    tab: "translation",
    render: ({ profileId }) => <TranslationGradingPanel profileId={profileId} />,
  },
  { key: "mock", tab: "mock", render: ({ profileId }) => <MockExamConsole profileId={profileId} /> },
  {
    key: "common-errors",
    tab: "common_errors",
    render: ({ profileId, onGotoTab }) => (
      <CommonErrorsCard profileId={profileId} framed onGotoTab={onGotoTab} />
    ),
  },
];

const TRACK_PANELS: Record<CampusTrack, readonly PanelSpec[]> = {
  cet: [...SHARED_PANELS, ...CET_PANELS],
  kaoyan: [...SHARED_PANELS, ...LIBRARY_PANELS, ...KAOYAN_PANELS],
  cert: [...SHARED_PANELS, ...CERT_PANELS],
};

const TRACK_BANNERS: Record<
  CampusTrack,
  (args: { profile: ExamProfile; planRate: number | null }) => ReactElement | null
> = {
  cet: ({ profile, planRate }) => (
    <CountdownBanner
      examDate={profile.exam_date}
      targetScore={profile.target_score}
      currentEstimate={profile.current_estimate}
      planRate={planRate}
    />
  ),
  kaoyan: ({ profile, planRate }) => (
    <CountdownBanner
      examDate={profile.exam_date}
      targetScore={profile.target_score}
      currentEstimate={profile.current_estimate}
      planRate={planRate}
    />
  ),
  cert: ({ profile }) => <CertDeadlineBanner profileId={profile.id} />,
};

function CertDeadlineBanner({ profileId }: { profileId: string }) {
  const { views } = useDeadlineViews(profileId);
  return <DeadlineBanner views={views} />;
}

export function CampusStationView({ track }: { track: CampusTrack }) {
  return (
    <CampusProfileProvider track={track}>
      <StationBody track={track} />
    </CampusProfileProvider>
  );
}

function StationBody({ track }: { track: CampusTrack }) {
  const { t } = useTranslation();
  const {
    profiles,
    activeProfile,
    loading,
    error,
    retryable,
    reload,
    setActive,
    createProfile,
    setStatus,
    renameProfile,
    actionError,
    clearActionError,
    creating: creatingProfile,
  } = useCampusProfile();
  const { capabilities } = useCapabilities();
  // Two different questions need two different flags: `creatingProfile` is "a create request is
  // in flight" (the card must not take a second submit), while `showCreateCard` is only "the
  // switcher's inline card is open". Driving both from one flag left the card's submit disabled
  // the instant it was opened from the switcher — invisible from the empty state, where the card
  // is always on screen and nothing ever sets the flag.
  const [showCreateCard, setShowCreateCard] = useState(false);
  const [showArchived, setShowArchived] = useState(false);
  const [renameId, setRenameId] = useState<string | null>(null);
  const [selectedDocId, setSelectedDocId] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<string | null>(null);
  const archivedCount = profiles.filter((p) => p.status === "archived").length;
  const panels = TRACK_PANELS[track];
  // A track's first panel is the default; a stale tab key falls back rather than rendering a
  // shell with no pane.
  const selected = panels.some((p) => p.key === activeTab) ? (activeTab as string) : panels[0].key;
  // Owned here rather than by the queue panel so the tab badge and the list agree.
  const review = useDueReviews(activeProfile?.id ?? null);

  const renameTarget = renameId ? profiles.find((p) => p.id === renameId) ?? null : null;

  const dialogs = (
    <>
      {showArchived ? (
        <ArchivedProfilesDialog
          profiles={profiles}
          onRestore={(id) => void setStatus(id, "active")}
          onRename={(id) => setRenameId(id)}
          onClose={() => setShowArchived(false)}
        />
      ) : null}
      {renameTarget ? (
        <ProfileRenameDialog
          profile={renameTarget}
          profiles={profiles}
          onSubmit={async (title) => (await renameProfile(renameTarget.id, title)).ok}
          onClose={() => setRenameId(null)}
        />
      ) : null}
      {actionError ? (
        <ProfileActionDialog
          error={actionError}
          profiles={profiles}
          onRestoreNamed={(title) =>
            actionError.profileId
              ? void setStatus(actionError.profileId, "active", title)
              : undefined
          }
          onClose={clearActionError}
        />
      ) : null}
    </>
  );

  if (loading) {
    return (
      <div className="campus-station" data-testid="campus-station-loading">
        <div className="st-body">
          <div className="st-col">
            <div className="mod">
              <div className="sk" style={{ width: 148 }} />
              <div className="sk" />
              <div className="sk" style={{ width: "62%" }} />
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="campus-station" data-testid="campus-station-error">
        <div className="st-body">
          <div className="st-col">
            <div className="alert">
              <Icon name="warning" size={15} />
              <div className="alert-text">
                <span className="alert-title">
                  {t(campusErrorKey(campusErrorInfo(error).code), {
                    defaultValue: campusErrorInfo(error).message || t("campus.common.error"),
                  })}
                </span>
              </div>
              {retryable ? (
                <button
                  type="button"
                  className="btn btn--ghost btn--sm"
                  onClick={reload}
                  data-testid="campus-station-retry"
                >
                  {t("campus.common.retry")}
                </button>
              ) : null}
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (!activeProfile) {
    return (
      <div className="campus-station" data-testid="campus-station-empty" data-track={track}>
        <div className="st-body">
          <div className="st-col">
            <header className="st-head">
              <h1 className="st-title">{t(`campus.track.${track}.name`)}</h1>
              <p className="st-sub">{t(`campus.track.${track}.tagline`)}</p>
            </header>
            <div className="mod">
              <div className="empty">
                <span className="ib ib--brand">
                  <Icon name="user" size={17} />
                </span>
                <span className="empty-title">{t("campus.profile.empty")}</span>
              </div>
              {archivedCount > 0 ? (
                <button
                  type="button"
                  className="btn btn--ghost btn--sm btn-start"
                  onClick={() => setShowArchived(true)}
                  data-testid="campus-profile-archived-entry"
                >
                  <Icon name="archive" size={13} />
                  <span>{t("campus.archived.title")}</span>
                  <span className="num">{archivedCount}</span>
                </button>
              ) : null}
              <ProfileCreateCard
                track={track}
                busy={creatingProfile}
                onCreate={(input) => {
                  void createProfile(input);
                }}
              />
            </div>
          </div>
        </div>
        {dialogs}
      </div>
    );
  }

  const ctx: PanelContext = {
    profileId: activeProfile.id,
    selectedDocId,
    onSelectDoc: setSelectedDocId,
    reviewItems: review.items,
    reviewLoading: review.loading,
    onReviewResult: (reviewId, correct) => {
      void review.submit(reviewId, correct);
    },
    onGotoTab: setActiveTab,
  };
  const badges: Record<string, number> = { review: review.items.length };

  return (
    <div className="campus-station" data-testid="campus-station" data-track={track}>
      <header className="st-top">
        <span className="st-top-title">{t(`campus.nav.${track}`)}</span>
        <ProfileSwitcher
          profiles={profiles}
          activeId={activeProfile.id}
          onSwitch={(id) => void setActive(id)}
          onCreate={() => setShowCreateCard(true)}
          onArchive={(id) => void setStatus(id, "archived")}
          onRename={(id) => setRenameId(id)}
          onShowArchived={() => setShowArchived(true)}
        />
      </header>

      <div className="st-body thin">
        <div className="st-col">
          <header className="st-head">
            <h1 className="st-title">{t(`campus.track.${track}.name`)}</h1>
            <p className="st-sub">{t(`campus.track.${track}.tagline`)}</p>
          </header>

          {showCreateCard ? (
            <ProfileCreateCard
              track={track}
              busy={creatingProfile}
              onCreate={(input) => {
                void createProfile(input).then((created) => {
                  if (created) setShowCreateCard(false);
                });
              }}
              onCancel={() => setShowCreateCard(false)}
            />
          ) : null}

          <EmptyModelGuide capabilities={capabilities} />

          <StationTabs
            track={track}
            panels={panels}
            badges={badges}
            active={selected}
            onSelect={setActiveTab}
          />

          {panels.map(({ key, render }) => (
            <div
              key={key}
              className={key === selected ? "st-pane is-on" : "st-pane"}
              role="tabpanel"
              id={`cs-pane-${track}-${key}`}
              aria-labelledby={`cs-tab-${track}-${key}`}
              hidden={key !== selected}
              data-pane={key}
              data-testid={`campus-station-pane-${key}`}
            >
              {render(ctx)}
            </div>
          ))}
        </div>

        <StationRail
          track={track}
          profile={activeProfile}
          dueCount={review.items.length}
          onGotoReview={() => setActiveTab("review")}
        />
      </div>
      {dialogs}
    </div>
  );
}

interface TabsProps {
  track: CampusTrack;
  panels: readonly PanelSpec[];
  badges: Record<string, number>;
  active: string;
  onSelect: (key: string) => void;
}

function StationTabs({ track, panels, badges, active, onSelect }: TabsProps) {
  const { t } = useTranslation();
  const listRef = useRef<HTMLDivElement>(null);

  // 页签条溢出时横向滚动、不折行，选中项始终留在视野内。scrollLeft 手工算：
  // scrollIntoView 会连带滚动外层祖先，选中最后一个页签时整站会跳走。
  const keepInView = (key: string) => {
    const list = listRef.current;
    const el = list?.querySelector<HTMLElement>(`[data-tab-key="${key}"]`);
    if (!list || !el) return;
    const left = el.offsetLeft;
    const right = left + el.offsetWidth;
    if (left < list.scrollLeft) list.scrollLeft = Math.max(0, left - 8);
    else if (right > list.scrollLeft + list.clientWidth) {
      list.scrollLeft = right - list.clientWidth + 8;
    }
  };

  useEffect(() => {
    keepInView(active);
  }, [active]);

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const keys = panels.map((panel) => panel.key);
    const from = Math.max(keys.indexOf(active), 0);
    const to =
      event.key === "ArrowRight"
        ? (from + 1) % keys.length
        : event.key === "ArrowLeft"
          ? (from - 1 + keys.length) % keys.length
          : event.key === "Home"
            ? 0
            : event.key === "End"
              ? keys.length - 1
              : -1;
    if (to < 0) return;
    event.preventDefault();
    onSelect(keys[to]);
    listRef.current?.querySelectorAll<HTMLElement>("[data-tab-key]")[to]?.focus({
      preventScroll: true,
    });
  };

  return (
    <div
      className="st-tabs"
      role="tablist"
      ref={listRef}
      aria-label={t("campus.station.tabs_aria", { track: t(`campus.nav.${track}`) })}
      onKeyDown={onKeyDown}
    >
      {panels.map((panel) => {
        const on = panel.key === active;
        const badge = badges[panel.key] ?? 0;
        return (
          <button
            key={panel.key}
            type="button"
            className={on ? "st-tab is-on" : "st-tab"}
            role="tab"
            id={`cs-tab-${track}-${panel.key}`}
            data-tab-key={panel.key}
            data-testid={`campus-station-tab-${panel.key}`}
            aria-selected={on}
            aria-controls={`cs-pane-${track}-${panel.key}`}
            tabIndex={on ? 0 : -1}
            onClick={() => onSelect(panel.key)}
          >
            {t(`campus.station.tab.${panel.tab}`)}
            {badge > 0 ? <span className="tb num">{badge}</span> : null}
          </button>
        );
      })}
    </div>
  );
}

interface RailProps {
  track: CampusTrack;
  profile: ExamProfile;
  dueCount: number;
  onGotoReview: () => void;
}

// 右栏只放跨模块都成立的常驻状态：倒计时 / 截止、学习进度、连续打卡。
// 每张卡都以真实数据为条件，没有数据就不占位（不画一个空壳指标）。
function StationRail({ track, profile, dueCount, onGotoReview }: RailProps) {
  const { t } = useTranslation();
  const Banner = TRACK_BANNERS[track];
  const { progress, loading } = usePlanProgress(profile.id);
  const tracks = progress ? Object.entries(progress.by_track) : [];
  const heat = progress?.heatmap ?? [];
  const total = tracks.reduce((sum, [, stat]) => sum + stat.total, 0);
  const done = tracks.reduce((sum, [, stat]) => sum + stat.done, 0);
  const rate = total ? Math.round((done / total) * 100) : 0;

  return (
    <aside className="st-rail thin" data-testid="campus-station-rail">
      <Banner profile={profile} planRate={total ? done / total : null} />

      {dueCount > 0 ? (
        <button
          type="button"
          className="btn btn--soft btn--sm btn-start"
          onClick={onGotoReview}
          data-testid="campus-station-goto-review"
        >
          {t("campus.station.goto_review")}
          <Icon name="chevronRight" size={12} />
        </button>
      ) : null}

      {loading && !progress ? (
        <div className="card">
          <div className="sk" style={{ width: 120 }} />
          <div className="sk" />
          <div className="sk" style={{ width: "70%" }} />
        </div>
      ) : null}

      {progress && tracks.length > 0 ? (
        <div className="card" data-testid="campus-station-progress">
          <div className="sec">
            <span className="ib ib--accent">
              <Icon name="chart" size={16} />
            </span>
            <div className="sec-text">
              <span className="sec-title">{t("campus.station.progress_title")}</span>
              <span className="sec-desc">{t("campus.station.progress_desc")}</span>
            </div>
            <span className="sec-n" data-testid="campus-station-progress-rate">
              {rate}%
            </span>
          </div>
          {tracks.map(([subject, stat]) => (
            <div className="prog" key={subject} data-testid="campus-station-progress-row">
              <span className="prog-k">
                {t(TRACK_LABEL_KEYS[subject] ?? "", { defaultValue: subject })}
              </span>
              <span className="bar">
                <i style={{ "--w": `${Math.round(stat.rate * 100)}%` } as Record<string, string>} />
              </span>
              <span className="prog-v">
                {stat.done}/{stat.total}
              </span>
            </div>
          ))}
        </div>
      ) : null}

      {progress && (progress.streak_days > 0 || heat.length > 0) ? (
        <div className="card" data-testid="campus-station-streak">
          <div className="sec">
            <span className="ib ib--brand">
              <Icon name="flame" size={16} />
            </span>
            <div className="sec-text">
              <span className="sec-title">{t("campus.station.streak_title")}</span>
              <span className="sec-desc">{t("campus.station.streak_desc")}</span>
            </div>
            <span className="sec-n">
              {t("campus.station.streak_days", { count: progress.streak_days })}
            </span>
          </div>
          <div className="heat">
            {heat.map((cell) => (
              <span
                key={cell.date}
                className={
                  cell.count >= 4
                    ? "hc hc--3"
                    : cell.count >= 2
                      ? "hc hc--2"
                      : cell.count >= 1
                        ? "hc hc--1"
                        : "hc"
                }
                title={cell.date}
                data-count={cell.count}
                data-testid="campus-station-heat-cell"
              />
            ))}
          </div>
        </div>
      ) : null}
    </aside>
  );
}

const ACTION_HEADING_KEY: Record<ProfileAction, string> = {
  create: "campus.profile.action_create_failed",
  archive: "campus.profile.action_archive_failed",
  restore: "campus.profile.action_restore_failed",
  rename: "campus.profile.action_rename_failed",
};

function ProfileActionDialog({
  error,
  profiles,
  onRestoreNamed,
  onClose,
}: {
  error: ProfileActionError;
  profiles: ExamProfile[];
  onRestoreNamed: (title: string) => void;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const info = campusErrorInfo(error.error);
  const code = info.code;
  const duplicate = code === "DUPLICATE_TITLE";
  const restoring = error.action === "restore" && duplicate && error.profileId !== null;
  const [title, setTitle] = useState(() =>
    restoring ? suggestProfileTitle(profiles, error.title, error.profileId ?? undefined) : "",
  );
  const clean = title.trim();
  const free =
    clean !== "" && !profileTitleTaken(profiles, clean, error.profileId ?? undefined);

  return (
    <CampusDialog
      testId="campus-profile-conflict"
      title={t(ACTION_HEADING_KEY[error.action])}
      icon="warning"
      onClose={onClose}
      footer={
        <>
          <button
            type="button"
            className="btn btn--text"
            onClick={onClose}
            data-testid="campus-profile-conflict-cancel"
          >
            {t("campus.profile.create_cancel")}
          </button>
          <button
            type="button"
            className="btn btn--primary"
            onClick={() => (restoring ? onRestoreNamed(clean) : onClose())}
            disabled={restoring && !free}
            data-testid="campus-profile-conflict-ok"
          >
            {t(restoring ? "campus.profile.restore_and_rename" : "campus.common.got_it")}
          </button>
        </>
      }
    >
      <div className="stack-gap" data-testid="campus-profile-conflict-body">
        <p className="dlg-lead">
          {t(campusErrorKey(code), {
            defaultValue: info.message || t("campus.common.error"),
          })}
        </p>
        {duplicate && error.action === "create" ? (
          <p className="dlg-note">{t("campus.profile.duplicate_hint", { title: error.title })}</p>
        ) : null}
        {restoring ? (
          <>
            <p className="dlg-note">
              {t("campus.profile.restore_rename_hint", { title: error.title })}
            </p>
            <div className="field">
              <span className="field-label">{t("campus.profile.title_label")}</span>
              <input
                className="input"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                data-testid="campus-profile-conflict-title"
              />
            </div>
            {!free ? (
              <p className="field-err" data-testid="campus-profile-conflict-error">
                {t(
                  clean === "" ? "campus.profile.title_required" : "campus.error.duplicate_title",
                )}
              </p>
            ) : null}
          </>
        ) : null}
      </div>
    </CampusDialog>
  );
}
