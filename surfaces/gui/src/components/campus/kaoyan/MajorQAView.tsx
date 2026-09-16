import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useLibraryDocs, useLibraryQA } from "../../../campus/hooks";
import { campusErrorInfo, campusErrorKey } from "../../../campus/utils";

// Major-station library Q&A (KY-09). Replaces the shared QAChatPanel in the kaoyan slot:
// it adds the profile document picker and keeps the same campus-qa-* / campus-citation
// testids so the e2e suite drives both panels the same way.

export function MajorQAView({
  profileId,
  onCite,
}: {
  profileId: string;
  onCite?: (docId: string, pageNo: number) => void;
}) {
  const { t } = useTranslation();
  const docs = useLibraryDocs(profileId);
  const { answer, asking, error, ask } = useLibraryQA(profileId);
  const [docId, setDocId] = useState("");
  const [question, setQuestion] = useState("");

  const send = () => {
    if (asking) return;
    void ask(question, docId || undefined);
  };

  return (
    <div className="rounded-xl2 border border-line bg-panel" data-testid="campus-major-qa-view">
      <div className="px-4 pt-3.5 text-[13px] font-semibold text-ink">
        {t("campus.kaoyan.major_qa.title")}
      </div>

      <div className="mt-2 flex items-center gap-2 px-4">
        <select
          className="rounded-lg border border-line bg-panel px-2 py-1.5 text-[12px] text-ink"
          data-testid="campus-major-qa-doc"
          value={docId}
          onChange={(event) => setDocId(event.target.value)}
        >
          <option value="">{t("campus.kaoyan.major_qa.doc_all")}</option>
          {docs.items.map((item) => (
            <option key={item.id} value={item.id}>
              {item.title}
            </option>
          ))}
        </select>
      </div>

      <div className="mt-2 flex items-center gap-2 px-4">
        <input
          className="flex-1 rounded-lg border border-line bg-transparent px-2.5 py-1.5 text-[13px] text-ink outline-none"
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") send();
          }}
          placeholder={t("campus.library.ask_placeholder")}
          data-testid="campus-qa-input"
        />
        <button
          type="button"
          className="rounded-lg bg-accent px-3 py-1.5 text-[13px] text-white disabled:opacity-40"
          onClick={send}
          disabled={asking}
          data-testid="campus-qa-send"
        >
          {asking ? t("campus.library.asking") : t("campus.library.ask")}
        </button>
      </div>

      {error ? (
        <div className="px-4 py-2 text-[12px] text-warnInk" data-testid="campus-qa-error">
          {t(campusErrorKey(campusErrorInfo(error).code), {
            defaultValue: campusErrorInfo(error).message || t("campus.common.error"),
          })}
        </div>
      ) : null}

      {asking ? (
        <div className="px-4 py-2 text-[12px] text-faint" data-testid="campus-qa-asking">
          {t("campus.library.asking")}
        </div>
      ) : null}

      {answer ? (
        <div className="px-4 pb-3.5 pt-2">
          <div className="text-[13px] text-ink" data-testid="campus-qa-answer">
            {answer.answer}
          </div>
          {answer.citations.length > 0 ? (
            <div className="mt-2 flex flex-wrap gap-1.5">
              {answer.citations.map((cite, index) => (
                <button
                  key={`${cite.doc_id}-${cite.page_no}-${index}`}
                  type="button"
                  className="rounded-lg border border-line px-2 py-1 text-[11px] text-accent"
                  onClick={() => onCite?.(cite.doc_id, cite.page_no)}
                  data-testid="campus-citation"
                  data-doc-id={cite.doc_id}
                  data-page-no={cite.page_no}
                >
                  {t("campus.library.citation")} P{cite.page_no}
                </button>
              ))}
            </div>
          ) : null}
          <div className="mt-2 text-[11px] text-faint" data-testid="campus-qa-notice">
            {t("campus.common.ai_notice")}
          </div>
        </div>
      ) : null}
    </div>
  );
}
