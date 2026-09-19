import { describe, expect, it } from "vitest";
import { dismissPendingQuestion, INTERRUPTED, pendingQuestionOf } from "./pendingQuestion";
import type { Item } from "./types";

const question = (text: string, resolved?: string): Item => ({
  kind: "question",
  question: text,
  options: ["Red", "Blue"],
  allow_text: true,
  multi: false,
  header: "",
  questions: [],
  ...(resolved ? { resolved } : {}),
});

describe("pendingQuestionOf", () => {
  it("finds the last unresolved question item", () => {
    const items: Item[] = [
      { kind: "user", text: "hi" },
      question("Which color?"),
    ];
    const pending = pendingQuestionOf(items);
    expect(pending?.kind).toBe("question");
    expect((pending as Extract<Item, { kind: "question" }>).question).toBe("Which color?");
  });

  it("returns undefined when nothing is pending", () => {
    expect(pendingQuestionOf([])).toBeUndefined();
    expect(pendingQuestionOf([{ kind: "user", text: "hi" }])).toBeUndefined();
    expect(pendingQuestionOf([question("done?", "Red")])).toBeUndefined();
  });
});

describe("dismissPendingQuestion", () => {
  it("resolves the pending question as interrupted so the composer card hides", () => {
    const items: Item[] = [
      { kind: "user", text: "hi" },
      question("Which color?"),
    ];
    const next = dismissPendingQuestion(items);
    expect(pendingQuestionOf(next)).toBeUndefined();
    const marked = next.find((i) => i.kind === "question") as Extract<Item, { kind: "question" }>;
    expect(marked.resolved).toBe(INTERRUPTED);
    expect(items.find((i) => i.kind === "question")?.resolved).toBeUndefined();
  });

  it("is a no-op with no pending question — pausing mid-stream must not corrupt items", () => {
    const items: Item[] = [
      { kind: "user", text: "stream the epic" },
      { kind: "assistant", text: "The epic scrolls ever onward" },
    ];
    expect(dismissPendingQuestion(items)).toBe(items);
  });

  it("keeps earlier answered questions and clears only the latest pending one", () => {
    const items: Item[] = [
      question("First?", "Red"),
      question("Second?"),
    ];
    const next = dismissPendingQuestion(items);
    const qs = next.filter((i) => i.kind === "question") as Extract<Item, { kind: "question" }>[];
    expect(qs[0].resolved).toBe("Red");
    expect(qs[1].resolved).toBe(INTERRUPTED);
  });
});
