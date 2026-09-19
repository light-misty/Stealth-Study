// @vitest-environment node
import { afterEach, describe, expect, it } from "vitest";
import net from "node:net";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import viteConfig from "../vite.config.ts";

type ConfigEnv = { command: "serve" | "build"; mode: string };

type ResolvedConfig = {
  server: { port: number; strictPort: boolean };
  define: Record<string, string>;
};

function listenOn(port: number): Promise<net.Server> {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.once("error", reject);
    server.listen(port, "127.0.0.1", () => resolve(server));
  });
}

function closeServer(server: net.Server): Promise<void> {
  return new Promise((resolve) => server.close(() => resolve()));
}

const configFn = viteConfig as unknown as (env: ConfigEnv) => Promise<ResolvedConfig>;

afterEach(() => {
  delete process.env.SS_DEV_PORT;
  delete process.env.SS_API_PORT;
  delete process.env.COWORKER_STATE_DIR;
  delete process.env.VITE_COWORKER_HTTP;
  delete process.env.VITE_COWORKER_WS;
  delete process.env.VITE_COWORKER_API_TOKEN;
});

describe("vite config dev port", () => {
  it("uses SS_DEV_PORT in serve mode when provided", async () => {
    process.env.SS_DEV_PORT = "14300";
    const config = await configFn({ command: "serve", mode: "development" });
    expect(config.server.port).toBe(14300);
    expect(config.server.strictPort).toBe(true);
  });

  it("skips the fixed port when 1420 is occupied in serve mode", async () => {
    const server = await listenOn(1420).catch(() => null);
    const config = await configFn({ command: "serve", mode: "development" });
    expect(config.server.port).toBeGreaterThan(1420);
    expect(config.server.strictPort).toBe(true);
    if (server) await closeServer(server);
  });

  it("keeps the fixed port 1420 in build mode regardless of SS_DEV_PORT", async () => {
    process.env.SS_DEV_PORT = "14300";
    const config = await configFn({ command: "build", mode: "production" });
    expect(config.server.port).toBe(1420);
  });

  it("exposes the newest sidecar port and token via VITE_ env in serve mode", async () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), "vite-api-test-"));
    try {
      fs.writeFileSync(path.join(dir, "sidecar-8765.token"), "old\n");
      fs.writeFileSync(path.join(dir, "sidecar-8766.token"), "tok-8766\n");
      fs.utimesSync(path.join(dir, "sidecar-8765.token"), new Date(), new Date(Date.now() - 60_000));
      process.env.COWORKER_STATE_DIR = dir;
      await configFn({ command: "serve", mode: "development" });
      expect(process.env.VITE_COWORKER_HTTP).toBe("http://127.0.0.1:8766");
      expect(process.env.VITE_COWORKER_WS).toBe("ws://127.0.0.1:8766");
      expect(process.env.VITE_COWORKER_API_TOKEN).toBe("tok-8766");
    } finally {
      fs.rmSync(dir, { recursive: true, force: true });
    }
  });

  it("honors SS_API_PORT over the newest sidecar token", async () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), "vite-api-test-"));
    try {
      fs.writeFileSync(path.join(dir, "sidecar-8766.token"), "tok-8766\n");
      fs.writeFileSync(path.join(dir, "sidecar-14321.token"), "tok-14321\n");
      process.env.COWORKER_STATE_DIR = dir;
      process.env.SS_API_PORT = "14321";
      await configFn({ command: "serve", mode: "development" });
      expect(process.env.VITE_COWORKER_HTTP).toBe("http://127.0.0.1:14321");
      expect(process.env.VITE_COWORKER_API_TOKEN).toBe("tok-14321");
    } finally {
      fs.rmSync(dir, { recursive: true, force: true });
    }
  });

  it("keeps existing VITE_ overrides and sets nothing in build mode", async () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), "vite-api-test-"));
    try {
      fs.writeFileSync(path.join(dir, "sidecar-8766.token"), "tok-8766\n");
      process.env.COWORKER_STATE_DIR = dir;
      process.env.VITE_COWORKER_HTTP = "http://127.0.0.1:9999";
      await configFn({ command: "serve", mode: "development" });
      expect(process.env.VITE_COWORKER_HTTP).toBe("http://127.0.0.1:9999");
      expect(process.env.VITE_COWORKER_WS).toBe("ws://127.0.0.1:8766");
      delete process.env.VITE_COWORKER_HTTP;
      delete process.env.VITE_COWORKER_WS;
      delete process.env.VITE_COWORKER_API_TOKEN;
      await configFn({ command: "build", mode: "production" });
      expect(process.env.VITE_COWORKER_HTTP).toBeUndefined();
      expect(process.env.VITE_COWORKER_WS).toBeUndefined();
      expect(process.env.VITE_COWORKER_API_TOKEN).toBeUndefined();
    } finally {
      fs.rmSync(dir, { recursive: true, force: true });
    }
  });
});
