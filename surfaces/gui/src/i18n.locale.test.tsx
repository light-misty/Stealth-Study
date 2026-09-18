// OPE-136 中文化审计第八批：日期时间格式此前一律跟随操作系统区域（toLocale* 传空 locale），
// 中文界面在英文系统上仍显示 9:09 PM / 7/22/26；<html lang> 也固定为 en。
import { describe, expect, it } from "vitest";
import { render } from "@testing-library/react";
import i18n from "i18next";

import { beforeAll } from "vitest";
import { getCurrentLanguage, intlLocale, setLanguage } from "./i18n";
import { Transcript } from "./components/Transcript";
import zh from "./locales/zh.json";

beforeAll(async () => {
  i18n.addResourceBundle("zh", "translation", zh, true, true);
});

const AT = new Date(2026, 8, 18, 21, 9, 0);

function bubbleTime() {
  const { container } = render(
    <Transcript
      items={[{ kind: "assistant", text: "hello", ts: Math.floor(AT.getTime() / 1000) }]}
      running={false}
      onApprove={() => {}}
    />,
  );
  return container.querySelector('[data-testid="bubble-ts"]')!.textContent!;
}

describe("日期时间格式化必须显式传入应用语言", () => {
  const mods = import.meta.glob("./**/*.{ts,tsx}", {
    eager: true,
    query: "?raw",
    import: "default",
  }) as Record<string, string>;
  const files = Object.entries(mods).filter(([file]) => !/\.test\./.test(file));

  it("扫描范围非空", () => {
    expect(files.length).toBeGreaterThan(100);
  });

  it.each(files)("%s", (file, text) => {
    const bare = text
      .split(/\r?\n/)
      .filter((line) => /\.toLocale(Time|Date)?String\((\[\]|undefined)?\s*[,)]/.test(line));
    expect(bare, `${file} 存在跟随操作系统区域的日期时间格式化`);
    expect(bare).toEqual([]);
  });
});

describe("intlLocale 跟随应用语言", () => {
  it("中文界面用 zh-CN", async () => {
    await setLanguage("zh");
    expect(getCurrentLanguage()).toBe("zh");
    expect(intlLocale()).toBe("zh-CN");
    expect(document.documentElement.lang).toBe("zh");
    expect(bubbleTime()).toBe(AT.toLocaleTimeString("zh-CN", { hour: "numeric", minute: "2-digit" }));
    expect(bubbleTime()).not.toMatch(/AM|PM/);
  });

  it("英文界面用 en-US", async () => {
    await setLanguage("en");
    expect(intlLocale()).toBe("en-US");
    expect(document.documentElement.lang).toBe("en");
    expect(bubbleTime()).toBe("9:09 PM");
  });
});

describe("原生托盘菜单跟随语言", () => {
  it("切换语言时把译文下发给 set_tray_labels", async () => {
    const calls: { cmd: string; args: unknown }[] = [];
    (globalThis as any).__TAURI__ = {
      core: {
        invoke: async (cmd: string, args: unknown) => {
          calls.push({ cmd, args });
          return null;
        },
      },
    };
    try {
      await setLanguage("zh");
      await setLanguage("en");
    } finally {
      delete (globalThis as any).__TAURI__;
    }
    expect(calls.map((c) => c.cmd)).toEqual(["set_tray_labels", "set_tray_labels"]);
    expect(calls[0].args).toEqual({ open: "打开 Stealth Study", settings: "设置", quit: "退出" });
    expect(calls[1].args).toEqual({ open: "Open Stealth Study", settings: "Settings", quit: "Quit" });
  });
});
