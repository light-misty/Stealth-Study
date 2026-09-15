import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useLibraryQA } from "../../campus/hooks";
import { campusErrorInfo, campusErrorKey } from "../../campus/utils";

// Library Q&A (B6). Answers always ship with page-level citations — a citation the user
// cannot open would leave them no way to check the claim (KY-03 hard acceptance).

export function QAChatPanel({
  profileId,
  docId,
  onCite,
}: {
  profileId: string;
  docId?: string;
  onCite?: (docId: string, pageNo: number) => void;
}) {
  const { t } = useTranslation();
  const { answer, asking, error, ask } = useLibraryQA(profileId, docId);
  const [question, setQuestion] = useState("");

  const send = () => {
    if (asking) return;
    void ask(question);
  };

  return (
    <div className="rounded-xl2 border border-line bg-panel" data-testid="campus-qa-panel">
      <div className="px-4 pt-3.5 text-[13px] font-semibold text-ink">
        {t("campus.library.ask")}
      </div>

      <div className="mt-2 flex items-center gap-2 px-4">
        <input
          className="flex-1 rounded-lg border border-line bg-transparent px-2.5 py-1.5 text-[13px] text-ink outline-none"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") send();
          }}
          placeholder={t("campus.library.ask_placeholder")}
          data-testid="campus-qa-input"
        />
        <button
          type="button"
          className="px-3 py-1.5 rounded-lg bg-accent text-white text-[13px] disabled:opacity-40"
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
                  className="px-2 py-1 rounded-lg text-[11px] text-accent border border-line"
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
