import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";

vi.mock("../campus/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../campus/api")>();
  return {
    ...actual,
    getAppState: vi.fn(),
    patchAppState: vi.fn(),
  };
});

import * as api from "../campus/api";
import { SettingsView } from "./SettingsView";

// INF-07 flag double-state regression at the Settings surface (08 §2.1 F-1/F-3/F-4):
// with the voice flag shipped off, the voice tab is filtered out while every other
// existing tab (and the new campus tab) stays reachable; the flag flips it back. The
// sections all degrade gracefully offline, so a rejecting fetch keeps this a pure
// component test.

const apiMock = api as unknown as Record<string, ReturnType<typeof vi.fn>>;

function goOffline() {
  // A fetch that never settles: sections keep their loading state, nothing throws, and
  // the assertions below only depend on the nav and the flag — not on loaded data.
  vi.stubGlobal("fetch", vi.fn(async () => new Promise<Response>(() => {})));
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  localStorage.removeItem("ocw.flag.voice");
});

describe("SettingsView flag double-state (INF-07)", () => {
  it("hides the voice tab while the voice flag ships off (F-1)", () => {
    goOffline();
    render(<SettingsView />);
    expect(screen.queryByText("Voice input")).toBeNull();
  });

  it("keeps the campus tab visible regardless of the flags and renders its panel", async () => {
    goOffline();
    apiMock.getAppState.mockResolvedValue({ active_profile_id: null, settings: {} });
    render(<SettingsView />);

    fireEvent.click(screen.getByText("Exam prep"));
    await waitFor(() => expect(screen.getByTestId("campus-settings")).toBeTruthy());
    expect(screen.getByTestId("campus-settings-daily-minutes")).toBeTruthy();
  });

  it("brings the voice tab back when the flag is flipped on (F-3)", () => {
    goOffline();
    localStorage.setItem("ocw.flag.voice", "1");
    render(<SettingsView />);

    fireEvent.click(screen.getByText("Voice input"));
    expect(
      screen.getByText("Voice Input setup is available in the OpenWorker desktop app."),
    ).toBeTruthy();
  });

  it("keeps every existing tab reachable with the flags off (F-4)", () => {
    goOffline();
    render(<SettingsView />);
    const nav = within(screen.getByRole("navigation"));

    for (const label of ["General", "Models", "Context optimization", "Skills", "Memory", "Coworkers"]) {
      fireEvent.click(nav.getByText(label));
      expect(nav.queryByText("Voice input")).toBeNull();
    }
    expect(nav.getByText("Exam prep")).toBeTruthy();
  });
});
