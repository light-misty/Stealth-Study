import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import { createProfile, patchProfile } from "../../campus/api";
import { useActiveProfile, useProfiles } from "../../campus/hooks";
import type {
  CampusTrack,
  ExamProfile,
  ProfileCreateInput,
  ProfileStatus,
} from "../../campus/types";
import { campusErrorInfo } from "../../campus/utils";

// The single place the station reads its profile from (04 §3.1): panels consume the
// active profile through this context instead of each firing their own A1/A6 request.

export type ProfileAction = "create" | "archive" | "restore";

export interface ProfileActionError {
  action: ProfileAction;
  title: string;
  error: unknown;
}

export interface CampusProfileContextValue {
  profiles: ExamProfile[];
  activeProfile: ExamProfile | null;
  activeId: string | null;
  loading: boolean;
  error: unknown;
  retryable: boolean;
  creating: boolean;
  actionError: ProfileActionError | null;
  clearActionError: () => void;
  reload: () => void;
  setActive: (id: string | null) => Promise<void>;
  createProfile: (input: ProfileCreateInput) => Promise<ExamProfile | null>;
  setStatus: (id: string, status: ProfileStatus) => Promise<void>;
}

const CampusProfileContext = createContext<CampusProfileContextValue | null>(null);

const statusAction = (status: ProfileStatus): ProfileAction =>
  status === "archived" ? "archive" : "restore";

export function CampusProfileProvider({
  track,
  children,
}: {
  track?: CampusTrack;
  children: ReactNode;
}) {
  const { profiles, loading, error, reload } = useProfiles(track);
  const {
    profile,
    activeId,
    loading: activeLoading,
    error: activeError,
    setActive,
  } = useActiveProfile(profiles);
  const [creating, setCreating] = useState(false);
  const [actionError, setActionError] = useState<ProfileActionError | null>(null);

  const create = useCallback(
    async (input: ProfileCreateInput) => {
      setCreating(true);
      setActionError(null);
      try {
        const created = await createProfile(input);
        // Adopt the new profile right away so the station does not sit on "no profile"
        // for the round-trip; a failed adoption still leaves the profile created.
        await setActive(created.id);
        reload();
        return created;
      } catch (err) {
        setActionError({ action: "create", title: input.title, error: err });
        return null;
      } finally {
        setCreating(false);
      }
    },
    [reload, setActive],
  );

  const setStatus = useCallback(
    async (id: string, status: ProfileStatus) => {
      setActionError(null);
      const title = profiles.find((p) => p.id === id)?.title ?? "";
      try {
        await patchProfile(id, { status });
        reload();
      } catch (err) {
        setActionError({ action: statusAction(status), title, error: err });
      }
    },
    [profiles, reload],
  );

  const clearActionError = useCallback(() => setActionError(null), []);

  const value = useMemo<CampusProfileContextValue>(
    () => ({
      profiles,
      activeProfile: profile,
      activeId,
      loading: loading || activeLoading,
      error: error ?? activeError,
      retryable: campusErrorInfo(error ?? activeError).retryable,
      creating,
      actionError,
      clearActionError,
      reload,
      setActive,
      createProfile: create,
      setStatus,
    }),
    [
      profiles,
      profile,
      activeId,
      loading,
      activeLoading,
      error,
      activeError,
      creating,
      actionError,
      clearActionError,
      reload,
      setActive,
      create,
      setStatus,
    ],
  );

  return <CampusProfileContext.Provider value={value}>{children}</CampusProfileContext.Provider>;
}

export function useCampusProfile(): CampusProfileContextValue {
  const value = useContext(CampusProfileContext);
  if (!value) {
    throw new Error("useCampusProfile must be used inside a CampusProfileProvider");
  }
  return value;
}
