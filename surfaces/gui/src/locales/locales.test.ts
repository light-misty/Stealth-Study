import { describe, expect, it } from "vitest";
import en from "./en.json";
import zh from "./zh.json";

// OPE-136 test plan #23: every UI string must exist in BOTH locales, or the Chinese
// UI silently falls back to English one key at a time. Flattens both trees and
// compares the full key sets — additions to one file without the other fail here,
// not in production.
function flatten(obj: Record<string, unknown>, prefix = ""): string[] {
  const keys: string[] = [];
  for (const [k, v] of Object.entries(obj)) {
    const path = prefix ? `${prefix}.${k}` : k;
    if (v && typeof v === "object" && !Array.isArray(v)) {
      keys.push(...flatten(v as Record<string, unknown>, path));
    } else {
      keys.push(path);
    }
  }
  return keys.sort();
}

// i18next pluralization: English declares `_one`/`_other` pairs; Chinese has no
// singular category, so it legitimately carries only `_other`. Compare base keys —
// a missing plural VARIANT is correct per-language grammar, a missing base key is
// a real gap.
function baseKeys(keys: string[]): string[] {
  return [...new Set(keys.map((k) => k.replace(/_(zero|one|two|few|many|other)$/, "")))].sort();
}

describe("locale completeness", () => {
  it("en.json and zh.json declare the same key set", () => {
    const enKeys = baseKeys(flatten(en as Record<string, unknown>));
    const zhKeys = baseKeys(flatten(zh as Record<string, unknown>));
    const missingInZh = enKeys.filter((k) => !zhKeys.includes(k));
    const missingInEn = zhKeys.filter((k) => !enKeys.includes(k));
    expect(missingInZh, `keys missing in zh.json: ${missingInZh.join(", ")}`).toEqual([]);
    expect(missingInEn, `keys missing in en.json: ${missingInEn.join(", ")}`).toEqual([]);
  });

  // OPE-136 中文化审计：敬称混用会让同一面板里既「你」又「您」；已有英文术语
  // （provider）在中文句子里则与同文档其他处的「提供方」译法冲突。
  it("zh.json 的中文值统一使用「你」且不残留 provider 一词", () => {
    const zhValues = flatten(zh as Record<string, unknown>)
      .map((k) => [k, readPath(zh as Record<string, unknown>, k)!.replace(/\{\{[^}]*\}\}/g, "")] as const)
      .filter(([, v]) => /[一-鿿]/.test(v));
    const honor = zhValues.filter(([, v]) => v.includes("您")).map(([k]) => k);
    const latin = zhValues.filter(([, v]) => /\bprovider\b/i.test(v)).map(([k]) => k);
    expect(honor, `zh.json 仍使用「您」：${honor.join(", ")}`).toEqual([]);
    expect(latin, `zh.json 中文值残留 provider：${latin.join(", ")}`).toEqual([]);
  });
});

function readPath(obj: Record<string, unknown>, path: string): string | undefined {
  const value = path.split(".").reduce<unknown>((acc, k) => (acc == null ? undefined : (acc as Record<string, unknown>)[k]), obj);
  return typeof value === "string" ? value : undefined;
}
