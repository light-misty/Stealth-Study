import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";

vi.mock("../api", () => ({
  codexAuthStatus: vi.fn().mockResolvedValue({ signed_in: false, authorizing: false }),
  codexAuthStart: vi.fn(),
  codexAuthSignOut: vi.fn(),
}));

vi.mock("../tauri", () => ({ openExternal: vi.fn() }));

import { ProviderForm, type ProviderSetupState } from "./ProviderSetup";

const oauthState = (): ProviderSetupState =>
  ({
    info: {
      name: "codex",
      title: "Codex",
      auth: "oauth",
      fields: [],
      needs_key: false,
    },
    sel: "codex",
    fields: {},
    setFieldValue: vi.fn(),
    dirty: false,
    secretFilled: false,
    credentialed: false,
    savedState: false,
    verify: { state: "idle" },
    showEndpoint: false,
    setShowEndpoint: vi.fn(),
    providers: [],
    ordered: [],
    keylessOk: new Set<string>(),
    openProvider: vi.fn(),
    cancelBackTimer: vi.fn(),
    runTestAndSave: vi.fn(),
    removeKey: vi.fn(),
    saveField: vi.fn(),
    fieldSaved: null,
    statusFor: () => null,
    refreshProviders: vi.fn().mockResolvedValue(undefined),
    backToGallery: vi.fn(),
  }) as unknown as ProviderSetupState;

afterEach(() => {
  cleanup();
  localStorage.removeItem("ocw.flag.login");
});

describe("ProviderForm OAuth pane (G-06)", () => {
  it("hides the browser sign-in button while the flag is off", () => {
    render(<ProviderForm ps={oauthState()} tp="ob" />);
    expect(screen.queryByTestId("ob-oauth-signin")).toBeNull();
  });

  it("shows the browser sign-in button when the flag is on", () => {
    localStorage.setItem("ocw.flag.login", "1");
    render(<ProviderForm ps={oauthState()} tp="ob" />);
    expect(screen.getByTestId("ob-oauth-signin")).toBeTruthy();
  });
});
