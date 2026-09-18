// OPE-136 中文化审计第五批：散落在纯模块与小组件里的英文标签。
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import i18n from "i18next";

import { fullPersonaName, shortPersonaName } from "./personaScope";
import { startDictation } from "./tauri";
import { Markdown } from "./components/Markdown";
import { ModelChecklist } from "./components/ModelChecklist";
import zh from "./locales/zh.json";

vi.mock("./api", () => ({
  addModel: vi.fn(async (id: string) => ({ ok: true, models: [id], model: id })),
  removeModel: vi.fn(async () => ({ ok: true, models: [], model: "" })),
  setDefaultModel: vi.fn(async () => ({ ok: true })),
  getSettings: vi.fn(async () => ({ models: [], model: "" })),
}));

const KNOWN = ["openai", "anthropic", "bedrock", "vertex"];

function renderChecklist(provider: string) {
  return render(
    <ModelChecklist
      provider={provider}
      knownProviders={KNOWN}
      suggested={[]}
      curated={[]}
      defaultModel=""
      onChanged={() => {}}
    />,
  );
}

beforeAll(async () => {
  i18n.addResourceBundle("zh", "translation", zh, true, true);
  await i18n.changeLanguage("zh");
});

afterEach(() => {
  cleanup();
});

afterAll(async () => {
  await i18n.changeLanguage("en");
});

describe("persona 名称跟随语言", () => {
  it("同事家族名用中文", () => {
    expect(shortPersonaName("Coworker", "cowork")).toBe("同事");
    expect(fullPersonaName("Coworker", "cowork")).toBe("同事");
    expect(shortPersonaName("Code Coworker", "code")).toBe("Code");
    expect(fullPersonaName("Code Coworker", "code")).toBe("Code 同事");
    expect(fullPersonaName("Ops", "ops")).toBe("Ops 同事");
    expect(fullPersonaName("Chat", "chat")).toBe("Chat");
  });
});

describe("非桌面端错误提示", () => {
  it("抛出的错误信息为中文", async () => {
    delete (globalThis as any).__TAURI__;
    await expect(startDictation()).rejects.toThrow("此功能需在桌面应用中运行。");
  });
});

describe("模型家族下拉", () => {
  it("选项与无障碍名为中文", () => {
    renderChecklist("vertex");
    const select = screen.getByRole("combobox", { name: "模型家族" });
    expect(select).toBeTruthy();
    expect(Array.from(select.querySelectorAll("option")).map((o) => o.textContent)).toEqual([
      "Gemini 系列",
      "Claude 系列",
      "开源权重",
    ]);
  });
});

describe("看板跳转胶囊", () => {
  it("悬浮说明为中文", () => {
    render(<Markdown text="[Board · 5 items](board:)" />);
    const chip = screen.getByTestId("board-chip");
    expect(chip.getAttribute("title")).toBe("打开看板");
    expect(chip.textContent).toContain("Board · 5 items");
  });
});

describe("切回英文后保持原样", () => {
  beforeAll(async () => {
    await i18n.changeLanguage("en");
  });

  it("沿用既有英文", () => {
    expect(shortPersonaName("Coworker", "cowork")).toBe("Coworker");
    expect(fullPersonaName("Code Coworker", "code")).toBe("Code Coworker");
    expect(fullPersonaName("coworker", "ops")).toBe("coworker");
    renderChecklist("bedrock");
    const select = screen.getByRole("combobox", { name: "Model family" });
    expect(Array.from(select.querySelectorAll("option")).map((o) => o.textContent)).toEqual([
      "Claude family",
      "Other models",
    ]);
    cleanup();
    render(<Markdown text="[Board · 5 items](board:)" />);
    expect(screen.getByTestId("board-chip").getAttribute("title")).toBe("Open the board");
  });
});
