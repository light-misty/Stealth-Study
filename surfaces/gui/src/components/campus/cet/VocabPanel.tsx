import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { listVocabToday, makeMnemonic, setVocabMastery } from "../../../campus/api";
import type { MasteryLevel, VocabItem } from "../../../campus/types";
import { campusErrorInfo, campusErrorKey } from "../../../campus/utils";

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
    <div
      key={item.id}
      className="rounded-xl2 border border-line bg-panel px-3 py-2.5"
      data-testid="campus-cet-vocab-item"
      data-word={item.word}
    >
      <div className="flex items-baseline gap-2">
        <span className="text-[13px] font-semibold text-ink">{item.word}</span>
        {item.phonetic ? <span className="text-[12px] text-faint">{item.phonetic}</span> : null}
      </div>
      <div className="mt-0.5 text-[12px] text-muted">{item.meaning}</div>
      {item.example ? <div className="mt-0.5 text-[12px] text-faint">{item.example}</div> : null}
      <div className="mt-2 flex flex-wrap items-center gap-1.5">
        {MASTERY_LEVELS.map((level) => (
          <button
            key={level}
            type="button"
            className={`rounded-lg2 border px-2 py-0.5 text-[11px] ${
              item.mastery === level
                ? "border-accent bg-accentSoft text-ink"
                : "border-line bg-panel text-muted"
            }`}
            data-testid="campus-cet-vocab-mastery"
            data-vocab={item.id}
            data-level={level}
            data-active={item.mastery === level ? "true" : "false"}
            onClick={() => markMastery(item.id, level)}
          >
            {t(MASTERY_KEY[level])}
          </button>
        ))}
        <button
          type="button"
          className="ml-auto rounded-lg2 border border-line bg-panel px-2 py-0.5 text-[11px] text-muted disabled:opacity-50"
          data-testid="campus-cet-vocab-mnemonic"
          data-vocab={item.id}
          disabled={mnemonicBusy === item.id}
          onClick={() => requestMnemonic(item.id)}
        >
          {mnemonicBusy === item.id
            ? t("campus.cet.vocab.mnemonic_busy")
            : t("campus.cet.vocab.mnemonic")}
        </button>
      </div>
      {markError === item.id ? (
        <div
          className="mt-1 text-[12px] text-warnInk"
          data-testid="campus-cet-vocab-mastery-error"
        >
          {t("campus.cet.vocab.mastery_error")}
        </div>
      ) : null}
      {mnemonicError === item.id ? (
        <div
          className="mt-1 text-[12px] text-warnInk"
          data-testid="campus-cet-vocab-mnemonic-error"
        >
          {t("campus.cet.vocab.mnemonic_error")}
        </div>
      ) : null}
      {mnemonics[item.id] ? (
        <div
          className="mt-1.5 rounded-lg2 border border-line bg-panel px-2.5 py-1.5 text-[12px] text-ink"
          data-testid="campus-cet-vocab-mnemonic-text"
          data-vocab={item.id}
        >
          {mnemonics[item.id]}
        </div>
      ) : null}
    </div>
  );

  if (error) {
    return (
      <div
        className="rounded-xl2 border border-warnInk/40 bg-warnSoft px-4 py-3 text-[13px] text-warnInk"
        data-testid="campus-cet-vocab-error"
      >
        {t(campusErrorKey(campusErrorInfo(error).code), {
          defaultValue: campusErrorInfo(error).message || t("campus.common.error"),
        })}
        <button
          type="button"
          className="ml-2 text-accent"
          onClick={() => setNonce((n) => n + 1)}
          data-testid="campus-cet-vocab-retry"
        >
          {t("campus.common.retry")}
        </button>
      </div>
    );
  }

  const isEmpty =
    !loading && data.new_items.length === 0 && data.review_items.length === 0;

  return (
    <div className="grid gap-3" data-testid="campus-cet-vocab">
      {isEmpty ? (
        <div
          className="rounded-xl2 border border-line bg-panel px-4 py-3.5 text-[12px] text-faint"
          data-testid="campus-cet-vocab-empty"
        >
          {t("campus.cet.vocab.empty")}
        </div>
      ) : (
        <>
          <section className="grid gap-2" data-testid="campus-cet-vocab-section-new">
            <div className="text-[13px] font-semibold text-ink">
              {t("campus.cet.vocab.today_new")}
            </div>
            {loading ? null : data.new_items.map(renderItem)}
          </section>
          <section className="grid gap-2" data-testid="campus-cet-vocab-section-review">
            <div className="text-[13px] font-semibold text-ink">
              {t("campus.cet.vocab.today_review")}
            </div>
            {loading ? null : data.review_items.map(renderItem)}
          </section>
        </>
      )}
    </div>
  );
}
