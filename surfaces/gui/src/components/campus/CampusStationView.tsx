import { useState, type ReactElement } from "react";
import { useTranslation } from "react-i18next";
import type { ProfileAction, ProfileActionError } from "./CampusProfileContext";
import { useCapabilities, useDeadlineViews } from "../../campus/hooks";
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

// The shell the three stations share (04 §3.1). Everything track-specific lives in these
// two lookup tables — the component itself never branches on the track, per the layering
// rule in 01 §4 (adding a station panel later means adding a row here, not an `if`).

interface PanelContext {
  profileId: string;
  selectedDocId: string | null;
  onSelectDoc: (docId: string) => void;
}

interface PanelSpec {
  key: string;
  render: (ctx: PanelContext) => ReactElement;
}

const SHARED_PANELS: readonly PanelSpec[] = [
  { key: "mistake", render: ({ profileId }) => <MistakeBookPanel profileId={profileId} /> },
  { key: "review", render: ({ profileId }) => <ReviewQueuePanel profileId={profileId} /> },
];

// 04 §2.1 puts the library and its Q&A on the kaoyan track. The kaoyan Q&A slot is the
// T18 MajorQAView (document picker + clickable page citations) rather than the shared
// QAChatPanel. Tracks get their own entry so T17/T18/T19 can append their business panels
// without touching this file's logic.
const LIBRARY_PANELS: readonly PanelSpec[] = [
  {
    key: "library",
    render: ({ profileId, selectedDocId, onSelectDoc }) => (
      <LibraryPanel profileId={profileId} selectedDocId={selectedDocId} onSelectDoc={onSelectDoc} />
    ),
  },
  {
    key: "qa",
    render: ({ profileId }) => <MajorQAView profileId={profileId} />,
  },
];

const CERT_PANELS: readonly PanelSpec[] = [
  { key: "cert_tree", render: ({ profileId }) => <KnowledgeTreePanel profileId={profileId} /> },
  { key: "cert_grading", render: ({ profileId }) => <SubjectiveGradingPanel profileId={profileId} /> },
  { key: "cert_setup", render: ({ profileId }) => <CertExamSetup profileId={profileId} /> },
];

// T18 kaoyan business panels: the combined plan editor + read-only board (KY-01/03,
// ADR-11), the weekly report view (KY-12) and the per-subject grading chat (KY-05/06).
const KAOYAN_PANELS: readonly PanelSpec[] = [
  { key: "plan", render: ({ profileId }) => <PlanPanel profileId={profileId} /> },
  { key: "weekly", render: ({ profileId }) => <WeeklyReportView profileId={profileId} /> },
  { key: "tutor", render: ({ profileId }) => <SubjectTutorChat profileId={profileId} /> },
];

// CET-01 … CET-13 in track order: placement, vocabulary, listening, essay/translation
// grading, the mock-exam console and the common-mistakes summary.
const CET_PANELS: readonly PanelSpec[] = [
  { key: "assessment", render: ({ profileId }) => <AssessmentFlow profileId={profileId} /> },
  { key: "vocab", render: ({ profileId }) => <VocabPanel profileId={profileId} /> },
  { key: "listening", render: ({ profileId }) => <ListeningDrill profileId={profileId} /> },
  { key: "essay", render: ({ profileId }) => <EssayGradingPanel profileId={profileId} /> },
  {
    key: "translation",
    render: ({ profileId }) => <TranslationGradingPanel profileId={profileId} />,
  },
  { key: "mock", render: ({ profileId }) => <MockExamConsole profileId={profileId} /> },
  { key: "common-errors", render: ({ profileId }) => <CommonErrorsCard profileId={profileId} /> },
];

const TRACK_PANELS: Record<CampusTrack, readonly PanelSpec[]> = {
  cet: [...SHARED_PANELS, ...CET_PANELS],
  kaoyan: [...SHARED_PANELS, ...LIBRARY_PANELS, ...KAOYAN_PANELS],
  cert: [...SHARED_PANELS, ...CERT_PANELS],
};

const TRACK_BANNERS: Record<CampusTrack, (args: { profile: ExamProfile }) => ReactElement | null> =
  {
    cet: ({ profile }) => <CountdownBanner examDate={profile.exam_date} />,
    kaoyan: ({ profile }) => <CountdownBanner examDate={profile.exam_date} />,
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
  const archivedCount = profiles.filter((p) => p.status === "archived").length;

  if (loading) {
    return (
      <div
        className="rounded-xl2 border border-line bg-panel px-4 py-6 text-[13px] text-faint"
        data-testid="campus-station-loading"
      >
        {t("campus.common.loading")}
      </div>
    );
  }

  if (error) {
    return (
      <div
        className="rounded-xl2 border border-warnInk/40 bg-warnSoft px-4 py-3 text-[13px] text-warnInk"
        data-testid="campus-station-error"
      >
        {t(campusErrorKey(campusErrorInfo(error).code), {
          defaultValue: campusErrorInfo(error).message || t("campus.common.error"),
        })}
        {retryable ? (
          <button
            type="button"
            className="ml-2 text-accent"
            onClick={reload}
            data-testid="campus-station-retry"
          >
            {t("campus.common.retry")}
          </button>
        ) : null}
      </div>
    );
  }

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

  if (!activeProfile) {
    return (
      <>
        <div className="grid gap-3" data-testid="campus-station-empty" data-track={track}>
          {archivedCount > 0 ? (
            <button
              type="button"
              className="justify-self-start flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-[13px] text-muted hover:text-ink border border-line"
              onClick={() => setShowArchived(true)}
              data-testid="campus-profile-archived-entry"
            >
              <Icon name="archive" size={13} />
              <span>{t("campus.archived.title")}</span>
              <span className="text-[12px] text-faint">{archivedCount}</span>
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
        {dialogs}
      </>
    );
  }

  return (
    <>
      <div className="grid gap-3" data-testid="campus-station" data-track={track}>
        {/* 页头：备考台名称 + 标语，对齐原型的 page-head（title 22px / sub 12.5px） */}
        <div className="grid gap-1.5" data-testid="campus-station-page-head">
          <h1 className="text-[22px] font-bold leading-[30px] text-ink">
            {t(`campus.track.${track}.name`)}
          </h1>
          <p className="text-[12.5px] leading-[19px] text-muted">
            {t(`campus.track.${track}.tagline`)}
          </p>
        </div>

        <div className="grid gap-2.5" data-testid="campus-station-header">
          <ProfileSwitcher
            profiles={profiles}
            activeId={activeProfile.id}
            onSwitch={(id) => void setActive(id)}
            onCreate={() => setShowCreateCard(true)}
            onArchive={(id) => void setStatus(id, "archived")}
            onRename={(id) => setRenameId(id)}
            onShowArchived={() => setShowArchived(true)}
          />
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
          {TRACK_BANNERS[track]({ profile: activeProfile })}
        </div>

        <div className="grid gap-3">
          {TRACK_PANELS[track].map(({ key, render }) => (
            <div key={key}>
              {render({
                profileId: activeProfile.id,
                selectedDocId,
                onSelectDoc: setSelectedDocId,
              })}
            </div>
          ))}
        </div>
      </div>
      {dialogs}
    </>
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
      onClose={onClose}
      footer={
        <>
          <button
            type="button"
            className="px-2.5 py-1.5 text-[13px] text-faint hover:text-muted"
            onClick={onClose}
            data-testid="campus-profile-conflict-cancel"
          >
            {t("campus.profile.create_cancel")}
          </button>
          <button
            type="button"
            className="px-3 py-1.5 rounded-lg bg-accent text-white text-[13px] disabled:opacity-40"
            onClick={() => (restoring ? onRestoreNamed(clean) : onClose())}
            disabled={restoring && !free}
            data-testid="campus-profile-conflict-ok"
          >
            {t(restoring ? "campus.profile.restore_and_rename" : "campus.common.got_it")}
          </button>
        </>
      }
    >
      <div className="grid gap-1.5" data-testid="campus-profile-conflict-body">
        <p className="text-[13px] leading-[20px] text-ink">
          {t(campusErrorKey(code), {
            defaultValue: info.message || t("campus.common.error"),
          })}
        </p>
        {duplicate && error.action === "create" ? (
          <p className="text-[12.5px] leading-[19px] text-muted">
            {t("campus.profile.duplicate_hint", { title: error.title })}
          </p>
        ) : null}
        {restoring ? (
          <>
            <p className="text-[12.5px] leading-[19px] text-muted">
              {t("campus.profile.restore_rename_hint", { title: error.title })}
            </p>
            <label className="block">
              <span className="text-[12px] text-muted">{t("campus.profile.title_label")}</span>
              <input
                className="mt-1 w-full rounded-lg border border-line bg-transparent px-2.5 py-1.5 text-[13px] text-ink outline-none"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                data-testid="campus-profile-conflict-title"
              />
            </label>
            {!free ? (
              <p className="text-[12px] text-warnInk" data-testid="campus-profile-conflict-error">
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
