import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { InboxView } from "./InboxView";
import type { InboxItem } from "../api";

// The Inbox page must surface EVERY pending item the sidebar's attention count advertises,
// an attended session's inline ask_user prompt included — the component contract behind the
// visibility fix (the server no longer filters inline items out of the cross-session list).

const INLINE_QUESTION: InboxItem = {
  id: "inb-q1",
  session_id: "s-1",
  kind: "question",
  title: "Which environment should I restart?",
  body: "",
  state: "pending",
  resolution: null,
  inbox: "default",
  created_at: "2026-09-19T08:00:00+00:00",
  resolved_at: null,
  visibility: "inline",
  options: ["staging", "production"],
  allow_text: true,
  multi: false,
  header: "",
  session_title: "Attended chat",
  session_agent: "cowork",
  session_workspace: "",
  session_exists: true,
};

const PENDING_APPROVAL: InboxItem = {
  id: "inb-a1",
  session_id: "s-2",
  kind: "approval",
  title: "Approve: run_shell",
  body: "rm -rf build/",
  state: "pending",
  resolution: null,
  inbox: "default",
  created_at: "2026-09-19T08:05:00+00:00",
  resolved_at: null,
  visibility: "inbox",
  session_title: "Unattended run",
  session_agent: "cowork",
  session_workspace: "",
  session_exists: true,
};

function stubFetch(routes: { match: string; json?: unknown; reject?: boolean }[]) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      for (const r of routes) {
        if (url.includes(r.match)) {
          if (r.reject) return Promise.reject(new Error("network down"));
          return { ok: true, json: async () => r.json } as Response;
        }
      }
      return { ok: true, json: async () => ({}) } as Response;
    }),
  );
}

function stubInbox(items: InboxItem[]) {
  stubFetch([
    { match: "/v1/inbox/routing", json: { bindings: [] } },
    { match: "/v1/inbox", json: { items } },
    { match: "/v1/unrouted", json: { items: [] } },
    { match: "/v1/personas", json: { personas: [] } },
    { match: "/v1/connectors", json: { connectors: [] } },
    { match: "/v1/channels/recent", json: { channels: [] } },
  ]);
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("InboxView", () => {
  it("lists an attended session's inline pending question", async () => {
    stubInbox([INLINE_QUESTION]);
    render(<InboxView onOpenSession={vi.fn()} />);
    expect(await screen.findByText("Which environment should I restart?")).toBeTruthy();
    expect(screen.getByTestId("inbox-tab-pending").textContent).toContain("1");
  });

  it("kind chips separate questions from approvals", async () => {
    stubInbox([INLINE_QUESTION, PENDING_APPROVAL]);
    render(<InboxView onOpenSession={vi.fn()} />);
    await screen.findByText("Which environment should I restart?");
    expect(screen.getByText("Approve: run_shell")).toBeTruthy();

    const filters = screen.getByTestId("inbox-filters");
    fireEvent.click(within(filters).getByText("Questions"));
    expect(screen.queryByText("Approve: run_shell")).toBeNull();
    expect(screen.getByText("Which environment should I restart?")).toBeTruthy();

    fireEvent.click(within(filters).getByText("Approvals"));
    expect(screen.getByText("Approve: run_shell")).toBeTruthy();
    expect(screen.queryByText("Which environment should I restart?")).toBeNull();
  });

  it("renders the empty state when the inbox request fails", async () => {
    stubFetch([{ match: "/v1/inbox", reject: true }]);
    render(<InboxView onOpenSession={vi.fn()} />);
    expect(await screen.findByText("Nothing pending.")).toBeTruthy();
  });
});
