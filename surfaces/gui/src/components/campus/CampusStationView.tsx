import { useEffect, useRef, useState, type KeyboardEvent, type ReactElement } from "react";
import { useTranslation } from "react-i18next";
import type { ProfileAction, ProfileActionError } from "./CampusProfileContext";
import {
  useCapabilities,
  useDeadlineViews,
  useDueReviews,
  usePlanProgress,
} from "../../campus/hooks";
import type {
  CampusTrack,
  DeadlineView,
  ExamProfile,
  ProgressReport,
  TodayProgress,
} from "../../campus/types";
import {
  campusErrorInfo,
  campusErrorKey,
  checkInSummary,
  heatWindow,
  profileTitleTaken,
  progressRatio,
  suggestProfileTitle,
} from "../../campus/utils";
import { CampusProfileProvider, useCampusProfile } from "./CampusProfileContext";
import { ProfileRenameDialog } from "./ProfileRenameDialog";
import { ArchivedProfilesDialog } from "./ArchivedProfilesDialog";
import { CampusDialog } from "./CampusDialog";
import { DeleteProfileDialog } from "./DeleteProfileDialog";
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
  onDeadlinesChanged: () => void;
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
    render: ({ profileId, onDeadlinesChanged }) => (
      <CertExamSetup profileId={profileId} onDeadlinesChanged={onDeadlinesChanged} />
    ),
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
  (args: {
    profile: ExamProfile;
    planRate: number | null;
    deadlineViews: DeadlineView[];
  }) => ReactElement
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
  cert: ({ deadlineViews }) => <DeadlineBanner views={deadlineViews} />,
};

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
    deleteProfile,
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
  const [deleteId, setDeleteId] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<unknown>(null);
  const [selectedDocId, setSelectedDocId] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<string | null>(null);
  const archivedCount = profiles.filter((p) => p.status === "archived").length;
  const panels = TRACK_PANELS[track];
  // A track's first panel is the default; a stale tab key falls back rather than rendering a
  // shell with no pane.
  const selected = panels.some((p) => p.key === activeTab) ? (activeTab as string) : panels[0].key;
  // Owned here rather than by the queue panel so the tab badge and the list agree.
  const review = useDueReviews(activeProfile?.id ?? null);
  // Same reason for the certificate milestones: the rail's countdown and the 节点 panel read
  // the same snapshot, and adding a node has to move the number in the rail immediately.
  const deadlines = useDeadlineViews(
    RAIL_DEADLINES[track] && activeProfile ? activeProfile.id : null,
  );

  const renameTarget = renameId ? profiles.find((p) => p.id === renameId) ?? null : null;
  const deleteTarget = deleteId ? profiles.find((p) => p.id === deleteId) ?? null : null;

  // A failed delete keeps the confirmation on screen with its error: that dialog is the last
  // place showing what the user agreed to destroy, so it must not be traded for a generic one.
  const confirmDelete = async (id: string) => {
    if (deleting) return;
    setDeleting(true);
    setDeleteError(null);
    const outcome = await deleteProfile(id);
    setDeleting(false);
    if (outcome.ok) setDeleteId(null);
    else setDeleteError(outcome.error);
  };

  const askDelete = (id: string) => {
    setDeleteError(null);
    setDeleteId(id);
  };

  const dialogs = (
    <>
      {showArchived ? (
        <ArchivedProfilesDialog
          profiles={profiles}
          onRestore={(id) => void setStatus(id, "active")}
          onRename={(id) => setRenameId(id)}
          onDelete={askDelete}
          onClose={() => setShowArchived(false)}
        />
      ) : null}
      {deleteTarget ? (
        <DeleteProfileDialog
          profile={deleteTarget}
          busy={deleting}
          error={deleteError}
          onConfirm={(id) => void confirmDelete(id)}
          onClose={() => {
            setDeleteId(null);
            setDeleteError(null);
          }}
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
    onDeadlinesChanged: deadlines.reload,
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
          onDelete={askDelete}
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
          deadlineViews={deadlines.views}
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
  deadlineViews: DeadlineView[];
  onGotoReview: () => void;
}

interface RailRow {
  key: string;
  labelKey: string;
  pair: (today: TodayProgress) => { done: number; total: number };
}

const MINUTES_ROW: RailRow = {
  key: "minutes",
  labelKey: "campus.station.row_minutes",
  pair: (today) => ({ done: today.minutes.done, total: today.minutes.plan }),
};
const VOCAB_ROW: RailRow = {
  key: "vocab",
  labelKey: "campus.station.row_vocab",
  pair: (today) => ({ done: today.vocab.done, total: today.vocab.quota }),
};
const TASKS_ROW: RailRow = {
  key: "tasks",
  labelKey: "campus.station.row_tasks",
  pair: (today) => today.tasks,
};
const REVIEW_ROW: RailRow = {
  key: "review",
  labelKey: "campus.station.row_review",
  pair: (today) => today.review,
};
const GRADING_ROW: RailRow = {
  key: "grading",
  labelKey: "campus.station.row_grading",
  pair: (today) => today.grading,
};
const DOCS_ROW: RailRow = {
  key: "docs",
  labelKey: "campus.station.row_docs",
  pair: (today) => ({ done: today.docs.ready, total: today.docs.total }),
};
const KNOWLEDGE_ROW: RailRow = {
  key: "knowledge",
  labelKey: "campus.station.row_knowledge",
  pair: (today) => ({ done: today.knowledge.mastered, total: today.knowledge.total }),
};

// 只有证书台有考试节点时间线（02 §4.17），其余两台的右栏不读 H10，省一次空请求。
const RAIL_DEADLINES: Record<CampusTrack, boolean> = {
  cet: false,
  kaoyan: false,
  cert: true,
};

// 设计稿的今日进度恒为四行：时长打头，后三行是该台自己的口径。表按台子取，
// 组件里不出现 track 分支（01 §3.2）。
const RAIL_ROWS: Record<CampusTrack, readonly RailRow[]> = {
  cet: [MINUTES_ROW, VOCAB_ROW, REVIEW_ROW, GRADING_ROW],
  kaoyan: [MINUTES_ROW, TASKS_ROW, REVIEW_ROW, DOCS_ROW],
  cert: [MINUTES_ROW, KNOWLEDGE_ROW, REVIEW_ROW, GRADING_ROW],
};

const EMPTY_PAIR = { done: 0, total: 0 };

function heatClass(count: number): string {
  if (count >= 4) return "hc hc--3";
  if (count >= 2) return "hc hc--2";
  if (count >= 1) return "hc hc--1";
  return "hc";
}

// 右栏是常驻的三块：倒计时 / 截止、今日进度、连续打卡。设计稿里三台都是这个骨架，
// 所以没有数据时也占住位置（数字取 0 或留白），不再整块消失——那会把中栏挤成半屏。
function StationRail({ track, profile, deadlineViews, onGotoReview }: RailProps) {
  const { t } = useTranslation();
  const Banner = TRACK_BANNERS[track];
  const { progress, loading } = usePlanProgress(profile.id);
  const rows = RAIL_ROWS[track];
  const today = progress?.today ?? null;
  const minutes = today ? rows[0].pair(today) : EMPTY_PAIR;
  const rate = Math.round(progressRatio(minutes.done, minutes.total) * 100);
  const heat = heatWindow(progress?.heatmap ?? []);
  const checkIn = checkInSummary(progress?.heatmap ?? []);

  return (
    <aside className="st-rail thin" data-testid="campus-station-rail">
      <Banner
        profile={profile}
        planRate={progress ? planRateOf(progress) : null}
        deadlineViews={deadlineViews}
      />

      <div className="card" data-testid="campus-station-progress">
        <div className="sec">
          <span className="ib ib--accent">
            <Icon name="chart" size={16} />
          </span>
          <div className="sec-text">
            <span className="sec-title">{t("campus.station.progress_title")}</span>
            <span className="sec-desc">
              {t("campus.station.progress_desc", { minutes: minutes.total })}
            </span>
          </div>
          <span className="sec-n" data-testid="campus-station-progress-rate">
            {rate}%
          </span>
        </div>
        {loading && !progress ? (
          <>
            <div className="sk" />
            <div className="sk" style={{ width: "70%" }} />
          </>
        ) : (
          rows.map((row) => {
            const pair = today ? row.pair(today) : EMPTY_PAIR;
            return (
              <div
                className="prog"
                key={row.key}
                data-testid="campus-station-progress-row"
                data-row={row.key}
                data-done={pair.done}
                data-total={pair.total}
              >
                <span className="prog-k">{t(row.labelKey)}</span>
                <span className="bar">
                  <i
                    style={
                      { "--w": `${Math.round(progressRatio(pair.done, pair.total) * 100)}%` } as Record<
                        string,
                        string
                      >
                    }
                  />
                </span>
                <span className="prog-v">
                  {pair.done}/{pair.total}
                </span>
              </div>
            );
          })
        )}
        <button
          type="button"
          className="btn btn--soft btn--sm btn-start"
          onClick={onGotoReview}
          data-testid="campus-station-goto-review"
        >
          {t("campus.station.goto_review")}
          <Icon name="chevronRight" size={12} />
        </button>
      </div>

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
            {t("campus.station.streak_days", { count: progress?.streak_days ?? 0 })}
          </span>
        </div>
        <div className="heat" data-testid="campus-station-heat">
          {heat.map((cell) => (
            <span
              key={cell.date}
              className={heatClass(cell.count)}
              title={cell.date}
              data-count={cell.count}
              data-testid="campus-station-heat-cell"
            />
          ))}
        </div>
        <span className="lrow-meta" data-testid="campus-station-checkin">
          {t("campus.station.streak_window", {
            weekDone: checkIn.weekDone,
            weekTotal: checkIn.weekTotal,
            monthDone: checkIn.monthDone,
            monthTotal: checkIn.monthTotal,
          })}
        </span>
      </div>
    </aside>
  );
}

/** The hero's progress bar follows the plan board, not today: the share of scheduled work done. */
function planRateOf(progress: ProgressReport): number {
  const totals = Object.values(progress.by_track);
  const total = totals.reduce((sum, stat) => sum + stat.total, 0);
  if (!total) return 0;
  return totals.reduce((sum, stat) => sum + stat.done, 0) / total;
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
