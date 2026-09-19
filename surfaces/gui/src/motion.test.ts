import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const css = readFileSync(resolve(process.cwd(), "src/styles.css"), "utf8");

describe("unified motion foundation", () => {
  it("defines shared motion tokens", () => {
    expect(css).toContain("--motion-fast:");
    expect(css).toContain("--motion-dur:");
    expect(css).toContain("--motion-ease:");
  });

  it("defines the shared keyframes", () => {
    expect(css).toContain("@keyframes ss-fade-in");
    expect(css).toContain("@keyframes ss-fade-up");
    expect(css).toContain("@keyframes ss-pop-in");
    expect(css).toContain("@keyframes ss-slide-down");
  });

  it("defines the shared transition utilities", () => {
    expect(css).toContain(".surface-view");
    expect(css).toContain(".anim-fade-up");
    expect(css).toContain(".overlay-fade");
    expect(css).toContain(".card-pop");
    expect(css).toContain(".toast-in");
  });

  it("disables motion globally under prefers-reduced-motion", () => {
    expect(css).toMatch(/animation-duration:\s*0\.01ms/);
    expect(css).toMatch(/animation-iteration-count:\s*1/);
    expect(css).toMatch(/transition-duration:\s*0\.01ms/);
  });
});
