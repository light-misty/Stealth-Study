import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";

vi.mock("./api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./api")>();
  const oldSession = {
    session_id: "sess-old",
    title: "Old chat",
    workspace: "",
    agent: "cowork",
    model: "test-model",
    mode: "auto",
    updated_at: new Date().toISOString(),
    messages: 2,
  };
  return {
    ...actual,
    getHealth: vi.fn().mockResolvedValue({ model: "test-model", default_workspace: null }),
    getSessions: vi.fn().mockResolvedValue([oldSession]),
    getRecentWorkspaces: vi.fn().mockResolvedValue([]),
    getSessionMessages: vi
      .fn()
      .mockResolvedValue([
        { role: "user", content: "old question" },
        { role: "assistant", content: "old session answer" },
      ]),
    getSettings: vi.fn().mockResolvedValue({ models: [], onboarded: true }),
    getPersonas: vi.fn().mockResolvedValue([]),
    getInbox: vi.fn().mockResolvedValue([]),
    getUnattended: vi.fn().mockResolvedValue([]),
    connectEvents: vi.fn(() => () => {}),
    announceInboxUnlock: vi.fn(),
    announceAutomationsChanged: vi.fn(),
    announceMemoryChanged: vi.fn(),
    Session: class {
      close() {}
      userMessage() {}
    },
  };
});

import { App } from "./App";
import { getSessionMessages } from "./api";

afterEach(cleanup);

describe("App boot", () => {
  it("opens a fresh session page on boot instead of resuming the most recent conversation", async () => {
    render(<App />);
    await waitFor(
      () => expect(screen.getByText("What are we studying today?")).toBeTruthy(),
      { timeout: 10000 },
    );
    expect(getSessionMessages).not.toHaveBeenCalled();
    expect(screen.queryByText("old session answer")).toBeNull();
  }, 15000);
});
