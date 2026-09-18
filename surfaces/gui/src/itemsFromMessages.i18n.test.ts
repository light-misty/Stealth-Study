// OPE-136 中文化审计：实时流用 t("app.notice.*") 生成通知，但历史回放路径
// (itemsFromMessages) 把同一批句子硬编码成英文 —— 中文界面下「刷新前中文、刷新后英文」。
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import i18n from "i18next";

import { itemsFromMessages } from "./itemsFromMessages";
import zh from "./locales/zh.json";

const noticeOf = (msgs: any[]) => itemsFromMessages(msgs)[0] as any;

beforeAll(async () => {
  i18n.addResourceBundle("zh", "translation", zh, true, true);
  await i18n.changeLanguage("zh");
});

afterAll(async () => {
  await i18n.changeLanguage("en");
});

describe("回放通知跟随界面语言", () => {
  it("中断/错误/切换/压缩使用中文", () => {
    expect(noticeOf([{ role: "notice", kind: "interrupted" }]).text).toBe("已中断。");
    expect(noticeOf([{ role: "notice", kind: "model_switch" }]).text).toBe("模型已切换");
    expect(noticeOf([{ role: "notice", kind: "compacted" }]).text).toBe("上下文已压缩");
    const err = noticeOf([{ role: "notice" }]);
    expect(err.text).toBe("错误：未知");
    expect(err.retriable).toBe(true);
  });

  it("服务端已写入的文本原样保留，不做二次翻译", () => {
    expect(noticeOf([{ role: "notice", kind: "model_switch", text: "切换到 GPT-5" }]).text).toBe("切换到 GPT-5");
    expect(
      noticeOf([{ role: "notice", kind: "compacted", text: "Context compacted — earlier turns were summarized" }]).text,
    ).toBe("Context compacted — earlier turns were summarized");
  });

  it("自动批准的两条兜底文案为中文", () => {
    expect(noticeOf([{ role: "notice", kind: "reviewer_paused" }]).text).toBe("本轮次内自动批准已暂停。");
    const mode = noticeOf([{ role: "notice", kind: "mode_notice" }]);
    expect(mode.title).toBe("自动批准已开启。");
  });

  it("MCP 启动失败通知为中文，服务器名保留", () => {
    const line = noticeOf([
      { role: "notice", kind: "mcp_error", text: "MCP server “sales-db” failed to start — see Settings ▸ Connectors" },
    ]);
    expect(line.text).toBe("MCP 服务器「sales-db」未能启动，其工具在本次会话不可用");
    expect(line.server).toBe("sales-db");
    expect(line.detail).toBe("MCP server “sales-db” failed to start");
    expect(noticeOf([{ role: "notice", kind: "mcp_error" }]).text).toBe("有 MCP 服务器启动失败");
  });
});

describe("切回英文后回放文案不变", () => {
  beforeAll(async () => {
    await i18n.changeLanguage("en");
  });

  it("沿用既有英文句子", () => {
    expect(noticeOf([{ role: "notice", kind: "interrupted" }]).text).toBe("Interrupted.");
    expect(noticeOf([{ role: "notice" }]).text).toBe("Error: unknown");
    expect(noticeOf([{ role: "notice", kind: "model_switch" }]).text).toBe("Model switched");
    expect(noticeOf([{ role: "notice", kind: "compacted" }]).text).toBe("Context compacted");
    expect(noticeOf([{ role: "notice", kind: "reviewer_paused" }]).text).toBe(
      "Auto-approve paused for the rest of this turn.",
    );
    expect(noticeOf([{ role: "notice", kind: "mode_notice" }]).title).toBe("Auto-approve is on.");
    expect(noticeOf([{ role: "notice", kind: "mcp_error" }]).text).toBe("An MCP server failed to start");
    expect(
      noticeOf([{ role: "notice", kind: "mcp_error", text: "MCP server “sales-db” failed to start" }]).text,
    ).toBe("MCP server “sales-db” didn’t start — its tools are unavailable here");
  });
});
