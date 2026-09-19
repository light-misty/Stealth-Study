// 后端错误 → 界面文案的唯一入口：有代号且语言包备齐就走语言包，否则退回原文。
// 原始文本始终保留在 detail 里，供悬浮提示与日志使用（方案 C 的兜底）。
import { beforeAll, describe, expect, it } from "vitest";
import i18n from "i18next";

import { apiErrorDetail, apiErrorText } from "./errors";
import en from "./locales/en.json";
import zh from "./locales/zh.json";

const t = (k: string, o?: Record<string, unknown>) =>
  i18n.getFixedT(null, "translation")(k, o) as string;

beforeAll(async () => {
  i18n.addResourceBundle("zh", "translation", zh, true, true);
  await i18n.changeLanguage("zh");
});

describe("apiErrorText", () => {
  it("有代号时用中文，且不再打印英文原文", () => {
    const res = { ok: false, error: "[WinError 5] Access is denied: 'D:\\\\repo'", error_code: "PERMISSION_DENIED" };
    expect(apiErrorText(res, t)).toBe("权限不足 —— 本应用无权访问该路径。");
  });

  it("代号大小写与前后空格都不影响解析", () => {
    expect(apiErrorText({ error_code: " disk_full ", error: "No space left" }, t)).toBe("磁盘空间不足 —— 请清理后重试。");
  });

  it("没有代号时保留后端原文，行为与改造前一致", () => {
    expect(apiErrorText({ error: "could not move the folder: EBUSY" }, t)).toBe("could not move the folder: EBUSY");
    expect(apiErrorText({ error_code: "NOT_A_REAL_CODE", error: "raw text" }, t)).toBe("raw text");
  });

  it("两者都缺时给通用中文提示", () => {
    expect(apiErrorText({}, t)).toBe("出错了。");
    expect(apiErrorText(undefined, t)).toBe("出错了。");
    expect(apiErrorText({ error: "" }, t, "连接失败")).toBe("连接失败");
  });

  it("英文界面用英文表", async () => {
    await i18n.changeLanguage("en");
    expect(apiErrorText({ error_code: "NETWORK_TIMEOUT", error: "timed out" }, t)).toBe(
      "The request timed out — check your connection and try again.",
    );
    await i18n.changeLanguage("zh");
  });

  it("代号携带参数时把变量插进本地化句子", () => {
    const res = {
      error: "Unknown skill: weekly-report",
      error_code: "SKILL_NOT_FOUND",
      error_params: { name: "weekly-report" },
    };
    expect(apiErrorText(res, t)).toBe("找不到技能「weekly-report」。");
  });

  it("detail 始终给出原始文本供悬浮与日志使用", () => {
    expect(apiErrorDetail({ error: "boom", error_code: "UNCLASSIFIED" })).toBe("boom");
    expect(apiErrorDetail({ error: "", error_code: "PERMISSION_DENIED" })).toBe("");
  });
});

describe("语言包与后端代号对齐", () => {
  it("两个语言都覆盖 error 命名空间且键集相同", () => {
    expect(Object.keys(en.error).sort()).toEqual(Object.keys(zh.error).sort());
    expect(Object.keys(en.error).length).toBeGreaterThan(20);
  });
});
