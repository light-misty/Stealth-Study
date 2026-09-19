import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { ScheduledView } from "./ScheduledView";
import { getAutomations, type Automation } from "../api";

vi.mock("../api", () => ({
  announceAutomationsChanged: vi.fn(),
  createAutomation: vi.fn(),
  deleteAutomation: vi.fn(),
  getAutomation: vi.fn(),
  getAutomations: vi.fn().mockResolvedValue([]),
  markAutomationSeen: vi.fn(),
  updateAutomation: vi.fn(),
}));

vi.mock("./AutomationQuickstart", () => ({
  AutomationQuickstart: () => <div data-testid="automation-quickstart" />,
}));

vi.mock("./IntegrationsView", () => ({
  PanelHead: ({ title, sub }: { title: string; sub: string }) => (
    <header>
      <h1>{title}</h1>
      <p>{sub}</p>
    </header>
  ),
}));

afterEach(cleanup);

describe("ScheduledView empty state", () => {
  it("renders translated emphasis as a strong element, not literal markup", () => {
    const { container } = render(
      <ScheduledView onOpenRun={vi.fn()} onRunNow={vi.fn()} />,
    );

    expect(
      screen.getByText("+ New automation", { selector: "strong" }),
    ).toBeTruthy();
    expect(container.textContent).not.toContain("<strong>");
  });
});

describe("ScheduledView task cards", () => {
  it("deepen the hover border for contrast", async () => {
    const task: Automation = {
      id: "t1",
      title: "Weekly digest",
      instructions: "do it",
      schedule: "Mondays at 09:00",
      workspace: "w",
      agent: "chat",
      enabled: true,
      next_run: null,
      last_run: null,
      last_status: null,
      run_count: 0,
      notify_on_completion: false,
      always_allowed: [],
    };
    vi.mocked(getAutomations).mockResolvedValue([task]);
    render(<ScheduledView onOpenRun={vi.fn()} onRunNow={vi.fn()} />);

    const card = (await screen.findByText("Weekly digest")).closest(".sched-card");
    expect(card?.className.split(" ")).toContain("hover:border-lineStronger");
    expect(card?.className.split(" ")).not.toContain("hover:border-lineStrong");
  });
});
