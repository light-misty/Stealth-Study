import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { GradeResult } from "../../campus/types";
import { GradingResultCard } from "./GradingResultCard";

afterEach(cleanup);

const result = (overrides: Partial<GradeResult> = {}): GradeResult => ({
  attempt_id: "a1",
  degrade_level: 0,
  rubric: "cet_writing",
  dimensions: [
    { name: "内容", score: 8, max: 15, comment: "论点清楚" },
    { name: "语言", score: 6, max: 10, comment: "有语法错误" },
  ],
  errors: [
    { original: "He go to school", suggestion: "He goes to school", type: "grammar", offset: 12 },
    { original: "very important", suggestion: "crucial", type: "word_choice", offset: null },
  ],
  model_answer_outline: "范文三段式",
  model_used: "gpt-4o-mini",
  notice: null,
  ...overrides,
});

describe("GradingResultCard", () => {
  it("renders every dimension and every error", () => {
    render(<GradingResultCard result={result()} />);
    const dims = screen.getAllByTestId("campus-grading-dimension");
    expect(dims.map((d) => d.getAttribute("data-name"))).toEqual(["内容", "语言"]);
    expect(dims[0].textContent).toContain("8/15");

    const errors = screen.getAllByTestId("campus-grading-error");
    expect(errors).toHaveLength(2);
    expect(errors[0].textContent).toContain("He go to school");
    expect(screen.getByTestId("campus-grading-outline").textContent).toContain("范文三段式");
  });

  it("always renders the degrade notice when the result was degraded", () => {
    render(<GradingResultCard result={result({ degrade_level: 1 })} />);
    expect(screen.getByTestId("campus-degrade-badge").getAttribute("data-degrade-level")).toBe("1");
  });

  it("passes the backend notice through to the badge", () => {
    render(<GradingResultCard result={result({ degrade_level: 2, notice: "两次解析失败" })} />);
    expect(screen.getByTestId("campus-degrade-notice-detail").textContent).toContain("两次解析失败");
  });

  it("locates an error in the original text only when an offset exists", () => {
    const onLocate = vi.fn();
    render(<GradingResultCard result={result()} onLocate={onLocate} />);
    const buttons = screen.getAllByTestId("campus-grading-locate");
    // The second error carries offset = null → no locate affordance for it.
    expect(buttons).toHaveLength(1);
    fireEvent.click(buttons[0]);
    expect(onLocate).toHaveBeenCalledWith(12);
  });

  it("offers adding the attempt to the mistake book when wired up", () => {
    const onAddToMistake = vi.fn();
    render(<GradingResultCard result={result()} onAddToMistake={onAddToMistake} />);
    fireEvent.click(screen.getByTestId("campus-grading-to-mistake"));
    expect(onAddToMistake).toHaveBeenCalled();
  });

  it("hides the mistake action when no handler is supplied", () => {
    render(<GradingResultCard result={result()} />);
    expect(screen.queryByTestId("campus-grading-to-mistake")).toBeNull();
  });

  it("says so plainly when nothing was flagged", () => {
    render(<GradingResultCard result={result({ errors: [] })} />);
    expect(screen.queryByTestId("campus-grading-error")).toBeNull();
    expect(screen.getByTestId("campus-grading-no-errors")).toBeTruthy();
  });

  it("names the model that graded and carries the AI disclaimer", () => {
    render(<GradingResultCard result={result()} />);
    expect(screen.getByTestId("campus-grading-model").textContent).toContain("gpt-4o-mini");
    expect(screen.getByTestId("campus-grading-ai-notice").textContent).toBe(
      "AI generated, for reference only",
    );
  });
});
