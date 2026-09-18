import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useKnowledgeTree, useMasteryCoverage } from "../../../campus/hooks";
import { MASTERY_LEVELS, type KnowledgePointNode, type MasteryLevel } from "../../../campus/types";
import { campusErrorInfo, campusErrorKey } from "../../../campus/utils";
import { Icon } from "../../Icon";
import { MasteryDots } from "../MasteryDots";

// 证书台的主语是一棵树：掌握度挂在节点上，覆盖率是这棵树被点亮的比例。
// 三档掌握度压成一组三点 Picker，当前档旁边始终跟着文字（PRD §7.4）；
// 层级上限沿用真实实现的 depth < 3，第 3 层不再给一个点了没反应的「添加子节点」。

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
    <div className="addrow" style={{ "--d": adding.parentId ? 2 : 1 } as Record<string, number>}>
      <input
        className="input"
        value={title}
        placeholder={t("campus.cert.tree.title_label")}
        onChange={(e) => {
          setTitle(e.target.value);
          setFormError(null);
        }}
        onKeyDown={(e) => {
          if (e.key === "Enter") void submitAdd();
          if (e.key === "Escape") setAdding(null);
        }}
        data-testid="campus-cert-tree-add-title"
      />
      <button
        type="button"
        className="btn btn--primary btn--sm"
        disabled={addBusy}
        onClick={() => void submitAdd()}
        data-testid="campus-cert-tree-add-submit"
      >
        {t("campus.cert.tree.submit")}
      </button>
      <button
        type="button"
        className="btn btn--text btn--sm"
        onClick={() => setAdding(null)}
        data-testid="campus-cert-tree-add-cancel"
      >
        {t("campus.cert.tree.cancel")}
      </button>
    </div>
  ) : null;

  return (
    <section className="mod" data-testid="campus-cert-tree-panel">
      <div className="mod-head">
        <span className="ib ib--brand">
          <Icon name="tree" size={16} />
        </span>
        <div className="mod-head-text">
          <span className="mod-title">{t("campus.cert.tree.title")}</span>
          <span className="mod-desc">{t("campus.cert.tree.hint")}</span>
        </div>
        <div className="mod-acts">
          {coverage.data ? (
            <span
              className="sec-n"
              data-testid="campus-cert-tree-coverage"
              data-coverage={coverage.data.coverage}
            >
              {t("campus.cert.tree.coverage")} {Math.round(coverage.data.coverage * 100)}%
            </span>
          ) : null}
          <button
            type="button"
            className="btn btn--ghost btn--sm"
            onClick={() => openAdd(null)}
            data-testid="campus-cert-tree-add-root"
          >
            <Icon name="plus" size={12} />
            {t("campus.cert.tree.add_root")}
          </button>
        </div>
      </div>

      {tree.loading ? (
        <div className="stack-gap" data-testid="campus-cert-tree-loading">
          <div className="sk" style={{ width: 200 }} />
          <div className="sk" style={{ width: "78%" }} />
          <span className="body-text">{t("campus.common.loading")}</span>
        </div>
      ) : null}

      {message ? (
        <div className="alert" data-testid="campus-cert-tree-error">
          <Icon name="warning" size={14} />
          <div className="alert-text">
            <span className="alert-title">{message}</span>
          </div>
          {tree.retryable ? (
            <button
              type="button"
              className="btn btn--ghost btn--sm"
              onClick={() => tree.reload()}
              data-testid="campus-cert-tree-retry"
            >
              {t("campus.common.retry")}
            </button>
          ) : null}
        </div>
      ) : null}

      {!tree.loading && tree.roots.length === 0 && !info ? (
        <div className="empty" data-testid="campus-cert-tree-empty">
          <span className="ib ib--brand">
            <Icon name="tree" size={17} />
          </span>
          <span className="empty-title">{t("campus.cert.tree.empty")}</span>
        </div>
      ) : null}

      {adding?.parentId === null && tree.roots.length === 0 ? addForm : null}

      {tree.roots.length > 0 ? (
        <div className="fill thin tree">
          {rows.map(({ node, depth }) => (
            <div key={node.id}>
              <div
                className={depth === 1 ? "tnode tnode--root" : "tnode"}
                style={{ "--d": depth } as Record<string, number>}
                data-testid="campus-cert-tree-node"
                data-id={node.id}
                data-depth={depth}
                data-questions={node.question_count}
                data-mistakes={node.mistake_count}
              >
                {node.children.length > 0 ? (
                  <button
                    type="button"
                    className="tnode-tw"
                    aria-label={collapsed.has(node.id) ? t("campus.cert.tree.expand") : t("campus.cert.tree.collapse")}
                    aria-expanded={!collapsed.has(node.id)}
                    onClick={() => toggle(node.id)}
                    data-testid="campus-cert-tree-toggle"
                  >
                    <Icon name={collapsed.has(node.id) ? "plus" : "minus"} size={11} />
                  </button>
                ) : (
                  <span className="tnode-tw tnode-tw--leaf" />
                )}
                <span className="tnode-t">{node.title}</span>
                <span className="tnode-s">
                  {t("campus.cert.tree.stats", {
                    questions: node.question_count,
                    mistakes: node.mistake_count,
                  })}
                </span>
                <div className="lvls">
                  {MASTERY_LEVELS.map((level) => (
                    <button
                      key={level}
                      type="button"
                      disabled={levelBusy !== null}
                      className={levels[node.id] === level ? "lvl is-on" : "lvl"}
                      aria-label={t(`campus.common.mastery.${level}`)}
                      onClick={() => void markLevel(node.id, level)}
                      data-testid={`campus-cert-tree-level-${level}`}
                    >
                      <span
                        className={
                          levels[node.id] === level
                            ? `mas-dot mas-dot--${level} is-on`
                            : `mas-dot mas-dot--${level}`
                        }
                      />
                    </button>
                  ))}
                </div>
                <span
                  className={`lvl-l lvl-l--${levels[node.id] ?? "unknown"}`}
                  data-testid="campus-cert-tree-level-label"
                >
                  {levels[node.id] ? t(`campus.common.mastery.${levels[node.id]}`) : "—"}
                </span>
                <div className="tnode-acts">
                  {depth < 3 ? (
                    <button
                      type="button"
                      className="btn btn--text btn--sm"
                      onClick={() => openAdd(node.id)}
                      data-testid="campus-cert-tree-add"
                    >
                      {t("campus.cert.tree.add_child")}
                    </button>
                  ) : null}
                  <button
                    type="button"
                    className="btn btn--text btn--sm"
                    onClick={() => void tree.removePoint(node.id)}
                    data-testid="campus-cert-tree-delete"
                  >
                    <Icon name="trash" size={12} />
                    {t("campus.cert.tree.delete")}
                  </button>
                </div>
              </div>
              {adding?.parentId === node.id ? addForm : null}
            </div>
          ))}
        </div>
      ) : null}

      {adding?.parentId === null && tree.roots.length > 0 ? addForm : null}

      {coverage.data ? (
        <div className="sub">
          <div className="sec">
            <div className="sec-text">
              <span className="sec-title">{t("campus.cert.tree.weak_top5")}</span>
            </div>
            <span className="sec-n">{coverage.data.weak_top5.length}</span>
          </div>
          {coverage.data.weak_top5.length === 0 ? (
            <div className="body-text">{t("campus.cert.tree.weak_empty")}</div>
          ) : (
            <div className="weak">
              {coverage.data.weak_top5.map((w) => (
                <div className="weak-row" key={w.point_id} data-testid="campus-cert-tree-weak-row">
                  <span className="weak-t">{w.title}</span>
                  <MasteryDots level={w.level} size="sm" />
                </div>
              ))}
            </div>
          )}
        </div>
      ) : null}
    </section>
  );
}
