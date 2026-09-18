// OPE-136 中文化审计：Composer 的 "/" 技能浮层与 token 用量 chip/弹层此前完全不走 i18n，
// 中文界面下浮层提示、占用条标题、单位说明整段英文。
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import i18n from "i18next";

import { Composer } from "./Composer";
import zh from "../locales/zh.json";

const MENU = {
  skills: [
    { name: "weekly-report", description: "Monday status report", scope: "global", enabled: true },
    { name: "greet", description: "says hello", scope: "project", enabled: true },
  ],
};

function stubFetch(skills: unknown) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      if (String(url).includes("/skills")) return { ok: true, json: async () => ({ skills }) } as Response;
      return { ok: true, json: async () => ({}) } as Response;
    }),
  );
}

const props = (extra: Partial<Parameters<typeof Composer>[0]> = {}) => ({
  mode: "interactive" as const,
  model: "gpt-5.6-sol",
  running: false,
  connected: true,
  sessionId: "s1",
  onSend: vi.fn(),
  onInterrupt: vi.fn(),
  onModeChange: vi.fn(),
  onModelChange: vi.fn(),
  ...extra,
});

const USAGE = {
  byModel: { "gpt-5": { input: 1_000, output: 8_000, cache_read: 800, cache_write: 0 } },
  context: 9_800,
};

const box = () => screen.getByRole("textbox");

beforeAll(async () => {
  i18n.addResourceBundle("zh", "translation", zh, true, true);
  await i18n.changeLanguage("zh");
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("中文界面下的技能浮层", () => {
  it("加载中文案与无障碍名", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Promise<Response>(() => {})));
    render(<Composer {...props()} />);
    fireEvent.change(box(), { target: { value: "/" } });
    expect(await screen.findByTestId("skill-popup")).toBeTruthy();
    expect(screen.getByText("正在加载技能…")).toBeTruthy();
  });

  it("无匹配与 scope 徽章为中文", async () => {
    stubFetch([]);
    render(<Composer {...props()} />);
    fireEvent.change(box(), { target: { value: "/zzz" } });
    expect(await screen.findByText("没有匹配的技能。")).toBeTruthy();
    cleanup();

    stubFetch(MENU.skills);
    render(<Composer {...props()} />);
    fireEvent.change(box(), { target: { value: "/" } });
    const popup = await screen.findByTestId("skill-popup");
    expect(popup.getAttribute("aria-label")).toBe("技能");
    expect(screen.getByText("全局")).toBeTruthy();
    expect(screen.getByText("项目")).toBeTruthy();
  });
});

describe("中文界面下的 token 用量", () => {
  it("chip 的悬浮说明与弹层为中文", async () => {
    stubFetch([]);
    render(<Composer {...props({ usage: USAGE as any, contextWindow: 200_000, contextBar: true })} />);
    const chip = await screen.findByTestId("usage-chip");
    expect(chip.getAttribute("aria-label")).toBe("token 用量");
    expect(chip.getAttribute("title")).toBe("上下文窗口已用 5% —— 9.8k / 200k");

    fireEvent.click(chip);
    const pop = await screen.findByTestId("usage-popover");
    expect(pop.textContent).toContain("上下文窗口");
    expect(pop.textContent).toContain("已用 9.8k / 200k · 5%");
    expect(pop.textContent).not.toMatch(/Context window|of 200k/);
  });

  it("无上下文窗口时给出中文占用说明", async () => {
    stubFetch([]);
    render(<Composer {...props({ usage: USAGE as any, model: "custom-model" })} />);
    const chip = await screen.findByTestId("usage-chip");
    expect(chip.getAttribute("title")).toBe("当前上下文：9.8k tokens");
    fireEvent.click(chip);
    expect(await screen.findByText("自定义模型无法显示上下文占用。")).toBeTruthy();
  });
});

describe("切回英文后 composer 文案不变", () => {
  beforeAll(async () => {
    await i18n.changeLanguage("en");
  });

  it("沿用既有英文", async () => {
    stubFetch([]);
    render(<Composer {...props({ usage: USAGE as any, contextWindow: 200_000, contextBar: true })} />);
    const chip = await screen.findByTestId("usage-chip");
    expect(chip.getAttribute("aria-label")).toBe("Token usage");
    expect(chip.getAttribute("title")).toBe("Context window 5% full — 9.8k of 200k");
    fireEvent.click(chip);
    const pop = await screen.findByTestId("usage-popover");
    expect(pop.textContent).toContain("Context window");
    expect(pop.textContent).toContain("9.8k of 200k · 5%");
    cleanup();

    stubFetch(MENU.skills);
    render(<Composer {...props()} />);
    fireEvent.change(box(), { target: { value: "/" } });
    const popup = await screen.findByTestId("skill-popup");
    expect(popup.getAttribute("aria-label")).toBe("Skills");
    expect(screen.getByText("project")).toBeTruthy();
  });
});
