import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { Sidebar } from "./Sidebar";
import type { SessionInfo } from "../types";

// The bottom-left anchor (§26). With cloud sign-in off (G-06) it is a plain "More"
// button: no "Not signed in" label, no sign-in item inside the menu it opens.

function stubFetch(routes: { match: string; method?: string; json: unknown }[]) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const method = (init?.method || "GET").toUpperCase();
      for (const r of routes) {
        if (url.includes(r.match) && (!r.method || r.method === method)) {
          return { ok: true, json: async () => r.json } as Response;
        }
      }
      return { ok: true, json: async () => ({}) } as Response;
    }),
  );
}

const SESSIONS: SessionInfo[] = [
  {
    session_id: "s-1",
    title: "hi there",
    workspace: "",
    agent: "cowork",
    model: "m",
    mode: "interactive",
    updated_at: "2026-06-29",
    messages: 1,
  },
];

const baseProps = {
  agent: "cowork",
  workspace: "",
  surfaces: { cowork: true, chat: false, code: false },
  sessions: SESSIONS,
  projects: [],
  activeSession: "s-1",
  onSwitchAgent: vi.fn(),
  onNewSession: vi.fn(),
  onSelectSession: vi.fn(),
  onNewProject: vi.fn(),
  onRenameSession: vi.fn(),
  onDeleteSession: vi.fn(),
  onArchiveSession: vi.fn(),
  onTogglePin: vi.fn(),
  onManage: vi.fn(),
  onOpenPersona: vi.fn(),
  onOpenScheduled: vi.fn(),
  onOpenAutomation: vi.fn(),
  onOpenCampus: vi.fn(),
  onOpenIntegrations: vi.fn(),
  onOpenAudit: vi.fn(),
  onOpenInbox: vi.fn(),
  scheduledActive: false,
  campusActive: null,
  integrationsActive: false,
  auditActive: false,
  inboxActive: false,
};

const stubRoutes = [
  { match: "/v1/personas", method: "GET", json: { personas: [] } },
  { match: "/v1/settings", method: "GET", json: { nav_layout: "flat" } },
  { match: "/v1/cloud/status", method: "GET", json: { signed_in: false, account: "", user_id: "" } },
];

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  localStorage.removeItem("ocw.flag.login");
});

const openMenu = () => fireEvent.click(screen.getByTestId("account-row"));

describe("Sidebar bottom-left anchor (G-06)", () => {
  it("is a plain More button with no sign-in affordance when the flag is off", async () => {
    stubFetch(stubRoutes);
    render(<Sidebar {...baseProps} />);
    await screen.findByText("hi there");

    const row = screen.getByTestId("account-row");
    expect(row.textContent).toContain("More");
    expect(row.textContent).not.toContain("Not signed in");
    expect(row.getAttribute("aria-label")).toBe("More");

    openMenu();
    expect(screen.getByTestId("account-menu")).toBeTruthy();
    expect(screen.queryByTestId("account-sign-in")).toBeNull();
    expect(screen.queryByText(/one-click connections need/)).toBeNull();
    expect(screen.queryByText("Sign in to Stealth Study")).toBeNull();
    // The menu is still the way to Inbox / Connectors / Settings / Activity.
    expect(screen.getByText("Inbox")).toBeTruthy();
    expect(screen.getByText("Settings")).toBeTruthy();
  });

  it("keeps only the label in the plain More row with no leading three-dot icon", async () => {
    stubFetch(stubRoutes);
    render(<Sidebar {...baseProps} />);
    await screen.findByText("hi there");

    const row = screen.getByTestId("account-row");
    expect(row.querySelectorAll("svg")).toHaveLength(1);
  });

  it("falls back to the signed-out account row and sign-in item when the flag is on", async () => {
    localStorage.setItem("ocw.flag.login", "1");
    stubFetch(stubRoutes);
    render(<Sidebar {...baseProps} />);
    await screen.findByText("hi there");

    const row = screen.getByTestId("account-row");
    expect(row.textContent).toContain("Not signed in");
    expect(row.textContent).not.toContain("More");

    openMenu();
    expect(screen.getByTestId("account-sign-in")).toBeTruthy();
    expect(screen.getByText(/one-click connections need/)).toBeTruthy();
  });
});
