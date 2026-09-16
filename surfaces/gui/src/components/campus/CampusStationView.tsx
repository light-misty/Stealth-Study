import { useState, type ReactElement } from "react";
import { useTranslation } from "react-i18next";
import { patchProfile } from "../../campus/api";
import { useCapabilities, useDeadlineViews } from "../../campus/hooks";
import type { CampusTrack, ExamProfile } from "../../campus/types";
import { campusErrorInfo, campusErrorKey } from "../../campus/utils";
import { CampusProfileProvider, useCampusProfile } from "./CampusProfileContext";
import { CountdownBanner } from "./CountdownBanner";
import { DeadlineBanner } from "./DeadlineBanner";
import { EmptyModelGuide } from "./EmptyModelGuide";
import { LibraryPanel } from "./LibraryPanel";
import { MistakeBookPanel } from "./MistakeBookPanel";
import { ProfileCreateCard } from "./ProfileCreateCard";
import { ProfileSwitcher } from "./ProfileSwitcher";
import { QAChatPanel } from "./QAChatPanel";
import { ReviewQueuePanel } from "./ReviewQueuePanel";
import { AssessmentFlow } from "./cet/AssessmentFlow";
import { CommonErrorsCard } from "./cet/CommonErrorsCard";
import { EssayGradingPanel } from "./cet/EssayGradingPanel";
import { ListeningDrill } from "./cet/ListeningDrill";
import { MockExamConsole } from "./cet/MockExamConsole";
import { TranslationGradingPanel } from "./cet/TranslationGradingPanel";
import { VocabPanel } from "./cet/VocabPanel";

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

// 04 §2.1 puts the library and its Q&A on the kaoyan track. Tracks get their own entry so
// T17/T18/T19 can append their business panels without touching this file's logic.
const LIBRARY_PANELS: readonly PanelSpec[] = [
  {
    key: "library",
    render: ({ profileId, selectedDocId, onSelectDoc }) => (
      <LibraryPanel profileId={profileId} selectedDocId={selectedDocId} onSelectDoc={onSelectDoc} />
    ),
  },
  {
    key: "qa",
    render: ({ profileId, selectedDocId }) => (
      <QAChatPanel profileId={profileId} docId={selectedDocId ?? undefined} />
    ),
  },
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
  kaoyan: [...SHARED_PANELS, ...LIBRARY_PANELS],
  cert: SHARED_PANELS,
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
  const { profiles, activeProfile, loading, error, retryable, reload, setActive, createProfile } =
    useCampusProfile();
  const { capabilities } = useCapabilities();
  const [creating, setCreating] = useState(false);
  const [selectedDocId, setSelectedDocId] = useState<string | null>(null);

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

  if (!activeProfile) {
    return (
      <div className="grid gap-3" data-testid="campus-station-empty" data-track={track}>
        <ProfileCreateCard
          track={track}
          busy={creating}
          onCreate={(input) => {
            void createProfile(input).then((created) => {
              if (created) setCreating(false);
            });
          }}
        />
      </div>
    );
  }

  const archive = async (id: string) => {
    await patchProfile(id, { status: "archived" });
    reload();
  };

  return (
    <div className="grid gap-3" data-testid="campus-station" data-track={track}>
      <div className="grid gap-2.5" data-testid="campus-station-header">
        <ProfileSwitcher
          profiles={profiles}
          activeId={activeProfile.id}
          onSwitch={(id) => void setActive(id)}
          onCreate={() => setCreating(true)}
          onArchive={(id) => void archive(id)}
        />
        {creating ? (
          <ProfileCreateCard
            track={track}
            busy={creating}
            onCreate={(input) => {
              void createProfile(input).then((created) => {
                if (created) setCreating(false);
              });
            }}
            onCancel={() => setCreating(false)}
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
  );
}
