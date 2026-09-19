import { useCallback, useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import { pollDocReady, useLibraryDocs } from "../../campus/hooks";
import type { ParseStatus } from "../../campus/types";
import { campusErrorInfo, campusErrorKey } from "../../campus/utils";
import { Icon } from "../Icon";

// The library list (B1-B5). Parsing is async on the backend, so a doc that is still
// pending is polled — and only that doc — until it reports ready/failed (04 §8).
// 解析状态是这一屏唯一会自己变的东西，所以 pending 行给一条进度而不是只有一句「解析中」，
// 用户才知道不是在卡住。导入入口保持 label 包隐藏 file input 的结构。

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
      stops.current[docId] = pollDocReady(profileId, docId, 1500, (doc) => {
        applyDoc(doc);
        if (doc.parse_status !== "pending") {
          stops.current[docId]?.();
          delete stops.current[docId];
        }
      });
    },
    [applyDoc, profileId],
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

  const ready = items.filter((doc) => doc.parse_status === "ready").length;

  return (
    <section className="mod" data-testid="campus-library-panel">
      <div className="mod-head">
        <span className="ib ib--brand">
          <Icon name="file" size={16} />
        </span>
        <div className="mod-head-text">
          <span className="mod-title">{t("campus.library.title")}</span>
          <span className="mod-desc">{t("campus.library.hint")}</span>
        </div>
        <div className="mod-acts">
          {items.length > 0 ? (
            <span className="sec-n" data-testid="campus-library-ready-count">
              {ready} / {items.length}
            </span>
          ) : null}
          <label className="import" data-testid="campus-library-import-label">
            <span className="btn btn--ghost btn--sm">
              <Icon name="upload" size={12} />
              {t("campus.library.import")}
            </span>
            <input
              type="file"
              onChange={(e) => void pickFile(e)}
              data-testid="campus-library-import"
            />
          </label>
        </div>
      </div>

      {loading ? (
        <div className="stack-gap" data-testid="campus-library-loading">
          <div className="sk" />
          <div className="sk" style={{ width: "74%" }} />
          <span className="body-text">{t("campus.common.loading")}</span>
        </div>
      ) : null}

      {error ? (
        <div className="alert" data-testid="campus-library-error">
          <Icon name="warning" size={14} />
          <div className="alert-text">
            <span className="alert-title">
              {t(campusErrorKey(campusErrorInfo(error).code), {
                defaultValue: campusErrorInfo(error).message || t("campus.common.error"),
              })}
            </span>
          </div>
          {retryable ? (
            <button type="button" className="btn btn--ghost btn--sm" onClick={reload}>
              {t("campus.common.retry")}
            </button>
          ) : null}
        </div>
      ) : null}

      {!loading && items.length === 0 ? (
        <div className="empty" data-testid="campus-library-empty">
          <span className="ib ib--brand">
            <Icon name="file" size={17} />
          </span>
          <span className="empty-title">{t("campus.library.empty")}</span>
        </div>
      ) : null}

      {items.length > 0 ? (
        <>
          <div className="rows fill thin">
            {items.map((doc) => (
              <div
                key={doc.id}
                className="lrow"
                data-testid="campus-library-row"
                data-id={doc.id}
                data-parse-status={doc.parse_status}
                data-selected={selectedDocId === doc.id ? "true" : "false"}
              >
                <div className="lrow-text">
                  <button
                    type="button"
                    className="lrow-title"
                    onClick={() => onSelectDoc?.(doc.id)}
                    data-testid="campus-library-title"
                  >
                    {doc.title}
                  </button>
                  <span className="lrow-meta">
                    {doc.file_type} · {doc.page_count} · {doc.imported_at.slice(0, 10)}
                  </span>
                </div>
                <div className="parse">
                  {doc.parse_status === "pending" ? (
                    <>
                      <span className="parse-k" data-testid="campus-library-status">
                        {t(STATUS_KEYS.pending)}
                      </span>
                      <span className="parse-bar" />
                    </>
                  ) : (
                    <span className="parse-k">
                      <span
                        className={
                          doc.parse_status === "ready" ? "tag tag--ok" : "tag tag--danger"
                        }
                        data-testid="campus-library-status"
                      >
                        {doc.parse_status === "ready" ? <Icon name="check" size={11} /> : null}
                        {t(STATUS_KEYS[doc.parse_status])}
                      </span>
                    </span>
                  )}
                  {doc.parse_status === "failed" && doc.fail_reason ? (
                    <span className="parse-k">{doc.fail_reason}</span>
                  ) : null}
                </div>
                <div className="doc-acts">
                  {doc.parse_status === "ready" && onSelectDoc ? (
                    <button
                      type="button"
                      className="btn btn--text btn--sm"
                      onClick={() => onSelectDoc(doc.id)}
                      data-testid="campus-library-cite"
                    >
                      {t("campus.library.ask")}
                    </button>
                  ) : null}
                  {doc.parse_status === "failed" ? (
                    <button
                      type="button"
                      className="btn btn--ghost btn--sm"
                      onClick={() => void retry(doc.id)}
                      data-testid="campus-library-retry"
                    >
                      <Icon name="refresh" size={12} />
                      {t("campus.library.retry")}
                    </button>
                  ) : null}
                  <button
                    type="button"
                    className="btn btn--text btn--sm"
                    onClick={() => void remove(doc.id)}
                    data-testid="campus-library-delete"
                  >
                    <Icon name="trash" size={12} />
                    {t("campus.library.delete")}
                  </button>
                </div>
              </div>
            ))}
          </div>
          <div className="mod-foot">
            <span className="ai-note">
              <Icon name="warning" size={12} />
              {t("campus.library.local_note")}
            </span>
          </div>
        </>
      ) : null}
    </section>
  );
}
