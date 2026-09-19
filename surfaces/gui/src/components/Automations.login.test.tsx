import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

vi.mock("../api", () => ({
  cloudLogin: vi.fn(),
  connectManaged: vi.fn(),
  getCloudStatus: vi.fn().mockResolvedValue({ signed_in: false, account: "", user_id: "" }),
  getConnectors: vi.fn().mockResolvedValue([]),
  getRecentChannels: vi.fn().mockResolvedValue([]),
  waitForCloudSignIn: vi.fn(() => () => {}),
}));

vi.mock("../connectors/ConnectorIcon", () => ({
  ConnectorBadge: () => <span />,
}));

import { AutomationQuickstart } from "./AutomationQuickstart";

// jsdom has no layout engine, so scrollIntoView is absent; the component calls it
// whenever a template is picked. Stubbing it keeps the assertion about sign-in.
beforeAll(() => {
  Element.prototype.scrollIntoView = vi.fn();
});

const pickGithubTemplate = async () => {
  render(<AutomationQuickstart busy={false} onCreate={vi.fn()} />);
  fireEvent.click(await screen.findByTestId("qs-template-github"));
  await screen.findByTestId("ob-connect-slack");
};

afterEach(() => {
  cleanup();
  localStorage.removeItem("ocw.flag.login");
});

describe("AutomationQuickstart template cards", () => {
  it("deepen the hover border for contrast", async () => {
    render(<AutomationQuickstart busy={false} onCreate={vi.fn()} />);
    const card = await screen.findByTestId("qs-template-github");
    expect(card.className.split(" ")).toContain("hover:border-lineStronger");
    expect(card.className.split(" ")).not.toContain("hover:border-lineStrong");
  });
});

describe("AutomationQuickstart cloud sign-in pane (G-06)", () => {
  it("never offers a sign-in pane while the flag is off", async () => {
    await pickGithubTemplate();
    expect(screen.queryByTestId("ob-cloudpane")).toBeNull();
    expect(screen.queryByTestId("ob-cloud-signin")).toBeNull();
  });

  it("clicking a connect row does not open a sign-in pane when off", async () => {
    await pickGithubTemplate();
    fireEvent.click(screen.getByTestId("ob-connect-slack"));
    await waitFor(() => expect(screen.getByTestId("ob-connect-slack")).toBeTruthy());
    expect(screen.queryByTestId("ob-cloudpane")).toBeNull();
    expect(screen.queryByTestId("ob-cloud-signin")).toBeNull();
  });

  it("shows the sign-in pane again when the flag is on", async () => {
    localStorage.setItem("ocw.flag.login", "1");
    await pickGithubTemplate();
    fireEvent.click(screen.getByTestId("ob-connect-slack"));
    await waitFor(() => expect(screen.getByTestId("ob-cloudpane")).toBeTruthy());
    expect(screen.getByTestId("ob-cloud-signin")).toBeTruthy();
  });
});
