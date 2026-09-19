import type { Item } from "./types";

export const INTERRUPTED = "interrupted";

export function pendingQuestionOf(items: Item[]): Item | undefined {
  return [...items].reverse().find((i) => i.kind === "question" && !i.resolved);
}

export function dismissPendingQuestion(items: Item[]): Item[] {
  for (let i = items.length - 1; i >= 0; i--) {
    const it = items[i];
    if (it.kind === "question" && !it.resolved) {
      const copy = [...items];
      copy[i] = { ...it, resolved: INTERRUPTED };
      return copy;
    }
  }
  return items;
}
