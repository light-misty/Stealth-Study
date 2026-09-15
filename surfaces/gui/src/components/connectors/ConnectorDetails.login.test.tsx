import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";

import { GmailDetail } from "./GmailDetail";
import { CalendarDetail } from "./CalendarDetail";
import { AccountsDetail } from "./AccountsDetail";
import { GithubDetail } from "./GithubDetail";
import type { CloudStatus, Connector } from "../../api";

// G-06: with sign-in off no connector surface may still tell the user to sign in —
// not in a setup note, not in a button tooltip, not in the relay status line.

function stubFetch(routes: { match: string; json: unknown }[]) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      for (const r of routes) {
        if (url.includes(r.match)) return { ok: true, json: async () => r.json } as Response;
      }
      return { ok: true, json: async () => ({}) } as Response;
    }),
  );
}

const signedOut = (): CloudStatus => ({
  signed_in: false,
  account: "",
  user_id: "",
  telemetry_enabled: false,
});

const connector = (over: Partial<Connector>): Connector =>
  ({
    name: "x",
    title: "X",
    icon: "x",
    blurb: "",
    auth: "oauth",
    two_way: false,
    channels: false,
    available: true,
    fields: [],
    instructions: [],
    connected: false,
    account: null,
    enabled: false,
    brand_color: "#000000",
    logo: "",
    allowed_users: [],
    tools: [],
    managed: true,
    managed_paused: false,
    accounts: [],
    ...over,
  }) as unknown as Connector;

const props = (c: Connector) => ({
  c,
  cloud: signedOut(),
  slack: null,
  onChanged: vi.fn(),
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  localStorage.removeItem("ocw.flag.login");
});

describe("Gmail / Calendar setup notes (G-06)", () => {
  it("omit the 'Requires cloud sign-in' note and the tooltip while the flag is off", () => {
    const { container: g } = render(
      <GmailDetail {...props(connector({ name: "gmail", title: "Gmail" }))} />,
    );
    expect(g.textContent).not.toContain("Requires cloud sign-in");
    expect(screen.getByTestId("add-account-btn").getAttribute("title")).toBe("");

    const { container: c } = render(
      <GmailDetail {...props(connector({ name: "google_calendar", title: "Google Calendar" }))} />,
    );
    expect(c.textContent).not.toContain("Requires cloud sign-in");
  });

  it("keep the note and tooltip out of CalendarDetail too", () => {
    const { container } = render(
      <CalendarDetail {...props(connector({ name: "google_calendar", title: "Google Calendar" }))} />,
    );
    expect(container.textContent).not.toContain("Requires cloud sign-in");
  });
});

describe("AccountsDetail add-account tooltip (G-06)", () => {
  it("carries no sign-in tooltip while the flag is off", () => {
    render(<AccountsDetail {...props(connector({ name: "notion", title: "Notion" }))} />);
    expect(screen.getByTestId("add-account-btn").getAttribute("title")).toBe("");
  });
});

describe("GitHub relay status line (G-06)", () => {
  it("reports the socket state instead of asking for a sign-in", async () => {
    stubFetch([
      { match: "/v1/subscriptions", json: { subscriptions: [] } },
      {
        match: "/v1/connectors/github/status",
        json: { signed_in: false, relay: { state: "offline" }, installs: {} },
      },
    ]);
    render(
      <GithubDetail
        {...props(connector({ name: "github", title: "GitHub", mode: "relay", connected: true }))}
      />,
    );
    const badge = await screen.findByTestId("github-mode-badge");
    expect(badge.textContent).not.toContain("Sign in");
    expect(badge.textContent).toContain("Offline");
  });
});

describe("the same surfaces still work when the flag is on (reversibility)", () => {
  it("restores the setup notes and tooltips", () => {
    localStorage.setItem("ocw.flag.login", "1");
    render(<GmailDetail {...props(connector({ name: "gmail", title: "Gmail" }))} />);
    expect(screen.getByTestId("add-account-btn").getAttribute("title")).toBe(
      "Sign in to OpenWorker Cloud first",
    );
  });
});
