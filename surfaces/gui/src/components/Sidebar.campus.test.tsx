import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { Sidebar } from "./Sidebar";
import type { SessionInfo } from "../types";

// 04 §4.3 (intrusion point #3): the three campus stations are first-class nav rows after
// Automations — never entries in the SURFACES persona fallback. Labels go through
// campus.nav.* (04 §7.2 folded the sidebar.campus_* sketch into that namespace), the
// active track carries the same row highlight as nav-automations, and a click hands the
// track back to the app via onOpenCampus.

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

const TRACKS = ["cet", "kaoyan", "cert"] as const;

const stubRoutes = [
  { match: "/v1/personas", method: "GET", json: { personas: [] } },
  { match: "/v1/settings", method: "GET", json: { nav_layout: "flat" } },
  { match: "/v1/cloud/status", method: "GET", json: { signed_in: false, account: "", user_id: "" } },
];

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("Sidebar campus nav rows (04 §4.3)", () => {
  it("renders one nav row per station with stable test ids", () => {
    stubFetch(stubRoutes);
    render(<Sidebar {...baseProps} />);
    for (const track of TRACKS) {
      expect(screen.getByTestId(`nav-campus-${track}`)).toBeTruthy();
    }
  });

  it("keeps the stations out of the persona accordion fallback", () => {
    stubFetch(stubRoutes);
    render(<Sidebar {...baseProps} />);

    // The three rows sit together in the fixed nav block, right after Automations —
    // never inside the scroll area that hosts the persona accordions (04 §4.3's warning
    // about the SURFACES fallback at the top of the file).
    const wrap = (id: string) => screen.getByTestId(id).closest("div");
    const campusWrap = wrap("nav-campus-cet");
    expect(campusWrap).toBeTruthy();
    for (const track of TRACKS) {
      expect(wrap(`nav-campus-${track}`)).toBe(campusWrap);
    }
    expect(wrap("nav-automations")!.nextElementSibling).toBe(campusWrap);

    const scrollArea = document.querySelector("div.flex-1.overflow-y-auto");
    expect(scrollArea).toBeTruthy();
    for (const track of TRACKS) {
      expect(scrollArea!.contains(screen.getByTestId(`nav-campus-${track}`))).toBe(false);
    }
  });

  it("highlights only the active track's row", () => {
    stubFetch(stubRoutes);
    render(<Sidebar {...baseProps} campusActive="kaoyan" />);
    const activeRow = (id: string) =>
      screen.getByTestId(id).className.match(/(?:^|\s)bg-chromeHover(?:\s|$)/) !== null;
    expect(activeRow("nav-campus-kaoyan")).toBe(true);
    for (const track of TRACKS.filter((t) => t !== "kaoyan")) {
      expect(activeRow(`nav-campus-${track}`)).toBe(false);
    }
  });

  it("hands the clicked track back through onOpenCampus", () => {
    stubFetch(stubRoutes);
    const onOpenCampus = vi.fn();
    render(<Sidebar {...baseProps} onOpenCampus={onOpenCampus} />);
    fireEvent.click(screen.getByTestId("nav-campus-cet"));
    fireEvent.click(screen.getByTestId("nav-campus-kaoyan"));
    fireEvent.click(screen.getByTestId("nav-campus-cert"));
    expect(onOpenCampus.mock.calls).toEqual([["cet"], ["kaoyan"], ["cert"]]);
  });
});
