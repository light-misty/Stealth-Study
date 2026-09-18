// OPE-136 中文化审计：上下文压缩卡片与自动批准卡片此前不调用 useTranslation，
// 整卡英文直出。这里锁住中文界面下这两张卡的文案来源。
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import i18n from "i18next";

vi.mock("../campus/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../campus/api")>();
  return { ...actual, getAppState: vi.fn(), patchAppState: vi.fn() };
});

vi.mock("../api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api")>();
  return {
    ...actual,
    getSettings: vi.fn(async () => ({
      models: ["gpt-5"],
      model_labels: {},
      compaction_threshold_pct: 0.8,
      compaction_cap_tokens: 250_000,
      compaction_model: "",
      auto_approve: true,
      auto_approve_shadow: true,
    })),
  };
});

import * as campusApi from "../campus/api";
import zh from "../locales/zh.json";
import { SettingsView } from "./SettingsView";

const campusMock = campusApi as unknown as Record<string, ReturnType<typeof vi.fn>>;

beforeAll(async () => {
  i18n.addResourceBundle("zh", "translation", zh, true, true);
  await i18n.changeLanguage("zh");
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function openTab(label: string) {
  vi.stubGlobal("fetch", vi.fn(async () => new Promise<Response>(() => {})));
  campusMock.getAppState.mockResolvedValue({ active_profile_id: null, settings: {} });
  render(<SettingsView />);
  fireEvent.click(within(screen.getByRole("navigation")).getByText(label));
}

describe("中文界面下的设置卡片", () => {
  it("上下文优化标签页与压缩卡片全中文", async () => {
    openTab("上下文优化");
    const card = await screen.findByTestId("compaction-card");
    expect(card.textContent).toContain("上下文压缩");
    expect(card.textContent).toContain("压缩于");
    expect(card.textContent).toContain("% 的上下文窗口时");
    expect(card.textContent).toContain("或");
    expect(card.textContent).toContain("个 token，以较小者为准");
    expect(card.textContent).toContain("摘要模型");
    expect(card.textContent).toContain("会话自身模型（默认）");
    expect(card.textContent).not.toMatch(/[A-Za-z]{6,}/);
  });

  it("自动批准卡片全中文且保留 <em> 强调", async () => {
    openTab("通用");
    const card = await screen.findByTestId("auto-approve-card");
    expect(card.textContent).toContain("自动批准（实验性）");
    expect(card.textContent).toContain("启用自动批准模式");
    expect(card.textContent).toContain("影子评估（用于度量）");
    expect(card.querySelector("em")?.textContent).toBe("自动批准");
    expect(card.textContent).not.toContain("Auto-approve");
    expect(card.textContent).not.toContain("Shadow evaluation");
  });

  it("面板副标题跟随语言", async () => {
    openTab("上下文优化");
    expect(await screen.findByText("会话如何消耗 token —— 附件处理方式与长历史压缩。")).toBeTruthy();
  });
});
