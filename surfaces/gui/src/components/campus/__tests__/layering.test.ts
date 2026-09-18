import { describe, expect, it } from "vitest";
import en from "../../../locales/en.json";
import zh from "../../../locales/zh.json";

// 08 §8 (T16-T19): the layering rule from 01 §4 is a grep gate — no component may branch
// on the track, station differences belong in the config tables. The i18n half of 08 §6.2
// (referenced keys ⊆ defined keys) is checked here too so a missing key fails CI instead
// of leaking a raw key to the user.
//
// Sources are pulled in as raw text through Vite's glob, which keeps this file free of
// node built-ins (the production `tsc` pass typechecks everything under src/).

const componentSources = import.meta.glob("../**/*.tsx", {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>;
const campusModuleSources = import.meta.glob("../../../campus/*.ts", {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>;

const sourcesOf = (bundle: Record<string, string>): [string, string][] =>
  Object.entries(bundle).filter(([path]) => !path.includes(".test."));

const componentFiles = sourcesOf(componentSources);
const campusSources = sourcesOf(campusModuleSources);

const stripComments = (source: string): string =>
  source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/[^\n]*/g, "");

function flatten(obj: Record<string, unknown>, prefix = ""): Set<string> {
  const keys = new Set<string>();
  for (const [key, value] of Object.entries(obj)) {
    const path = prefix ? `${prefix}.${key}` : key;
    if (value && typeof value === "object" && !Array.isArray(value)) {
      for (const child of flatten(value as Record<string, unknown>, path)) keys.add(child);
    } else {
      keys.add(path);
    }
  }
  return keys;
}

const enKeys = flatten(en as Record<string, unknown>);
const zhKeys = flatten(zh as Record<string, unknown>);

describe("campus layering rules", () => {
  it("finds the campus sources to check", () => {
    expect(componentFiles.length).toBeGreaterThan(5);
    expect(campusSources.length).toBeGreaterThan(1);
  });

  it("never branches on the track inside a component", () => {
    const offenders: string[] = [];
    for (const [path, source] of [...componentFiles, ...campusSources]) {
      if (/\btrack\s*===\s*/.test(source) || /\btrack\s*==\s*[^=]/.test(source)) {
        offenders.push(path);
      }
    }
    expect(offenders, `track equality branches: ${offenders.join(", ")}`).toEqual([]);
  });

  it("keeps campus components off the legacy app api", () => {
    const offenders = componentFiles
      .filter(([, source]) => /from\s+"(?:\.\.\/)+api"/.test(source))
      .map(([path]) => path);
    expect(offenders, `legacy api imports: ${offenders.join(", ")}`).toEqual([]);
  });

  it("keeps Chinese UI copy out of the sources (all of it goes through i18n)", () => {
    const offenders = componentFiles
      .filter(([, source]) => /[一-鿿]/.test(stripComments(source)))
      .map(([path]) => path);
    expect(offenders, `hardcoded Chinese strings: ${offenders.join(", ")}`).toEqual([]);
  });
});

describe("campus i18n key coverage", () => {
  const literalKeys = (): string[] => {
    const found = new Set<string>();
    for (const [, source] of [...componentFiles, ...campusSources]) {
      for (const match of source.matchAll(/"(campus\.[\w.]+)"/g)) found.add(match[1]);
    }
    return [...found].sort();
  };

  it("defines every literal campus key in both locales", () => {
    const keys = literalKeys();
    expect(keys.length).toBeGreaterThan(20);
    // A base key may be defined through its plural variants (i18next resolves them).
    const defined = (set: Set<string>, key: string) =>
      set.has(key) || set.has(`${key}_one`) || set.has(`${key}_other`);
    const missingInZh = keys.filter((key) => !defined(zhKeys, key));
    const missingInEn = keys.filter((key) => !defined(enKeys, key));
    expect(missingInZh, `missing in zh.json: ${missingInZh.join(", ")}`).toEqual([]);
    expect(missingInEn, `missing in en.json: ${missingInEn.join(", ")}`).toEqual([]);
  });

  it("defines the key families built at runtime", () => {
    const families: string[][] = [
      ["unknown", "fuzzy", "mastered"].map((level) => `campus.common.mastery.${level}`),
      [
        "concept_unclear",
        "misread",
        "calculation_or_operation",
        "out_of_scope",
        "time_short",
        "pending",
      ].map((item) => `campus.common.attribution.${item}`),
      ["grading", "question", "explain"].map((task) => `campus.model.task.${task}`),
      [
        "registration_open",
        "registration_close",
        "payment_close",
        "admission_ticket",
        "exam",
        "score_query",
      ].map((node) => `campus.cert.deadline.node.${node}`),
      [1, 2, 3].map((level) => `campus.grading.degrade_notice_${level}`),
      // One tab label per station panel (CampusStationView's PanelSpec.tab); the keys are built
      // at runtime by template, so the strip's whole vocabulary is spelled out here instead.
      [
        "mistake",
        "review",
        "assessment",
        "vocab",
        "listening",
        "essay",
        "translation",
        "mock",
        "common_errors",
        "library",
        "qa",
        "plan",
        "weekly",
        "tutor",
        "cert_tree",
        "cert_grading",
        "cert_setup",
      ].map((tab) => `campus.station.tab.${tab}`),
    ];
    for (const family of families) {
      for (const key of family) {
        expect(zhKeys.has(key), `zh missing ${key}`).toBe(true);
        expect(enKeys.has(key), `en missing ${key}`).toBe(true);
      }
    }
  });

  it("keeps the plural variants the countdown and counters rely on", () => {
    for (const base of [
      "campus.common.days_left",
      "campus.mistake.count",
      "campus.mistake.wrong_count",
    ]) {
      expect(enKeys.has(`${base}_one`) && enKeys.has(`${base}_other`), `${base} en plural`).toBe(
        true,
      );
      expect(zhKeys.has(`${base}_other`), `${base} zh plural`).toBe(true);
    }
  });
});
