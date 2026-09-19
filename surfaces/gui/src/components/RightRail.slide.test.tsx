import { render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { RightRail } from "./RightRail";

vi.mock("../api", async () => {
  const actual: any = await vi.importActual("../api");
  return {
    ...actual,
    getArtifacts: vi.fn().mockResolvedValue([]),
    getRoots: vi.fn().mockResolvedValue([]),
    getJournalCases: vi.fn().mockResolvedValue([]),
    readArtifact: vi.fn().mockResolvedValue({ ok: true, path: "r.md", kind: "markdown", content: "x" }),
    revealArtifact: vi.fn().mockResolvedValue({ ok: true }),
  };
});

function rail(active: boolean) {
  return (
    <RightRail
      active={active}
      sessionId="s1"
      refreshKey={0}
      toolNames={[]}
      todo={[]}
      running={false}
    />
  );
}

describe("RightRail slide shell", () => {
  it("stays mounted when hidden and toggles the rail-off marker", () => {
    const { container, rerender } = render(rail(false));
    const shell = container.querySelector(".right-rail");
    expect(shell).toBeTruthy();
    expect(shell?.classList.contains("rail-off")).toBe(true);

    rerender(rail(true));
    expect(container.querySelector(".right-rail")?.classList.contains("rail-off")).toBe(false);

    rerender(rail(false));
    expect(container.querySelector(".right-rail")?.classList.contains("rail-off")).toBe(true);
  });
});
