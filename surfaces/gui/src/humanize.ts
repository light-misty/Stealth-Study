// UX-015 (§33): tool calls render as one-liners. The model does NOT emit a purpose
// per call — the stream is name+args+result — so the sentence is synthesized here from
// per-tool templates. `run_shell` is the exception: its optional `description` argument is
// model-written intent and is preferred when present. Fallback: "Used <tool> — <short args>".

import { getI18n } from "react-i18next";

import { shortArgs } from "./components/ApprovalCard";

// A one-line sentence in three segments so the UI can emphasize the object:
// "Read " + <b>runbook.md</b> + " from the shared folder".
export interface HumanLine {
  pre: string;
  obj?: string;
  post?: string;
}

const th = (k: string, opts?: Record<string, unknown>) =>
  getI18n().getFixedT(null, "translation")(`humanize.${k}`, opts) as string;

const trunc = (s: string, n: number) => (s.length > n ? s.slice(0, n - 1) + "…" : s);
const baseName = (p: string) => p.replace(/\/+$/, "").split("/").pop() || p;
const lowerFirst = (s: string) => `${s.charAt(0).toLowerCase()}${s.slice(1)}`;

// send_message targets are "platform:chat" or "platform:chat:thread" — show the platform
// by name and the last human-ish segment of the chat id.
function messageTarget(target: string): { platform: string; tail: string } {
  const [platform, ...rest] = String(target).split(":");
  const chat = rest[0] || "";
  const tail = chat.includes("/") ? chat.split("/").pop() || chat : chat;
  const names: Record<string, string> = { slack: "Slack", telegram: "Telegram" };
  return { platform: names[platform] || platform, tail };
}

function statusLabel(status: string): string {
  const key = `status.${status.toLowerCase()}`;
  const resolved = th(key);
  return resolved === `humanize.${key}` ? status.replace(/_/g, " ") : resolved;
}

export function humanizeTool(name: string, args: any): HumanLine {
  const a = args && typeof args === "object" ? args : {};
  switch (name) {
    case "run_shell": {
      const cmd = trunc(String(a.command ?? ""), 60);
      const desc = typeof a.description === "string" && a.description.trim() ? a.description.trim() : "";
      const pre = a.run_in_background ? th("tool.started_background") : th("tool.ran_command");
      return {
        pre,
        obj: cmd,
        ...(desc ? { post: th("tool.detail_suffix", { text: lowerFirst(desc) }) } : {}),
      };
    }
    case "shell_task_output":
      return { pre: th("tool.checked_background") };
    case "shell_task_kill":
      return { pre: th("tool.stopped_background") };
    case "read_file":
      return { pre: th("tool.read_file"), obj: baseName(String(a.path ?? th("tool.a_file"))) };
    case "write_file":
      return { pre: th("tool.write_file"), obj: baseName(String(a.path ?? th("tool.a_file"))) };
    case "replace_in_file":
    case "apply_patch":
    case "apply_unified_diff":
      return { pre: th("tool.edited_file"), obj: a.path ? baseName(String(a.path)) : th("tool.files") };
    case "grep":
      return { pre: th("tool.searched_code"), obj: `“${trunc(String(a.pattern ?? ""), 40)}”` };
    case "git_log":
      return { pre: th("tool.git_history") };
    case "todo_write": {
      // `todos` is current; `items` renders histories from before the rename (the old
      // key breaks Together's GLM-5.2 chat template — see coworker/tools/todo.py).
      const items = Array.isArray(a.todos) ? a.todos : Array.isArray(a.items) ? a.items : [];
      if (items.length === 1) {
        const it = items[0] || {};
        const status = String(it.status || "");
        return {
          pre: th("tool.plan_updated"),
          obj: `“${trunc(String(it.content ?? ""), 70)}”`,
          ...(status ? { post: th("tool.plan_status_suffix", { status: statusLabel(status) }) } : {}),
        };
      }
      return { pre: th("tool.plan_updated_count", { n: items.length }) };
    }
    case "send_message": {
      const { platform, tail } = messageTarget(String(a.target ?? ""));
      if (!tail) return { pre: th("tool.sent_message") };
      return { pre: th("tool.sent_message_to", { platform }), obj: tail };
    }
    case "web_search":
      return { pre: th("tool.searched_web"), obj: `“${trunc(String(a.query ?? ""), 60)}”` };
    case "web_fetch": {
      let host = String(a.url ?? "");
      try {
        host = new URL(host).host || host;
      } catch {
        /* keep raw */
      }
      return { pre: th("tool.read_web_page"), obj: trunc(host, 50) };
    }
    case "explore":
      return { pre: th("tool.explored"), obj: `“${trunc(String(a.task ?? a.prompt ?? ""), 60)}”` };
    case "load_skill":
      // SKILLS-SPEC §4.1 #4 — the trust line: the transcript always shows the moment a
      // skill's instructions were picked up, model-invoked or forced via /skill.
      return { pre: th("tool.used_skill"), obj: String(a.name ?? "") };
    case "ask_user":
      return { pre: th("tool.asked_question") };
    case "propose_plan":
      return { pre: th("tool.proposed_plan") };
    case "request_directory":
      return { pre: th("tool.requested_folder"), obj: String(a.path ?? "") };
    default: {
      const rest = trunc(shortArgs(a), 80);
      return { pre: th("tool.used_tool", { name }), ...(rest ? { post: th("tool.detail_suffix", { text: rest }) } : {}) };
    }
  }
}

// The approval card's headline (§35): the ask, phrased as the action being decided.
// run_shell leads with the model's own description ("Run a command — fetch stock data").
export function humanizeApprovalTitle(name: string, args: any): HumanLine {
  const a = args && typeof args === "object" ? args : {};
  switch (name) {
    case "write_file":
      return { pre: th("approval.write"), obj: baseName(String(a.path ?? th("tool.a_file"))) };
    case "replace_in_file":
    case "apply_patch":
    case "apply_unified_diff":
      return { pre: th("approval.edit"), obj: a.path ? baseName(String(a.path)) : th("tool.files") };
    case "run_shell": {
      const desc = typeof a.description === "string" && a.description.trim() ? a.description.trim() : "";
      return {
        pre: th("approval.run_command"),
        ...(desc ? { post: th("tool.detail_suffix", { text: lowerFirst(desc) }) } : {}),
      };
    }
    case "send_message": {
      const { tail } = messageTarget(String(a.target ?? ""));
      return tail ? { pre: th("approval.send_message_to"), obj: tail } : { pre: th("approval.send_message") };
    }
    case "send_file": {
      const { tail } = messageTarget(String(a.target ?? ""));
      return tail ? { pre: th("approval.send_file_to"), obj: tail } : { pre: th("approval.send_file") };
    }
    case "create_scheduled_task":
      return a.title
        ? { pre: th("approval.create_automation"), obj: `“${trunc(String(a.title), 60)}”` }
        : { pre: th("approval.create_automation_generic") };
    case "save_skill":
      // SKILLS-SPEC §5.2/§7: "Add", never "install"; destination is "your skills".
      return a.name
        ? { pre: th("approval.add_skill"), obj: String(a.name), post: th("approval.add_skill_post") }
        : { pre: th("approval.add_skill_generic") };
    // Egress cards (OPE-136 finding 5): name the destination in the headline; the full
    // URL/query renders in the card's expandable preview.
    case "web_fetch": {
      let host = "";
      try {
        host = new URL(String(a.url ?? "")).host;
      } catch {
        /* unparseable url → generic title; the preview still shows the raw string */
      }
      return host ? { pre: th("approval.fetch_from"), obj: host } : { pre: th("approval.fetch_page") };
    }
    case "web_search":
      return { pre: th("approval.web_search") };
    default:
      return { pre: th("approval.use_tool", { name }) };
  }
}

// Approvals with no executed tool call (typically declined): the ask, phrased as intent.
export function humanizeAsk(name: string, args: any): HumanLine {
  const a = args && typeof args === "object" ? args : {};
  switch (name) {
    case "run_shell":
      return { pre: th("ask.run"), obj: trunc(String(a.command ?? ""), 60) };
    case "write_file":
      return { pre: th("ask.write"), obj: baseName(String(a.path ?? th("tool.a_file"))) };
    case "replace_in_file":
    case "apply_patch":
    case "apply_unified_diff":
      return { pre: th("ask.edit"), obj: a.path ? baseName(String(a.path)) : th("tool.files") };
    case "send_message": {
      const { platform, tail } = messageTarget(String(a.target ?? ""));
      if (!tail) return { pre: th("ask.send_message") };
      return { pre: th("ask.message_to"), obj: tail, post: th("ask.message_on", { platform }) };
    }
    default:
      return { pre: th("ask.use_tool", { name }) };
  }
}
