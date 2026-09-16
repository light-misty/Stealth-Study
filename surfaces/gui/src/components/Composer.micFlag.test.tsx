// INF-07 flag double-state for the composer mic (08 §2.1 F-1/F-3): with the voice flag
// shipped off, the mic button — the app's single physical voice entry (04 §4.7) — never
// renders even in the desktop app, so no recording can start and no microphone permission
// is ever requested; the flag flips it straight back.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { Composer } from "./Composer";

const READY = {
  recording: false,
  model_installed: true,
  model_verified: true,
  test_passed: true,
  download_in_progress: false,
  model_name: "Whisper Base English (local)",
  model_bytes: 147964211,
  supported: true,
  device_summary: "macOS 15 · Apple Silicon",
  compatibility_reason: null,
};

let invoke: ReturnType<typeof vi.fn>;

const props = () => ({
  mode: "interactive" as const,
  model: "gpt-5.6-sol",
  running: false,
  connected: true,
  onSend: vi.fn(),
  onInterrupt: vi.fn(),
  onModeChange: vi.fn(),
  onModelChange: vi.fn(),
});

beforeEach(() => {
  invoke = vi.fn(async (cmd: string) => (cmd === "get_dictation_status" ? READY : null));
  (globalThis as any).__TAURI__ = { core: { invoke }, event: { listen: async () => () => {} } };
});

afterEach(() => {
  cleanup();
  delete (globalThis as any).__TAURI__;
  localStorage.removeItem("ocw.flag.voice");
});

describe("Composer mic vs the voice flag (04 §4.7)", () => {
  it("renders no mic in the desktop app while the flag ships off (F-1)", async () => {
    render(<Composer {...props()} />);
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(screen.queryByLabelText(/dictation|Voice Input/i)).toBeNull();
  });

  it("is force-hidden even with ocw.flag.voice = 0", async () => {
    localStorage.setItem("ocw.flag.voice", "0");
    render(<Composer {...props()} />);
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(screen.queryByLabelText(/dictation|Voice Input/i)).toBeNull();
  });

  it("brings the mic back with ocw.flag.voice = 1 (F-3)", async () => {
    localStorage.setItem("ocw.flag.voice", "1");
    render(<Composer {...props()} />);
    expect(await screen.findByLabelText("Start dictation")).toBeTruthy();
  });
});
