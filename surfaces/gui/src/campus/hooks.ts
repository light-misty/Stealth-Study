import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  askLibrary,
  deleteLibraryDoc,
  getAppState,
  getCapabilities,
  getLibraryDoc,
  getReminders,
  importLibraryDoc,
  listDueReviews,
  listLibraryDocs,
  listMistakes,
  listProfiles,
  patchAppState,
  patchMistake,
  retryLibraryDoc,
  submitReviewResult,
} from "./api";
import type {
  Attribution,
  CampusTrack,
  CapabilitiesReport,
  DeadlineView,
  ExamProfile,
  LibraryQAAnswer,
  MistakeBookEntry,
  MistakeFilters,
  ReviewDueItem,
  SourceDoc,
} from "./types";
import { campusErrorInfo } from "./utils";

// Data hooks for the campus station. Every hook reads through campus/api.ts and keeps
// its own loading/error state; panels stay presentational. Mutations update the local
// list first (optimistic) and roll it back when the request fails, so a flaky backend
// never leaves the UI showing a write that did not happen.

interface AsyncState<T> {
  data: T;
  setData: React.Dispatch<React.SetStateAction<T>>;
  setError: React.Dispatch<React.SetStateAction<unknown>>;
  loading: boolean;
  error: unknown;
  retryable: boolean;
  reload: () => void;
}

function useAsync<T>(load: () => Promise<T>, deps: unknown[], initial: T): AsyncState<T> {
  const [data, setData] = useState<T>(initial);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const [nonce, setNonce] = useState(0);
  const loadRef = useRef(load);
  loadRef.current = load;

  useEffect(() => {
    let alive = true;
    setLoading(true);
    loadRef.current().then(
      (value) => {
        if (!alive) return;
        setData(value);
        setError(null);
        setLoading(false);
      },
      (err) => {
        if (!alive) return;
        setError(err);
        setLoading(false);
      },
    );
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, nonce]);

  const reload = useCallback(() => setNonce((n) => n + 1), []);
  return { data, setData, setError, loading, error, retryable: campusErrorInfo(error).retryable, reload };
}

/** A1: every profile for the station (archived ones stay hidden by the switcher). */
export function useProfiles(track?: CampusTrack) {
  const { data, loading, error, retryable, reload } = useAsync<ExamProfile[]>(
    () => listProfiles(track).then((res) => res?.items ?? []),
    [track],
    [],
  );
  return { profiles: data, loading, error, retryable, reload };
}

/** A6 + A7: the remembered active profile, with the write-back on switch. */
export function useActiveProfile(profiles: ExamProfile[]) {
  const [activeId, setActiveId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    let alive = true;
    getAppState().then(
      (state) => {
        if (!alive) return;
        setActiveId(state?.active_profile_id ?? null);
        setLoading(false);
      },
      (err) => {
        if (!alive) return;
        setError(err);
        setLoading(false);
      },
    );
    return () => {
      alive = false;
    };
  }, []);

  const profile = useMemo(() => {
    const remembered = profiles.find((p) => p.id === activeId && p.status !== "archived");
    return remembered ?? profiles.find((p) => p.status === "active") ?? null;
  }, [profiles, activeId]);

  const setActive = useCallback(async (id: string | null) => {
    setError(null);
    try {
      await patchAppState({ active_profile_id: id });
      setActiveId(id);
    } catch (err) {
      setError(err);
    }
  }, []);

  return { profile, activeId, loading, error, setActive };
}

/** D5 / D6: today's review queue; submitting drops the item immediately. */
export function useDueReviews(profileId: string | null) {
  const { data, setData, setError, loading, error, retryable, reload } = useAsync<
    ReviewDueItem[]
  >(
    () => (profileId ? listDueReviews(profileId).then((res) => res?.items ?? []) : Promise.resolve([])),
    [profileId],
    [],
  );

  const submit = useCallback(
    async (reviewId: string, correct: boolean) => {
      const snapshot = data;
      setData((prev) => prev.filter((item) => item.id !== reviewId));
      try {
        return await submitReviewResult(reviewId, correct);
      } catch (err) {
        setData(snapshot);
        setError(err);
        return null;
      }
    },
    [data, setData, setError],
  );

  return { items: data, loading, error, retryable, reload, submit };
}

/** D1 / D2: the mistake book; re-attributing patches the row in place. */
export function useMistakes(profileId: string | null, filters: MistakeFilters = {}) {
  const filterKey = JSON.stringify(filters);
  const filtersRef = useRef(filters);
  filtersRef.current = filters;

  const { data, setData, setError, loading, error, retryable, reload } = useAsync<{
    items: MistakeBookEntry[];
    total: number;
  }>(
    () =>
      profileId
        ? listMistakes(profileId, filtersRef.current).then((res) => ({
            items: res?.items ?? [],
            total: res?.total ?? 0,
          }))
        : Promise.resolve({ items: [], total: 0 }),
    [profileId, filterKey],
    { items: [], total: 0 },
  );

  const setAttribution = useCallback(
    async (id: string, attribution: Attribution) => {
      const snapshot = data.items;
      setData((prev) => ({
        ...prev,
        items: prev.items.map((item) => (item.id === id ? { ...item, attribution } : item)),
      }));
      try {
        const updated = await patchMistake(id, { attribution });
        setData((prev) => ({
          ...prev,
          items: prev.items.map((item) => (item.id === id ? updated : item)),
        }));
        return updated;
      } catch (err) {
        setData((prev) => ({ ...prev, items: snapshot }));
        setError(err);
        return null;
      }
    },
    [data.items, setData, setError],
  );

  return { items: data.items, total: data.total, loading, error, retryable, reload, setAttribution };
}

/** B1-B5: the library list plus import / retry / delete. */
export function useLibraryDocs(profileId: string | null) {
  const { data, setData, setError, loading, error, retryable, reload } = useAsync<SourceDoc[]>(
    () =>
      profileId ? listLibraryDocs(profileId).then((res) => res?.items ?? []) : Promise.resolve([]),
    [profileId],
    [],
  );

  const importDoc = useCallback(
    async (file: File) => {
      if (!profileId) return null;
      setError(null);
      try {
        const created = await importLibraryDoc(profileId, file);
        setData((prev) => [...prev, created]);
        return created;
      } catch (err) {
        setError(err);
        return null;
      }
    },
    [profileId, setData, setError],
  );

  const retry = useCallback(
    async (docId: string) => {
      setError(null);
      try {
        const updated = await retryLibraryDoc(docId);
        setData((prev) => prev.map((d) => (d.id === docId ? updated : d)));
        return updated;
      } catch (err) {
        setError(err);
        return null;
      }
    },
    [setData, setError],
  );

  const remove = useCallback(
    async (docId: string) => {
      setError(null);
      try {
        await deleteLibraryDoc(docId);
        setData((prev) => prev.filter((d) => d.id !== docId));
        return true;
      } catch (err) {
        setError(err);
        return false;
      }
    },
    [setData, setError],
  );

  /** Merge a document fetched elsewhere (the parse-status poll) into the list. */
  const applyDoc = useCallback(
    (updated: SourceDoc) => {
      setData((prev) =>
        prev.some((d) => d.id === updated.id)
          ? prev.map((d) => (d.id === updated.id ? updated : d))
          : [...prev, updated],
      );
    },
    [setData],
  );

  return { items: data, loading, error, retryable, reload, importDoc, retry, remove, applyDoc };
}

/** B3: the only polling in the station — parse status until ready/failed (04 §8). */
export function pollDocReady(
  docId: string,
  intervalMs = 1500,
  onUpdate?: (doc: SourceDoc) => void,
  maxAttempts = 40,
): () => void {
  let attempts = 0;
  let stopped = false;
  const stop = () => {
    stopped = true;
    clearInterval(timer);
  };
  const tick = async () => {
    if (stopped) return;
    attempts += 1;
    try {
      const doc = await getLibraryDoc(docId);
      onUpdate?.(doc);
      if (doc?.parse_status === "ready" || doc?.parse_status === "failed" || attempts >= maxAttempts) {
        stop();
      }
    } catch {
      if (attempts >= maxAttempts) stop();
    }
  };
  const timer = setInterval(tick, intervalMs);
  return stop;
}

/** B6: one question against the library, citations included. */
export function useLibraryQA(profileId: string | null, docId?: string) {
  const [answer, setAnswer] = useState<LibraryQAAnswer | null>(null);
  const [asking, setAsking] = useState(false);
  const [error, setError] = useState<unknown>(null);

  const ask = useCallback(
    async (question: string) => {
      const trimmed = question.trim();
      if (!profileId || !trimmed) return null;
      setAsking(true);
      setError(null);
      try {
        const res = await askLibrary(profileId, trimmed, docId);
        setAnswer(res);
        return res;
      } catch (err) {
        setError(err);
        setAnswer(null);
        return null;
      } finally {
        setAsking(false);
      }
    },
    [profileId, docId],
  );

  const reset = useCallback(() => {
    setAnswer(null);
    setError(null);
  }, []);

  return { answer, asking, error, ask, reset };
}

/** A8: model capability report driving EmptyModelGuide. */
export function useCapabilities() {
  const { data, loading, error, reload } = useAsync<CapabilitiesReport | null>(
    () => getCapabilities(),
    [],
    null,
  );
  return { capabilities: data, loading, error, reload };
}

/** H10: the deadline banner feed (application-level reminders, ADR-12). */
export function useDeadlineViews(profileId: string | null) {
  const { data, loading, error, reload } = useAsync<DeadlineView[]>(
    () => (profileId ? getReminders(profileId).then((res) => res?.banner ?? []) : Promise.resolve([])),
    [profileId],
    [],
  );
  return { views: data, loading, error, reload };
}
