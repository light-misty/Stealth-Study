// OPE-136 中文化审计第六批：连接器与模型提供商面板。
// 动态文案（relTime 的英文兜底、注册表通用名、云登录引导语）用行为断言锁住；静态英文
// 字面量用「白名单棘轮」扫描锁住 —— 新增硬编码英文属性会失败，确属品牌名/示例 URL 的
// 必须显式登记在 ALLOW。SlackHowItWorks 是对第三方 Slack 界面的演示插画，只参与属性扫描。
import { afterEach, beforeAll, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import i18n from "i18next";

import { ConnectorIcon } from "../../connectors/ConnectorIcon";
import { CloudSignInInline } from "./CloudSignIn";
import { relTime } from "../../providers/ProviderSetup";
import zh from "../../locales/zh.json";

const ALLOW = new Set([
  'title="GitHub"',
  'title="Gmail"',
  'title="HubSpot"',
  'title="Slack"',
  'placeholder="https://mcp.example.com/mcp"',
]);

const asText = (mods: unknown) => Object.entries(mods as Record<string, string>);

function sources(): [string, string][] {
  return [
    ...asText(import.meta.glob("./*.{ts,tsx}", { eager: true, query: "?raw", import: "default" })),
    ...asText(import.meta.glob("../../connectors/*.{ts,tsx}", { eager: true, query: "?raw", import: "default" })),
    ...asText(import.meta.glob("../../providers/*.{ts,tsx}", { eager: true, query: "?raw", import: "default" })),
  ].filter(([file]) => !/\.test\./.test(file));
}

beforeAll(async () => {
  i18n.addResourceBundle("zh", "translation", zh, true, true);
  await i18n.changeLanguage("zh");
});

afterEach(() => {
  cleanup();
  localStorage.removeItem("ocw.flag.login");
});

describe("连接器文案跟随语言", () => {
  it("注册表通用名为中文，品牌名保持原样", () => {
    render(<ConnectorIcon connector={{ name: "email", logo: "email" } as any} />);
    expect(screen.getByRole("img").getAttribute("aria-label")).toBe("邮件");
    cleanup();
    render(<ConnectorIcon connector={{ name: "browser", logo: "browser" } as any} />);
    expect(screen.getByRole("img").getAttribute("aria-label")).toBe("浏览器");
    cleanup();
    render(<ConnectorIcon connector={{ name: "x", logo: "no-such-logo" } as any} />);
    expect(screen.getByRole("img").getAttribute("aria-label")).toBe("连接器");
    cleanup();
    render(<ConnectorIcon connector={{ name: "slack", logo: "slack" } as any} />);
    expect(screen.getByRole("img").getAttribute("aria-label")).toBe("Slack");
  });

  it("相对时间跟随语言", () => {
    const now = Math.floor(Date.now() / 1000);
    const t = i18n.getFixedT(null, "translation");
    expect(relTime(now - 10, t)).toBe("刚刚");
    expect(relTime(now - 600, t)).toBe("10 分钟前");
    expect(relTime(now - 7_200, t)).toBe("2 小时前");
    expect(relTime(now - 172_800, t)).toBe("2 天前");
    expect(relTime(null, t)).toBeNull();
  });

  it("云登录引导语不再是英文兜底", () => {
    localStorage.setItem("ocw.flag.login", "1");
    render(<CloudSignInInline />);
    expect(screen.getByText("登录后可一键连接，或改用无需登录的手动方式。")).toBeTruthy();
  });
});

describe("连接器目录不残留英文字面量", () => {
  const PROSE = /[A-Za-z]{2,}/;
  const isUrl = (v: string) => /^https?:\/\//.test(v);

  it("扫描目录非空", () => {
    expect(sources().length).toBeGreaterThan(15);
  });

  it.each(sources())("%s", (file, text) => {
    const offenders: string[] = [];
    for (const line of text.split(/\r?\n/)) {
      const plain = line.match(/(?:title|aria-label|placeholder|alt|label)="([^"]+)"/g) || [];
      for (const hit of plain) {
        const value = hit.slice(hit.indexOf('="') + 2, -1);
        if (!PROSE.test(value) || isUrl(value)) continue;
        if (ALLOW.has(hit)) continue;
        offenders.push(`${file}: ${line.trim()}`);
      }
      const tpl = line.match(/(?:title|aria-label|placeholder)=\{\x60([^$\x60]*)/g) || [];
      for (const hit of tpl) {
        const value = hit.slice(hit.indexOf("\x60") + 1);
        if (PROSE.test(value)) offenders.push(`${file}: ${line.trim()}`);
      }
    }
    expect(offenders, `${file} 存在未走 i18n 的英文界面文案`).toEqual([]);
  });
});
