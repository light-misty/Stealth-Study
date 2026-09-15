import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";

vi.mock("../api", () => ({
  cloudLogin: vi.fn(),
  connectManaged: vi.fn(),
  connectConnector: vi.fn(),
  getCloudStatus: vi.fn().mockResolvedValue({ signed_in: false, account: "", user_id: "" }),
  waitForCloudSignIn: vi.fn(() => () => {}),
  announceCloudChanged: vi.fn(),
  updateConnectorTools: vi.fn(),
}));

vi.mock("../connectors/ConnectorIcon", () => ({
  ConnectorBadge: () => <span />,
}));

import { CloudSignInInline, CloudStatusPending } from "./connectors/CloudSignIn";
import { AddConnectionModal } from "./connectors/AddConnectionModal";
import { ConnectSetup } from "./ManageTabs";
import type { CloudStatus, Connector } from "../api";

const connector = (): Connector =>
  ({
    name: "notion",
    title: "Notion",
    icon: "notion",
    blurb: "Docs and databases.",
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
  }) as unknown as Connector;

const signedOut = (): CloudStatus => ({
  signed_in: false,
  account: "",
  user_id: "",
  telemetry_enabled: false,
});

afterEach(() => {
  cleanup();
  localStorage.removeItem("ocw.flag.login");
});

describe("CloudSignInInline (G-06)", () => {
  it("renders the real sign-in button when the flag is on", () => {
    localStorage.setItem("ocw.flag.login", "1");
    render(<CloudSignInInline />);
    expect(screen.getByTestId("inline-cloud-sign-in")).toBeTruthy();
  });

  it("renders nothing when the flag is off", () => {
    const { container } = render(<CloudSignInInline />);
    expect(screen.queryByTestId("inline-cloud-sign-in")).toBeNull();
    expect(container.textContent).toBe("");
  });

  it("leaves the unknown-status pane alone — it is not a sign-in affordance", () => {
    render(<CloudStatusPending />);
    expect(screen.getByTestId("cloud-status-pending")).toBeTruthy();
  });
});

describe("AddConnectionModal one-click panes (G-06)", () => {
  it("offers no sign-in button and falls through to pending", () => {
    render(
      <AddConnectionModal
        c={connector()}
        cloud={signedOut()}
        onClose={vi.fn()}
        onChanged={vi.fn()}
      />,
    );
    expect(screen.queryByTestId("inline-cloud-sign-in")).toBeNull();
  });

  it("shows the sign-in button again when the flag is on", () => {
    localStorage.setItem("ocw.flag.login", "1");
    render(
      <AddConnectionModal
        c={connector()}
        cloud={signedOut()}
        onClose={vi.fn()}
        onChanged={vi.fn()}
      />,
    );
    expect(screen.getByTestId("inline-cloud-sign-in")).toBeTruthy();
  });
});

describe("ConnectSetup managed block (G-06)", () => {
  it("drops the whole managed pane — not just the button — when the flag is off", () => {
    const { container } = render(
      <ConnectSetup c={connector()} cloud={signedOut()} onConnected={vi.fn()} />,
    );
    // Nothing left of the cloud pane: no dead "checking" placeholder either.
    expect(screen.queryByTestId("managed-connect")).toBeNull();
    expect(screen.queryByTestId("inline-cloud-sign-in")).toBeNull();
    expect(screen.queryByTestId("cloud-status-pending")).toBeNull();
    expect(container.textContent).not.toContain("Sign in");
  });

  it("shows the sign-in ask when the flag is on", () => {
    localStorage.setItem("ocw.flag.login", "1");
    render(<ConnectSetup c={connector()} cloud={signedOut()} onConnected={vi.fn()} />);
    expect(screen.getByTestId("managed-connect")).toBeTruthy();
    expect(screen.getByTestId("inline-cloud-sign-in")).toBeTruthy();
  });
});
