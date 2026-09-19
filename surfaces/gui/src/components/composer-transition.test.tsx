import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { Composer } from "./Composer";

const MENU = {
  skills: [
    { name: "weekly-report", description: "Monday status report", scope: "global", enabled: true },
  ],
};

function stubFetch() {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      if (url.includes("/skills")) return { ok: true, json: async () => MENU } as Response;
      return { ok: true, json: async () => ({}) } as Response;
    }),
  );
}

const props = (extra: Partial<Parameters<typeof Composer>[0]> = {}) => ({
  mode: "interactive",
  model: "gpt-5.6-sol",
  running: false,
  connected: true,
  sessionId: "s1",
  workspace: "",
  contextWindow: 5,
  usage: { byModel: { m: { input: 300, output: 100, cache_read: 0, cache_write: 0 } } } as any,
  onSend: vi.fn(),
  onInterrupt: vi.fn(),
  onModeChange: vi.fn(),
  onModelChange: vi.fn(),
  ...extra,
});

const box = () => screen.getByPlaceholderText(/Ask your study partner/);

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("composer popovers carry entrance transitions", () => {
  it("skill popup fades up", async () => {
    stubFetch();
    render(<Composer {...props()} />);
    fireEvent.change(box(), { target: { value: "/" } });
    expect((await screen.findByTestId("skill-popup")).classList.contains("anim-fade-up")).toBe(
      true,
    );
  });

  it("mode menu pops up from its trigger", () => {
    stubFetch();
    render(<Composer {...props()} />);
    fireEvent.click(screen.getByLabelText("Mode"));
    expect(screen.getByTestId("mode-menu").classList.contains("menu-pop-up")).toBe(true);
  });

  it("usage popover pops up from its trigger", () => {
    stubFetch();
    render(<Composer {...props()} />);
    fireEvent.click(screen.getByTestId("usage-chip"));
    expect(screen.getByTestId("usage-popover").classList.contains("menu-pop-up")).toBe(true);
  });
});
