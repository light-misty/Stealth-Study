// OPE-136 中文化审计第七批：备考台。
// 两类回归：动态拼接的 i18n 键若缺失会在界面直接印出键路径；未走 campusErrorKey 的后端
// 异常会让中文界面整句英文。都用静态扫描 + 枚举展开锁住，避免后续新增状态再次漏网。
import { describe, expect, it } from "vitest";

import en from "../../locales/en.json";
import zh from "../../locales/zh.json";
import { MOCK_STAGES } from "../../campus/types";

const PANELS = [
  "cet/AssessmentFlow.tsx",
  "cet/MockExamConsole.tsx",
  "cet/ListeningDrill.tsx",
  "cet/VocabPanel.tsx",
  "cet/GradingWorkshopBody.tsx",
];

function panelSources(): Record<string, string> {
  const mods = import.meta.glob(["./**/*.tsx", "!./**/*.test.tsx"], {
    eager: true,
    query: "?raw",
    import: "default",
  }) as Record<string, string>;
  return Object.fromEntries(Object.entries(mods).map(([k, v]) => [k.replace(/^\.\//, ""), v]));
}

function has(obj: unknown, path: string): boolean {
  return path.split(".").reduce<unknown>((acc, k) => (acc == null ? undefined : (acc as never)[k]), obj) !== undefined;
}

describe("模拟考阶段标签", () => {
  it.each(MOCK_STAGES.map((s) => [s] as const))("stage_%s 在两种语言都有键", (stage) => {
    const key = `campus.cet.mock.stage_${stage}`;
    expect(has(en, key), `${key} 缺失于 en.json`).toBe(true);
    expect(has(zh, key), `${key} 缺失于 zh.json`).toBe(true);
  });
});

describe("备考台不再直接渲染后端英文异常", () => {
  it("扫描目录非空", () => {
    expect(Object.keys(panelSources()).length).toBeGreaterThan(15);
  });

  it("被点名的面板都在扫描范围内", () => {
    const files = Object.keys(panelSources());
    for (const rel of PANELS) expect(files, `未扫描到 ${rel}`).toContain(rel);
  });

  it.each(PANELS)("%s", (rel) => {
    const leaks = panelSources()[rel]
      .split(/\r?\n/)
      .filter((line) => /campusErrorInfo\([^)]*\)\.message/.test(line) && !/defaultValue:/.test(line));
    expect(leaks, `${rel} 直接把后端 message 渲染进界面，应改走 campusErrorKey`).toEqual([]);
  });
});
