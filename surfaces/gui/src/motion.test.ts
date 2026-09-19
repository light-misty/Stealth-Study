import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const css = readFileSync(resolve(process.cwd(), "src/styles.css"), "utf8");
const campusCss = readFileSync(resolve(process.cwd(), "src/campus-station.css"), "utf8");

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

  it("animates shared overlay surfaces", () => {
    expect(css).toMatch(/\.gate-overlay\s*\{[^}]*animation:/);
    expect(css).toMatch(/\.gate\s*\{[^}]*animation:/);
    expect(css).toMatch(/\.dd-menu\s*\{[^}]*animation:/);
    expect(css).toMatch(/\.dlg-card\s*\{[^}]*animation:/);
    expect(css).toMatch(/\.board-overlay\s*\{[^}]*animation:/);
    expect(css).toContain("@keyframes ss-pop-centered");
    expect(css).toContain(".modal-pop");
  });

  it("animates in-place view swaps and the rail width change", () => {
    expect(css).toMatch(/\.chat-view\s*\{[^}]*animation:/);
    expect(css).toMatch(/\.right-rail\s*\{[^}]*transition:[^}]*width/);
  });

  it("keeps the new-session page free of entrance animations", () => {
    expect(css).not.toMatch(/\.intro\s*\{[^}]*animation:/);
    expect(css).not.toMatch(/\.hero\s*\{[^}]*animation:/);
    expect(css).not.toMatch(/\.intro-head\s*\{[^}]*animation:/);
    expect(css).not.toMatch(/\.intro-lede\s*\{[^}]*animation:/);
    expect(css).not.toMatch(/\.intro-tasks\s*\{[^}]*animation:/);
  });

  it("animates transcript content, waiting state, nav reveal and campus tab strip", () => {
    expect(css).toMatch(/\.transcript > \*\s*\{[^}]*animation:/);
    expect(css).toMatch(/\.waiting-transcript\s*\{[^}]*animation:/);
    expect(css).toMatch(/\.nav-reveal-btn\s*\{[^}]*animation:/);
    expect(campusCss).toMatch(/\.campus-station \.st-tabs\s*\{[^}]*scroll-behavior:\s*smooth/);
  });
});
