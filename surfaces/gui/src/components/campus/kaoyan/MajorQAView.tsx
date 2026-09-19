import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useLibraryDocs, useLibraryQA } from "../../../campus/hooks";
import { campusErrorInfo, campusErrorKey } from "../../../campus/utils";
import { Icon } from "../../Icon";

// Major-station library Q&A (KY-09). Replaces the shared QAChatPanel in the kaoyan slot:
// it adds the profile document picker and keeps the same campus-qa-* / campus-citation
// testids so the e2e suite drives both panels the same way.
// 一次一问：真实实现没有会话列表，所以这里不画一个假的历史对话流。

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
    <section className="mod" data-testid="campus-major-qa-view">
      <div className="mod-head">
        <span className="ib ib--brand">
          <Icon name="chat" size={16} />
        </span>
        <div className="mod-head-text">
          <span className="mod-title">{t("campus.kaoyan.major_qa.title")}</span>
          <span className="mod-desc">{t("campus.kaoyan.major_qa.hint")}</span>
        </div>
        <div className="mod-acts">
          <div className="sel sel--sm">
            <select
              aria-label={t("campus.kaoyan.major_qa.doc_aria")}
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
            <Icon name="chevronDown" size={13} className="sel-chev" />
          </div>
        </div>
      </div>

      <div className="stack">
        <div className="qa-ask">
          <input
            className="input"
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
            className="btn btn--primary"
            onClick={send}
            disabled={asking}
            data-testid="campus-qa-send"
          >
            {asking ? t("campus.library.asking") : t("campus.library.ask")}
          </button>
        </div>

        <div className="fill thin qcol">
          {error ? (
            <div className="alert" data-testid="campus-qa-error">
              <Icon name="warning" size={14} />
              <div className="alert-text">
                <span className="alert-title">
                  {t(campusErrorKey(campusErrorInfo(error).code), {
                    defaultValue: campusErrorInfo(error).message || t("campus.common.error"),
                  })}
                </span>
              </div>
            </div>
          ) : null}

          {asking ? (
            <div className="stack-gap" data-testid="campus-qa-asking">
              <div className="sk" />
              <div className="sk" style={{ width: "82%" }} />
              <div className="sk" style={{ width: "54%" }} />
            </div>
          ) : null}

          {answer ? (
            <div className="sub sub--ring qa-ans">
              <span className="qa-ans-k">
                <Icon name="sparkle" size={12} />
                {t("campus.kaoyan.major_qa.answer_kicker")}
              </span>
              <p className="qa-body" data-testid="campus-qa-answer">
                {answer.answer}
              </p>
              {answer.citations.length > 0 ? (
                <div className="cites">
                  {answer.citations.map((cite, index) => (
                    <button
                      key={`${cite.doc_id}-${cite.page_no}-${index}`}
                      type="button"
                      className="cite"
                      onClick={() => onCite?.(cite.doc_id, cite.page_no)}
                      data-testid="campus-citation"
                      data-doc-id={cite.doc_id}
                      data-page-no={cite.page_no}
                    >
                      <Icon name="file" size={11} />
                      {t("campus.library.citation")}
                      <span className="num">P.{cite.page_no}</span>
                    </button>
                  ))}
                </div>
              ) : null}
              <span className="ai-note" data-testid="campus-qa-notice">
                <Icon name="sparkle" size={12} />
                {t("campus.common.ai_notice")}
              </span>
            </div>
          ) : null}
        </div>
      </div>
    </section>
  );
}
