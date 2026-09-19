import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import {
  createProfile,
  deleteProfile as deleteProfileRequest,
  patchProfile,
} from "../../campus/api";
import { useActiveProfile, useProfiles } from "../../campus/hooks";
import type {
  CampusTrack,
  ExamProfile,
  ProfileCreateInput,
  ProfileDeleteResult,
  ProfilePatch,
  ProfileStatus,
} from "../../campus/types";
import { campusErrorInfo } from "../../campus/utils";

// The single place the station reads its profile from (04 §3.1): panels consume the
// active profile through this context instead of each firing their own A1/A6 request.

export type ProfileAction = "create" | "archive" | "restore" | "rename";

export interface ProfileActionError {
  action: ProfileAction;
  profileId: string | null;
  title: string;
  error: unknown;
}

export type ProfileRenameResult = { ok: true } | { ok: false; error: unknown };

/** A delete is the one destructive action the dialog reads back, so it answers with the receipt. */
export type ProfileDeleteOutcome =
  | { ok: true; result: ProfileDeleteResult }
  | { ok: false; error: unknown };

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
  renameProfile: (id: string, title: string) => Promise<ProfileRenameResult>;
  setStatus: (id: string, status: ProfileStatus, title?: string) => Promise<void>;
  deleteProfile: (id: string) => Promise<ProfileDeleteOutcome>;
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
        setActionError({ action: "create", profileId: null, title: input.title, error: err });
        return null;
      } finally {
        setCreating(false);
      }
    },
    [reload, setActive],
  );

  const renameProfile = useCallback(
    async (id: string, title: string): Promise<ProfileRenameResult> => {
      try {
        await patchProfile(id, { title });
        reload();
        return { ok: true };
      } catch (err) {
        return { ok: false, error: err };
      }
    },
    [reload],
  );

  // The delete is the one action whose failure the caller has to show *in place* — the
  // confirmation dialog is already the user's last chance, so it keeps the error and the
  // retry rather than trading them for a generic one.
  const deleteProfile = useCallback(
    async (id: string): Promise<ProfileDeleteOutcome> => {
      try {
        const result = await deleteProfileRequest(id);
        reload();
        return { ok: true, result };
      } catch (err) {
        return { ok: false, error: err };
      }
    },
    [reload],
  );

  const setStatus = useCallback(
    async (id: string, status: ProfileStatus, title?: string) => {
      const patch: ProfilePatch = title === undefined ? { status } : { status, title };
      const carrying = title ?? profiles.find((p) => p.id === id)?.title ?? "";
      try {
        await patchProfile(id, patch);
        setActionError(null);
        reload();
      } catch (err) {
        setActionError({
          action: statusAction(status),
          profileId: id,
          title: carrying,
          error: err,
        });
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
      renameProfile,
      reload,
      setActive,
      createProfile: create,
      setStatus,
      deleteProfile,
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
      renameProfile,
      reload,
      setActive,
      create,
      setStatus,
      deleteProfile,
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
