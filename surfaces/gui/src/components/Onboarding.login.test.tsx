import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { Onboarding } from "./Onboarding";

vi.mock("../api", () => ({
  cloudLogin: vi.fn(),
  connectManaged: vi.fn(),
  getCloudStatus: vi.fn().mockResolvedValue({ signed_in: false, account: null }),
  getConnectors: vi.fn().mockResolvedValue([]),
  setOnboarded: vi.fn(),
}));

vi.mock("../connectors/ConnectorIcon", () => ({
  ConnectorBadge: () => <span />,
}));

vi.mock("../providers/ProviderSetup", () => ({
  ProviderCards: () => <div data-testid="provider-cards" />,
  ProviderForm: () => <div data-testid="provider-form" />,
  useProviderSetup: () => ({
    providers: [],
    keylessOk: new Set(["local"]),
    sel: null,
    dirty: false,
    secretFilled: false,
    credentialed: false,
    verify: { state: "idle" },
    cancelBackTimer: vi.fn(),
    runTestAndSave: vi.fn().mockResolvedValue(true),
  }),
}));

const openStepOne = async () => {
  render(<Onboarding onDone={vi.fn()} />);
  fireEvent.click(await screen.findByTestId("ob-continue"));
  await screen.findByTestId("ob-step-tools");
};

afterEach(() => {
  cleanup();
  localStorage.removeItem("ocw.flag.login");
});

describe("Onboarding cloud sign-in band (G-06)", () => {
  it("renders the sign-in band when showLogin() is on", async () => {
    localStorage.setItem("ocw.flag.login", "1");
    await openStepOne();

    expect(screen.getByTestId("ob-cloud-signin")).toBeTruthy();
    expect(screen.getByText("Sign in for one-click connections")).toBeTruthy();
  });

  it("hides the sign-in band when showLogin() is off but keeps step one usable", async () => {
    await openStepOne();

    expect(screen.getByTestId("ob-step-tools")).toBeTruthy();
    expect(screen.queryByTestId("ob-cloud-signin")).toBeNull();
    expect(screen.queryByTestId("ob-tools-signedin")).toBeNull();
    // The skip button must not mention signing in when there is no sign-in to skip.
    const skip = screen.getByTestId("ob-tools-skip");
    expect(skip).toBeTruthy();
    expect(skip.textContent).toBe("Next");
  });
});
