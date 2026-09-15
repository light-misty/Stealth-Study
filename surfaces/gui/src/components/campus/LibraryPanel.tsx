import { useCallback, useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import { pollDocReady, useLibraryDocs } from "../../campus/hooks";
import type { ParseStatus } from "../../campus/types";
import { campusErrorInfo, campusErrorKey } from "../../campus/utils";

// The library list (B1-B5). Parsing is async on the backend, so a doc that is still
// pending is polled — and only that doc — until it reports ready/failed (04 §8).

const STATUS_KEYS: Record<ParseStatus, string> = {
  pending: "campus.library.parsing",
  ready: "campus.library.ready",
  failed: "campus.library.failed",
};

export function LibraryPanel({
  profileId,
  selectedDocId,
  onSelectDoc,
}: {
  profileId: string;
  selectedDocId?: string | null;
  onSelectDoc?: (docId: string) => void;
}) {
  const { t } = useTranslation();
  const { items, loading, error, retryable, reload, importDoc, retry, remove, applyDoc } =
    useLibraryDocs(profileId);
  const stops = useRef<Record<string, () => void>>({});

  const startPolling = useCallback(
    (docId: string) => {
      if (stops.current[docId]) return;
      stops.current[docId] = pollDocReady(docId, 1500, (doc) => {
        applyDoc(doc);
        if (doc.parse_status !== "pending") {
          stops.current[docId]?.();
          delete stops.current[docId];
        }
      });
    },
    [applyDoc],
  );

  useEffect(() => {
    for (const doc of items) if (doc.parse_status === "pending") startPolling(doc.id);
  }, [items, startPolling]);

  useEffect(() => {
    const running = stops.current;
    return () => {
      for (const stop of Object.values(running)) stop();
    };
  }, []);

  const pickFile = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    const created = await importDoc(file);
    if (created && created.parse_status === "pending") startPolling(created.id);
  };

  return (
    <div className="rounded-xl2 border border-line bg-panel" data-testid="campus-library-panel">
      <div className="flex items-center justify-between px-4 pt-3.5">
        <div className="text-[13px] font-semibold text-ink">{t("campus.library.title")}</div>
        <label className="text-[12px] text-accent cursor-pointer" data-testid="campus-library-import-label">
          {t("campus.library.import")}
          <input
            type="file"
            className="hidden"
            onChange={(e) => void pickFile(e)}
            data-testid="campus-library-import"
          />
        </label>
      </div>

      {loading ? (
        <div className="px-4 py-3 text-[12px] text-faint" data-testid="campus-library-loading">
          {t("campus.common.loading")}
        </div>
      ) : null}

      {error ? (
        <div className="px-4 py-2 text-[12px] text-warnInk" data-testid="campus-library-error">
          {t(campusErrorKey(campusErrorInfo(error).code), {
            defaultValue: campusErrorInfo(error).message || t("campus.common.error"),
          })}
          {retryable ? (
            <button type="button" className="ml-2 text-accent" onClick={reload}>
              {t("campus.common.retry")}
            </button>
          ) : null}
        </div>
      ) : null}

      {!loading && items.length === 0 ? (
        <div className="px-4 py-3 text-[12px] text-faint" data-testid="campus-library-empty">
          {t("campus.library.empty")}
        </div>
      ) : null}

      <ul className="mt-2 grid gap-1.5 px-4 pb-3.5">
        {items.map((doc) => (
          <li
            key={doc.id}
            className="flex items-center justify-between gap-2 rounded-lg border border-line px-3 py-2"
            data-testid="campus-library-row"
            data-id={doc.id}
            data-parse-status={doc.parse_status}
            data-selected={selectedDocId === doc.id ? "true" : "false"}
          >
            <div className="min-w-0">
              <button
                type="button"
                className="text-[12px] text-ink truncate"
                onClick={() => onSelectDoc?.(doc.id)}
                data-testid="campus-library-title"
              >
                {doc.title}
              </button>
              <div className="text-[11px] text-faint" data-testid="campus-library-status">
                {t(STATUS_KEYS[doc.parse_status])}
              </div>
            </div>
            <div className="flex items-center gap-1.5">
              {doc.parse_status === "failed" ? (
                <button
                  type="button"
                  className="px-2 py-1 rounded-lg text-[12px] text-accent border border-line"
                  onClick={() => void retry(doc.id)}
                  data-testid="campus-library-retry"
                >
                  {t("campus.library.retry")}
                </button>
              ) : null}
              <button
                type="button"
                className="px-2 py-1 rounded-lg text-[12px] text-faint hover:text-danger border border-line"
                onClick={() => void remove(doc.id)}
                data-testid="campus-library-delete"
              >
                {t("campus.library.delete")}
              </button>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
