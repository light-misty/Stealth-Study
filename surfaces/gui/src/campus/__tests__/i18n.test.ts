import { describe, expect, it } from "vitest";
import en from "../../locales/en.json";
import zh from "../../locales/zh.json";

const SEGMENTS = [
  "nav",
  "track",
  "common",
  "profile",
  "settings",
  "grading",
  "mistake",
  "review",
  "question",
  "library",
  "cet",
  "kaoyan",
  "cert",
  "privacy",
  "export",
  "error",
] as const;

const BACKEND_ERROR_CODES = [
  "PROFILE_REQUIRED",
  "PROFILE_NOT_FOUND",
  "PROFILE_READ_ONLY",
  "FORBIDDEN_PROFILE",
  "DUPLICATE_TITLE",
  "DUPLICATE_NODE",
  "EXAM_DATE_REQUIRED",
  "FILE_TOO_LARGE",
  "UNSUPPORTED_TYPE",
  "DISK_FULL",
  "DOC_NOT_FOUND",
  "DOC_NOT_READY",
  "DOC_SCAN_EMPTY",
  "PARSE_ERROR",
  "QUESTION_NOT_FOUND",
  "POINT_NOT_FOUND",
  "ATTEMPT_NOT_FOUND",
  "RQ_NOT_FOUND",
  "MOCK_NOT_FOUND",
  "ASSESSMENT_NOT_FOUND",
  "ITEM_NOT_FOUND",
  "INVALID_ATTRIBUTION",
  "INVALID_LEVEL",
  "ILLEGAL_TRANSITION",
  "ILLEGAL_STAGE",
  "STAGE_LOCKED",
  "MOCK_SUBMITTED",
  "PAUSE_EXCEEDED",
  "ASSESSMENT_FINISHED",
  "MODEL_NOT_CONFIGURED",
  "MODEL_TIMEOUT",
  "MODEL_OUTPUT_INVALID",
  "RUBRIC_NOT_FOUND",
  "AUTOMATION_UNAVAILABLE",
  "EXPORT_NOT_FOUND",
  "NO_TASK_DATA",
  "SCHEMA_VERSION_ERROR",
] as const;

const TRACKS = ["cet", "kaoyan", "cert"] as const;

function flatten(obj: Record<string, unknown>, prefix: string): string[] {
  const keys: string[] = [];
  for (const [key, value] of Object.entries(obj)) {
    const path = `${prefix}.${key}`;
    if (value && typeof value === "object" && !Array.isArray(value)) {
      keys.push(...flatten(value as Record<string, unknown>, path));
    } else {
      keys.push(path);
    }
  }
  return keys.sort();
}

function baseKeys(keys: string[]): string[] {
  return [...new Set(keys.map((k) => k.replace(/_(zero|one|two|few|many|other)$/, "")))].sort();
}

describe("campus i18n skeleton", () => {
  it("declares the campus namespace with every planned segment in both locales", () => {
    for (const [name, tree] of [
      ["zh", zh],
      ["en", en],
    ] as const) {
      const campus = (tree as Record<string, Record<string, unknown>>).campus;
      expect(campus, `${name}.campus namespace`).toBeTruthy();
      for (const segment of SEGMENTS) {
        expect(campus?.[segment], `${name}.campus.${segment}`).toBeTruthy();
      }
    }
  });

  it("adds the settings campus tab label to both locales", () => {
    const zhTab = (zh as Record<string, any>).settings?.tab?.campus;
    const enTab = (en as Record<string, any>).settings?.tab?.campus;
    expect(zhTab, "zh settings.tab.campus").toBeTruthy();
    expect(enTab, "en settings.tab.campus").toBeTruthy();
  });

  it("declares station track keys for the backend TrackSpec i18n_key", () => {
    for (const track of TRACKS) {
      for (const leaf of ["name", "tagline"]) {
        expect((zh as Record<string, any>).campus.track[track][leaf], `zh campus.track.${track}.${leaf}`).toBeTruthy();
        expect((en as Record<string, any>).campus.track[track][leaf], `en campus.track.${track}.${leaf}`).toBeTruthy();
      }
    }
  });

  it("maps every backend error code to a campus.error key in both locales", () => {
    for (const code of BACKEND_ERROR_CODES) {
      const key = code.toLowerCase();
      expect((zh as Record<string, any>).campus.error[key], `zh campus.error.${key}`).toBeTruthy();
      expect((en as Record<string, any>).campus.error[key], `en campus.error.${key}`).toBeTruthy();
    }
  });

  it("keeps zh/en campus base key sets equal", () => {
    const zhCampus = (zh as Record<string, Record<string, unknown>>).campus ?? {};
    const enCampus = (en as Record<string, Record<string, unknown>>).campus ?? {};
    const zhKeys = baseKeys(flatten(zhCampus, "campus"));
    const enKeys = baseKeys(flatten(enCampus, "campus"));
    const missingInZh = enKeys.filter((k) => !zhKeys.includes(k));
    const missingInEn = zhKeys.filter((k) => !enKeys.includes(k));
    expect(missingInZh, `campus keys missing in zh.json: ${missingInZh.join(", ")}`).toEqual([]);
    expect(missingInEn, `campus keys missing in en.json: ${missingInEn.join(", ")}`).toEqual([]);
  });
});
