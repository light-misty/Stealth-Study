// @vitest-environment node
import { afterEach, describe, expect, it } from "vitest";
import net from "node:net";
import viteConfig from "../vite.config.ts";

type ConfigEnv = { command: "serve" | "build"; mode: string };

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

const configFn = viteConfig as unknown as (env: ConfigEnv) => Promise<{
  server: { port: number; strictPort: boolean };
}>;

afterEach(() => {
  delete process.env.SS_DEV_PORT;
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
});
