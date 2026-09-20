import { defineConfig, devices } from "@playwright/test";

// LIVE smoke config — runs against the REAL backend (stealthstudy-server on :8765) and a REAL model.
// Deliberately separate from playwright.config.ts (testDir ./e2e), so `npm run e2e` and CI never
// pick these up. Run manually with `npm run e2e:live` when the backend is up and a model is set.
// Nondeterministic and costs a few model tokens per run — a confidence smoke, not an assertion gate.
const PORT = 5199;

export default defineConfig({
  testDir: "./e2e-live",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"]],
  // Model + tool execution take real time.
  timeout: 180_000,
  use: {
    baseURL: `http://localhost:${PORT}`,
    trace: "on-first-retry",
    // Without an action timeout a selector that never appears waits for the whole test timeout
    // (or forever, when `test.timeout` is disabled), which reads as a hang instead of a failure.
    // Model latency happens while awaiting a response, not while an action becomes actionable, so
    // 30s is generous for a click/fill on a live UI.
    actionTimeout: 30_000,
  },
  expect: { timeout: 15_000 },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    // The dev server's default API base is 127.0.0.1:8765 — i.e. the real backend (no mocks here).
    command: `npm run dev -- --port ${PORT} --strictPort`,
    url: `http://localhost:${PORT}`,
    reuseExistingServer: true,
    timeout: 120_000,
  },
});
