import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render } from "@testing-library/react";

vi.mock("../api", () => ({
  announceAutomationsChanged: vi.fn(),
  createAutomation: vi.fn(),
  deleteAutomation: vi.fn(),
  getAutomation: vi.fn().mockResolvedValue(null),
  getAutomations: vi.fn().mockResolvedValue([]),
  getAudit: vi.fn().mockResolvedValue([]),
  getConnectors: vi.fn().mockResolvedValue([]),
  getInbox: vi.fn().mockResolvedValue([]),
  getInboxRouting: vi.fn().mockResolvedValue(null),
  getPersonaDetail: vi.fn().mockResolvedValue({
    id: "ops",
    name: "Ops Coworker",
    icon: "wrench",
    tagline: "Operate and investigate",
    description: "A careful, methodical operations engineer.",
    media: [],
    builtin: true,
    group: "general",
    enabled: true,
    surfaced: true,
    default: false,
    tools: ["files"],
    recommended_models: [],
    default_permission_mode: "interactive",
    workspace: null,
    recommends: [],
    default_connections: [],
  }),
  getPersonaMediaUrl: vi.fn(),
  getPersonas: vi.fn().mockResolvedValue([]),
  getRecentChannels: vi.fn().mockResolvedValue([]),
  getSettings: vi.fn().mockResolvedValue({}),
  getTrustedWorkspaces: vi.fn().mockResolvedValue([]),
  getUnrouted: vi.fn().mockResolvedValue([]),
  markAutomationSeen: vi.fn(),
  resolveInboxItem: vi.fn(),
  setPersonaConnection: vi.fn(),
  setPersonaEnabled: vi.fn(),
  updateAutomation: vi.fn(),
  updatePersona: vi.fn(),
  exportPersona: vi.fn(),
  deletePersona: vi.fn(),
}));

vi.mock("../tauri", () => ({
  chooseFolder: vi.fn(),
  checkForUpdate: vi.fn().mockResolvedValue(null),
  isTauri: () => false,
  getAutostart: vi.fn().mockResolvedValue(false),
  getKeepAwake: vi.fn().mockResolvedValue(false),
  getDictationStatus: vi.fn().mockResolvedValue({}),
}));

vi.mock("../connectors/ConnectorIcon", () => ({
  ConnectorBadge: () => <span />,
}));

vi.mock("./connectors/ConnectorsSection", () => ({
  ConnectorsSection: () => <div data-testid="connectors-section" />,
}));

vi.mock("./AutomationQuickstart", () => ({
  AutomationQuickstart: () => <div data-testid="automation-quickstart" />,
}));

vi.mock("./IntegrationsView", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./IntegrationsView")>();
  return {
    ...actual,
    PanelHead: ({ title, sub }: { title: string; sub: string }) => (
      <header>
        <h1>{title}</h1>
        <p>{sub}</p>
      </header>
    ),
  };
});

import { AuditView } from "./AuditView";
import { InboxView } from "./InboxView";
import { IntegrationsView } from "./IntegrationsView";
import { PersonaView } from "./PersonaView";
import { ScheduledView } from "./ScheduledView";
import { SettingsView } from "./SettingsView";

const mainOf = (container: HTMLElement) => container.querySelector("main");

afterEach(cleanup);

describe("top-level surface roots carry the unified entrance transition", () => {
  it("ScheduledView", () => {
    const { container } = render(
      <ScheduledView onOpenRun={vi.fn()} onRunNow={vi.fn()} />,
    );
    expect(mainOf(container)?.classList.contains("surface-view")).toBe(true);
  });

  it("IntegrationsView", () => {
    const { container } = render(<IntegrationsView />);
    expect(mainOf(container)?.classList.contains("surface-view")).toBe(true);
  });

  it("AuditView", () => {
    const { container } = render(<AuditView />);
    expect(mainOf(container)?.classList.contains("surface-view")).toBe(true);
  });

  it("InboxView", () => {
    const { container } = render(<InboxView onOpenSession={vi.fn()} />);
    expect(mainOf(container)?.classList.contains("surface-view")).toBe(true);
  });

  it("PersonaView", () => {
    const { container } = render(
      <PersonaView personaId="ops" onBack={vi.fn()} onOpenIntegrations={vi.fn()} />,
    );
    expect(mainOf(container)?.classList.contains("surface-view")).toBe(true);
  });

  it("SettingsView fades its pane on tab remount", () => {
    const { container } = render(<SettingsView />);
    expect(container.querySelector(".anim-fade-up")).not.toBeNull();
  });
});
