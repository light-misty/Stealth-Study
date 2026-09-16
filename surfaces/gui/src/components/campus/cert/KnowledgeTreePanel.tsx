import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useKnowledgeTree, useMasteryCoverage } from "../../../campus/hooks";
import { MASTERY_LEVELS, type KnowledgePointNode, type MasteryLevel } from "../../../campus/types";
import { campusErrorInfo, campusErrorKey } from "../../../campus/utils";
import { MasteryDots } from "../MasteryDots";

interface TreeRow {
  node: KnowledgePointNode;
  depth: number;
}

const flatten = (
  nodes: KnowledgePointNode[],
  depth: number,
  collapsed: Set<string>,
  out: TreeRow[],
): TreeRow[] => {
  for (const node of nodes) {
    out.push({ node, depth });
    if (node.children.length > 0 && !collapsed.has(node.id)) {
      flatten(node.children, depth + 1, collapsed, out);
    }
  }
  return out;
};

export function KnowledgeTreePanel({ profileId }: { profileId: string }) {
  const { t } = useTranslation();
  const tree = useKnowledgeTree(profileId);
  const coverage = useMasteryCoverage(profileId);
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const [levels, setLevels] = useState<Record<string, MasteryLevel>>({});
  const localRef = useRef<Set<string>>(new Set());
  const [adding, setAdding] = useState<{ parentId: string | null } | null>(null);
  const [title, setTitle] = useState("");
  const [addBusy, setAddBusy] = useState(false);
  const [levelBusy, setLevelBusy] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);

  useEffect(() => {
    const pending = (coverage.data?.weak_top5 ?? []).filter(
      (w) => !localRef.current.has(w.point_id) && levels[w.point_id] !== w.level,
    );
    if (pending.length > 0) {
      setLevels((prev) => {
        const next = { ...prev };
        for (const w of pending) next[w.point_id] = w.level;
        return next;
      });
    }
  }, [coverage.data]);

  const rows = flatten(tree.roots, 1, collapsed, []);

  const toggle = (id: string) => {
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  const markLevel = async (pointId: string, level: MasteryLevel) => {
    if (levelBusy) return;
    setLevelBusy(pointId);
    const mastery = await tree.setLevel(pointId, level);
    setLevelBusy(null);
    if (mastery) {
      localRef.current.add(pointId);
      setLevels((prev) => ({ ...prev, [pointId]: mastery.level }));
      coverage.reload();
    }
  };

  const openAdd = (parentId: string | null) => {
    setFormError(null);
    setTitle("");
    setAdding({ parentId });
  };

  const submitAdd = async () => {
    if (addBusy || !adding) return;
    const trimmed = title.trim();
    if (!trimmed) {
      setFormError("campus.cert.tree.title_required");
      return;
    }
    setAddBusy(true);
    const created = await tree.addPoint({ title: trimmed, parentId: adding.parentId });
    setAddBusy(false);
    if (created) {
      setAdding(null);
      setTitle("");
    }
  };

  const info = tree.error ? campusErrorInfo(tree.error) : null;
  const message = formError
    ? t(formError)
    : info
      ? t(campusErrorKey(info.code), { defaultValue: info.message || t("campus.common.error") })
      : null;

  const addForm = adding ? (
    <div className="mt-2 flex items-center gap-2">
      <input
        className="min-w-0 flex-1 rounded-lg border border-line bg-panel px-2 py-1 text-[12px] text-ink"
        value={title}
        placeholder={t("campus.cert.tree.title_label")}
        onChange={(e) => {
          setTitle(e.target.value);
          setFormError(null);
        }}
        data-testid="campus-cert-tree-add-title"
      />
      <button
        type="button"
        className="shrink-0 rounded-lg border border-accent px-2 py-1 text-[12px] text-accent disabled:opacity-50"
        disabled={addBusy}
        onClick={() => void submitAdd()}
        data-testid="campus-cert-tree-add-submit"
      >
        {t("campus.cert.tree.submit")}
      </button>
      <button
        type="button"
        className="shrink-0 rounded-lg border border-line px-2 py-1 text-[12px] text-muted"
        onClick={() => setAdding(null)}
        data-testid="campus-cert-tree-add-cancel"
      >
        {t("campus.cert.tree.cancel")}
      </button>
    </div>
  ) : null;

  return (
    <div className="rounded-xl2 border border-line bg-panel" data-testid="campus-cert-tree-panel">
      <div className="flex items-center justify-between px-4 pt-3.5">
        <div className="text-[13px] font-semibold text-ink">{t("campus.cert.tree.title")}</div>
        {coverage.data ? (
          <div
            className="text-[11px] text-faint"
            data-testid="campus-cert-tree-coverage"
            data-coverage={coverage.data.coverage}
          >
            {t("campus.cert.tree.coverage")} {Math.round(coverage.data.coverage * 100)}%
          </div>
        ) : null}
      </div>

      {tree.loading ? (
        <div className="px-4 py-3 text-[12px] text-faint" data-testid="campus-cert-tree-loading">
          {t("campus.common.loading")}
        </div>
      ) : null}

      {message ? (
        <div
          className="flex items-center gap-2 px-4 py-2 text-[12px] text-warnInk"
          data-testid="campus-cert-tree-error"
        >
          <span className="min-w-0 truncate">{message}</span>
          {tree.retryable ? (
            <button
              type="button"
              className="shrink-0 rounded-lg border border-line px-2 py-0.5 text-[11px] text-muted"
              onClick={() => tree.reload()}
              data-testid="campus-cert-tree-retry"
            >
              {t("campus.common.retry")}
            </button>
          ) : null}
        </div>
      ) : null}

      {!tree.loading && tree.roots.length === 0 && !info ? (
        <div className="px-4 py-3">
          <div className="text-[12px] text-faint" data-testid="campus-cert-tree-empty">
            {t("campus.cert.tree.empty")}
          </div>
          <button
            type="button"
            className="mt-2 rounded-lg border border-line px-2.5 py-1 text-[12px] text-accent"
            onClick={() => openAdd(null)}
            data-testid="campus-cert-tree-add-root"
          >
            {t("campus.cert.tree.add_root")}
          </button>
          {adding?.parentId === null ? addForm : null}
        </div>
      ) : null}

      {tree.roots.length > 0 ? (
        <ul className="mt-2 grid gap-1 px-2 pb-2">
          {rows.map(({ node, depth }) => (
            <li
              key={node.id}
              className="rounded-lg border border-line px-2 py-1.5"
              style={{ marginLeft: (depth - 1) * 16 }}
              data-testid="campus-cert-tree-node"
              data-id={node.id}
              data-depth={depth}
              data-questions={node.question_count}
              data-mistakes={node.mistake_count}
            >
              <div className="flex items-center gap-2">
                {node.children.length > 0 ? (
                  <button
                    type="button"
                    className="h-5 w-5 shrink-0 rounded border border-line text-[10px] leading-none text-muted"
                    onClick={() => toggle(node.id)}
                    data-testid="campus-cert-tree-toggle"
                  >
                    {collapsed.has(node.id) ? "+" : "-"}
                  </button>
                ) : null}
                <span className="min-w-0 flex-1 truncate text-[12px] text-ink">{node.title}</span>
                <span className="shrink-0 text-[11px] text-faint">
                  {t("campus.cert.tree.stats", {
                    questions: node.question_count,
                    mistakes: node.mistake_count,
                  })}
                </span>
                {depth < 3 ? (
                  <button
                    type="button"
                    className="shrink-0 rounded-lg border border-line px-2 py-0.5 text-[11px] text-muted"
                    onClick={() => openAdd(node.id)}
                    data-testid="campus-cert-tree-add"
                  >
                    {t("campus.cert.tree.add_child")}
                  </button>
                ) : null}
                <button
                  type="button"
                  className="shrink-0 rounded-lg border border-line px-2 py-0.5 text-[11px] text-danger"
                  onClick={() => void tree.removePoint(node.id)}
                  data-testid="campus-cert-tree-delete"
                >
                  {t("campus.cert.tree.delete")}
                </button>
              </div>
              {adding?.parentId === node.id ? addForm : null}
              <div className="mt-1.5 flex items-center gap-2">
                {levels[node.id] ? <MasteryDots level={levels[node.id]} size="sm" /> : null}
                <div className="flex items-center gap-1">
                  {MASTERY_LEVELS.map((level) => (
                    <button
                      key={level}
                      type="button"
                      disabled={levelBusy !== null}
                      className={`rounded-lg border px-1.5 py-0.5 text-[11px] disabled:opacity-50 ${
                        levels[node.id] === level
                          ? "border-accent text-accent"
                          : "border-line text-muted"
                      }`}
                      onClick={() => void markLevel(node.id, level)}
                      data-testid={`campus-cert-tree-level-${level}`}
                    >
                      {t(`campus.common.mastery.${level}`)}
                    </button>
                  ))}
                </div>
              </div>
            </li>
          ))}
        </ul>
      ) : null}

      {coverage.data ? (
        <div className="px-4 pb-3.5">
          <div className="text-[11px] font-semibold text-muted">
            {t("campus.cert.tree.weak_top5")}
          </div>
          {coverage.data.weak_top5.length === 0 ? (
            <div className="mt-1 text-[11px] text-faint">{t("campus.cert.tree.weak_empty")}</div>
          ) : (
            <ul className="mt-1 grid gap-1">
              {coverage.data.weak_top5.map((w) => (
                <li
                  key={w.point_id}
                  className="flex items-center justify-between gap-2 rounded-lg border border-line px-2 py-1"
                  data-testid="campus-cert-tree-weak-row"
                >
                  <span className="min-w-0 truncate text-[12px] text-ink">{w.title}</span>
                  <MasteryDots level={w.level} size="sm" />
                </li>
              ))}
            </ul>
          )}
        </div>
      ) : null}
    </div>
  );
}
