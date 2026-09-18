// OPE-136 中文化审计：transcript 的步骤行/审批标题由 humanize.ts 拼装，早期版本把英文
// 句子硬编码在 switch 分支里，中文界面会整行漏出英文。这里锁住两种语言下的输出。
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import i18n from "i18next";

import { humanizeApprovalTitle, humanizeAsk, humanizeTool } from "./humanize";
import en from "./locales/en.json";
import zh from "./locales/zh.json";

const CJK = /[㐀-鿿]/;

beforeAll(async () => {
  i18n.addResourceBundle("zh", "translation", zh, true, true);
  await i18n.changeLanguage("zh");
});

afterAll(async () => {
  await i18n.changeLanguage("en");
});

describe("humanizeTool 中文输出", () => {
  it("文件类步骤使用中文动词", () => {
    expect(humanizeTool("read_file", { path: "docs/runbook.md" })).toEqual({ pre: "已读取 ", obj: "runbook.md" });
    expect(humanizeTool("write_file", { path: "a/b/c.ts" }).pre).toBe("已写入 ");
    expect(humanizeTool("replace_in_file", { path: "c.ts" }).pre).toBe("已编辑 ");
    expect(humanizeTool("apply_patch", {}).pre).toBe("已编辑 ");
    expect(humanizeTool("apply_patch", {}).obj).toBe("文件");
  });

  it("缺失 path 时回退到中文占位而不是 a file", () => {
    expect(humanizeTool("read_file", {}).obj).toBe("某个文件");
  });

  it("命令与网页步骤保持前缀+对象结构", () => {
    expect(humanizeTool("run_shell", { command: "ls" }).pre).toBe("已运行 ");
    expect(humanizeTool("run_shell", { command: "ls", run_in_background: true }).pre).toBe("已在后台启动：");
    expect(humanizeTool("web_search", { query: "台风" }).pre).toBe("已联网搜索 —— ");
    expect(humanizeTool("load_skill", { name: "weekly-report" }).pre).toBe("已使用技能：");
    expect(humanizeTool("request_directory", { path: "D:/repo" }).pre).toBe("已申请文件夹访问权限 —— ");
  });

  it("无对象步骤整句中文", () => {
    for (const name of ["shell_task_output", "shell_task_kill", "git_log", "ask_user", "propose_plan"]) {
      expect(humanizeTool(name, {}), `${name} 仍是英文`).toMatchObject({ pre: expect.stringMatching(CJK) });
    }
  });

  it("计划状态词跟随语言", () => {
    const line = humanizeTool("todo_write", { todos: [{ content: "发日报", status: "in_progress" }] });
    expect(line.pre).toBe("已更新计划 —— ");
    expect(line.post).toBe(" → 进行中");
    expect(humanizeTool("todo_write", { todos: [{ content: "x", status: "pending" }] }).post).toBe(" → 待办");
    expect(humanizeTool("todo_write", { todos: [{ content: "x" }, { content: "y" }] }).pre).toBe("已更新计划 —— 2 项");
  });

  it("未知工具保留工具名但用中文引导", () => {
    const line = humanizeTool("gmail_search_messages", { query: "from:ci" });
    expect(line.pre).toBe("已使用 gmail_search_messages");
    expect(line.post).toContain("query=from:ci");
  });

  it("消息类步骤把平台名放在中文句式中", () => {
    expect(humanizeTool("send_message", { target: "slack:C0123" }).pre).toBe("已发送 Slack 消息给 ");
    expect(humanizeTool("send_message", {}).pre).toBe("已发送消息");
  });
});

describe("humanizeApprovalTitle 中文输出", () => {
  it("审批标题使用中文动词", () => {
    expect(humanizeApprovalTitle("write_file", { path: "x.ts" })).toEqual({ pre: "写入 ", obj: "x.ts" });
    expect(humanizeApprovalTitle("replace_in_file", { path: "x.ts" }).pre).toBe("编辑 ");
    expect(humanizeApprovalTitle("run_shell", { command: "ls" }).pre).toBe("运行命令");
    expect(humanizeApprovalTitle("web_fetch", { url: "https://example.com/a" }).pre).toBe("访问 ");
    expect(humanizeApprovalTitle("web_fetch", { url: "not a url" }).pre).toBe("访问网页");
    expect(humanizeApprovalTitle("web_search", {}).pre).toBe("联网搜索");
    expect(humanizeApprovalTitle("save_skill", { name: "kw" })).toEqual({ pre: "添加技能 ", obj: "kw", post: " 到你的技能库" });
    expect(humanizeApprovalTitle("save_skill", {}).pre).toBe("添加一个技能到你的技能库");
    expect(humanizeApprovalTitle("send_file", { target: "telegram:chat" }).pre).toBe("发送文件给 ");
    expect(humanizeApprovalTitle("send_file", {}).pre).toBe("发送文件");
    expect(humanizeApprovalTitle("send_message", {}).pre).toBe("发送消息");
    expect(humanizeApprovalTitle("create_scheduled_task", {}).pre).toBe("创建自动化任务");
  });

  it("未知工具名不翻译，但引导词是中文", () => {
    expect(humanizeApprovalTitle("custom_tool", {}).pre).toBe("使用 custom_tool");
  });
});

describe("humanizeAsk 中文输出", () => {
  it("未执行的请求以「想要…」表述", () => {
    expect(humanizeAsk("run_shell", { command: "rm -rf build/" })).toEqual({ pre: "想要运行 ", obj: "rm -rf build/" });
    expect(humanizeAsk("write_file", { path: "x.ts" }).pre).toBe("想要写入 ");
    expect(humanizeAsk("apply_patch", {}).pre).toBe("想要编辑 ");
    expect(humanizeAsk("send_message", {}).pre).toBe("想要发送消息");
    expect(humanizeAsk("unknown_tool", {}).pre).toBe("想要使用 unknown_tool");
  });

  it("带目标的发消息保持前中后三段中文", () => {
    const line = humanizeAsk("send_message", { target: "slack:C0123" });
    expect(line).toEqual({ pre: "想要给 ", obj: "C0123", post: " 发消息（Slack）" });
  });
});

describe("切回英文后输出保持不变", () => {
  beforeAll(async () => {
    await i18n.changeLanguage("en");
  });

  it("沿用原有的英文文案", () => {
    expect(humanizeTool("read_file", { path: "runbook.md" })).toEqual({ pre: "Read ", obj: "runbook.md" });
    expect(humanizeTool("load_skill", { name: "x" }).pre).toBe("Used skill: ");
    expect(humanizeTool("todo_write", { todos: [{ content: "a", status: "in_progress" }] }).post).toBe(" → in progress");
    expect(humanizeAsk("run_shell", { command: "ls" }).pre).toBe("Wanted to run ");
    expect(humanizeApprovalTitle("write_file", { path: "a.md" }).pre).toBe("Write ");
    expect(humanizeApprovalTitle("save_skill", { name: "kw" }).post).toBe(" to your skills");
    expect(humanizeTool("read_file", {}).obj).toBe("a file");
    expect(en.humanize.tool.read_file).toBe("Read ");
  });
});
