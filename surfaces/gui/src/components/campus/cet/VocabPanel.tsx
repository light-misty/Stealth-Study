import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { listVocabToday, makeMnemonic, setVocabMastery } from "../../../campus/api";
import type { MasteryLevel, VocabItem } from "../../../campus/types";
import { campusErrorInfo } from "../../../campus/utils";
import { Icon } from "../../Icon";

const MASTERY_LEVELS: MasteryLevel[] = ["unknown", "fuzzy", "mastered"];

const MASTERY_KEY: Record<MasteryLevel, string> = {
  unknown: "campus.cet.vocab.mastery_unknown",
  fuzzy: "campus.cet.vocab.mastery_fuzzy",
  mastered: "campus.cet.vocab.mastery_mastered",
};

interface VocabState {
  new_items: VocabItem[];
  review_items: VocabItem[];
}

function patchLocal(
  items: VocabState,
  vocabId: string,
  fn: (it: VocabItem) => VocabItem,
): VocabState {
  const map = (list: VocabItem[]) => list.map((it) => (it.id === vocabId ? fn(it) : it));
  return { new_items: map(items.new_items), review_items: map(items.review_items) };
}

function replaceItem(items: VocabState, updated: VocabItem): VocabState {
  return patchLocal(items, updated.id, () => updated);
}

function findItem(items: VocabState, vocabId: string): VocabItem | null {
  return (
    items.new_items.find((it) => it.id === vocabId) ??
    items.review_items.find((it) => it.id === vocabId) ??
    null
  );
}

export function VocabPanel({ profileId }: { profileId: string }) {
  const { t } = useTranslation();
  const [data, setData] = useState<VocabState>({ new_items: [], review_items: [] });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const [markError, setMarkError] = useState<string | null>(null);
  const [mnemonics, setMnemonics] = useState<Record<string, string>>({});
  const [mnemonicBusy, setMnemonicBusy] = useState<string | null>(null);
  const [mnemonicError, setMnemonicError] = useState<string | null>(null);
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    if (!profileId) {
      setLoading(false);
      return;
    }
    let alive = true;
    setLoading(true);
    listVocabToday(profileId).then(
      (res) => {
        if (!alive) return;
        setData({ new_items: res?.new_items ?? [], review_items: res?.review_items ?? [] });
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
  }, [profileId, nonce]);

  const markMastery = (vocabId: string, level: MasteryLevel) => {
    const current = findItem(data, vocabId);
    if (!current || current.mastery === level) return;
    const previous = current.mastery;
    setMarkError(null);
    setData((cur) => patchLocal(cur, vocabId, (it) => ({ ...it, mastery: level })));
    setVocabMastery(vocabId, profileId, level).then(
      (updated) => setData((cur) => replaceItem(cur, updated)),
      () => {
        setData((cur) => patchLocal(cur, vocabId, (it) => ({ ...it, mastery: previous })));
        setMarkError(vocabId);
      },
    );
  };

  const requestMnemonic = (vocabId: string) => {
    if (mnemonicBusy) return;
    setMnemonicError(null);
    setMnemonicBusy(vocabId);
    makeMnemonic(profileId, vocabId).then(
      (res) => {
        setMnemonics((cur) => ({ ...cur, [vocabId]: res.mnemonic }));
        setMnemonicBusy(null);
      },
      () => {
        setMnemonicError(vocabId);
        setMnemonicBusy(null);
      },
    );
  };

  const renderItem = (item: VocabItem) => (
    <div className="sub word" key={item.id} data-testid="campus-cet-vocab-item" data-word={item.word}>
      <div className="word-h">
        <span className="word-t">{item.word}</span>
        {item.phonetic ? <span className="word-p">{item.phonetic}</span> : null}
      </div>
      <p className="word-m">{item.meaning}</p>
      {item.example ? <p className="word-x">{item.example}</p> : null}
      <div className="word-foot">
        <div className="picks">
          {MASTERY_LEVELS.map((level) => (
            <button
              key={level}
              type="button"
              className={item.mastery === level ? "pick is-on" : "pick"}
              data-testid="campus-cet-vocab-mastery"
              data-vocab={item.id}
              data-level={level}
              data-active={item.mastery === level ? "true" : "false"}
              onClick={() => markMastery(item.id, level)}
            >
              <span
                className={
                  item.mastery === level ? `mas-dot mas-dot--${level} is-on` : `mas-dot mas-dot--${level}`
                }
              />
              {t(MASTERY_KEY[level])}
            </button>
          ))}
        </div>
        <span className="st-spacer" />
        <button
          type="button"
          className="btn btn--ghost btn--sm"
          data-testid="campus-cet-vocab-mnemonic"
          data-vocab={item.id}
          disabled={mnemonicBusy === item.id}
          onClick={() => requestMnemonic(item.id)}
        >
          <Icon name="sparkle" size={12} />
          {mnemonicBusy === item.id
            ? t("campus.cet.vocab.mnemonic_busy")
            : t("campus.cet.vocab.mnemonic")}
        </button>
      </div>
      {markError === item.id ? (
        <span className="field-err" data-testid="campus-cet-vocab-mastery-error">
          {t("campus.cet.vocab.mastery_error")}
        </span>
      ) : null}
      {mnemonicError === item.id ? (
        <span className="field-err" data-testid="campus-cet-vocab-mnemonic-error">
          {t("campus.cet.vocab.mnemonic_error")}
        </span>
      ) : null}
      {mnemonics[item.id] ? (
        <div className="mnemonic" data-testid="campus-cet-vocab-mnemonic-text" data-vocab={item.id}>
          <Icon name="sparkle" size={14} />
          <div className="mnemonic-text">
            <span className="mnemonic-k">{t("campus.cet.vocab.mnemonic")}</span>
            <span>{mnemonics[item.id]}</span>
          </div>
        </div>
      ) : null}
    </div>
  );

  const renderSection = (
    testId: string,
    label: string,
    items: VocabItem[],
  ) =>
    items.length === 0 ? null : (
      <section className="qcol" data-testid={testId}>
        <div className="sec">
          <div className="sec-text">
            <span className="sec-title">{label}</span>
          </div>
          <span className="sec-n">{items.length}</span>
        </div>
        {items.map(renderItem)}
      </section>
    );

  if (error) {
    return (
      <div className="alert" data-testid="campus-cet-vocab-error">
        <Icon name="warning" size={14} />
        <div className="alert-text">
          <span className="alert-title">{t("campus.common.error")}</span>
          <span className="alert-desc">{campusErrorInfo(error).message}</span>
        </div>
        <button
          type="button"
          className="btn btn--ghost btn--sm"
          onClick={() => setNonce((n) => n + 1)}
          data-testid="campus-cet-vocab-retry"
        >
          {t("campus.common.retry")}
        </button>
      </div>
    );
  }

  const isEmpty = !loading && data.new_items.length === 0 && data.review_items.length === 0;

  return (
    <section className="mod" data-testid="campus-cet-vocab">
      <div className="mod-head">
        <span className="ib ib--accent">
          <Icon name="book" size={16} />
        </span>
        <div className="mod-head-text">
          <span className="mod-title">{t("campus.cet.vocab.title")}</span>
          <span className="mod-desc">{t("campus.cet.vocab.hint")}</span>
        </div>
        <div className="mod-acts">
          {data.new_items.length + data.review_items.length > 0 ? (
            <span className="sec-n">
              {t("campus.cet.vocab.today_new")} {data.new_items.length} ·{" "}
              {t("campus.cet.vocab.today_review")} {data.review_items.length}
            </span>
          ) : null}
        </div>
      </div>

      {loading ? (
        <div className="stack-gap">
          <div className="sk" style={{ width: 160 }} />
          <div className="sk" />
          <div className="sk" style={{ width: "70%" }} />
        </div>
      ) : isEmpty ? (
        <div className="empty" data-testid="campus-cet-vocab-empty">
          <span className="ib ib--brand">
            <Icon name="book" size={17} />
          </span>
          <span className="empty-title">{t("campus.cet.vocab.empty")}</span>
        </div>
      ) : (
        <div className="fill thin qcol">
          {renderSection("campus-cet-vocab-section-new", t("campus.cet.vocab.today_new"), data.new_items)}
          {renderSection(
            "campus-cet-vocab-section-review",
            t("campus.cet.vocab.today_review"),
            data.review_items,
          )}
        </div>
      )}
    </section>
  );
}
