import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import { createProfile } from "../../campus/api";
import { useActiveProfile, useProfiles } from "../../campus/hooks";
import type { CampusTrack, ExamProfile, ProfileCreateInput } from "../../campus/types";
import { campusErrorInfo } from "../../campus/utils";

// The single place the station reads its profile from (04 §3.1): panels consume the
// active profile through this context instead of each firing their own A1/A6 request.

export interface CampusProfileContextValue {
  profiles: ExamProfile[];
  activeProfile: ExamProfile | null;
  activeId: string | null;
  loading: boolean;
  error: unknown;
  retryable: boolean;
  creating: boolean;
  createError: unknown;
  reload: () => void;
  setActive: (id: string | null) => Promise<void>;
  createProfile: (input: ProfileCreateInput) => Promise<ExamProfile | null>;
}

const CampusProfileContext = createContext<CampusProfileContextValue | null>(null);

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
  const [createError, setCreateError] = useState<unknown>(null);

  const create = useCallback(
    async (input: ProfileCreateInput) => {
      setCreating(true);
      setCreateError(null);
      try {
        const created = await createProfile(input);
        // Adopt the new profile right away so the station does not sit on "no profile"
        // for the round-trip; a failed adoption still leaves the profile created.
        await setActive(created.id);
        reload();
        return created;
      } catch (err) {
        setCreateError(err);
        return null;
      } finally {
        setCreating(false);
      }
    },
    [reload, setActive],
  );

  const value = useMemo<CampusProfileContextValue>(
    () => ({
      profiles,
      activeProfile: profile,
      activeId,
      loading: loading || activeLoading,
      error: error ?? activeError ?? createError,
      retryable: campusErrorInfo(error ?? activeError ?? createError).retryable,
      creating,
      createError,
      reload,
      setActive,
      createProfile: create,
    }),
    [
      profiles,
      profile,
      activeId,
      loading,
      activeLoading,
      error,
      activeError,
      createError,
      creating,
      reload,
      setActive,
      create,
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
