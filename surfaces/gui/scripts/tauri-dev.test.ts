// @vitest-environment node
import { afterEach, describe, expect, it } from "vitest";
import fs from "node:fs";
import net from "node:net";
import os from "node:os";
import path from "node:path";
import { buildDevConfig, resolveDevPort, writeDevConfig } from "./tauri-dev.mjs";

function listenOn(port: number, host = "127.0.0.1"): Promise<net.Server> {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.once("error", reject);
    server.listen(port, host, () => resolve(server));
  });
}

function closeServer(server: net.Server): Promise<void> {
  return new Promise((resolve) => server.close(() => resolve()));
}

afterEach(() => {
  delete process.env.SS_DEV_PORT;
});

describe("buildDevConfig", () => {
  it("returns a tauri config override pointing devUrl at the given port", () => {
    expect(buildDevConfig(1421)).toEqual({ build: { devUrl: "http://localhost:1421" } });
  });
});

describe("writeDevConfig", () => {
  it("writes the override config as JSON into the target directory", () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), "tauri-dev-test-"));
    try {
      const filePath = writeDevConfig(1422, dir);
      expect(path.basename(filePath)).toBe("tauri.dev.conf.json");
      expect(JSON.parse(fs.readFileSync(filePath, "utf8"))).toEqual({
        build: { devUrl: "http://localhost:1422" },
      });
    } finally {
      fs.rmSync(dir, { recursive: true, force: true });
    }
  });
});

describe("resolveDevPort", () => {
  it("honors SS_DEV_PORT without probing", async () => {
    const server = await listenOn(14310);
    try {
      process.env.SS_DEV_PORT = "14310";
      await expect(resolveDevPort()).resolves.toBe(14310);
    } finally {
      await closeServer(server);
    }
  });

  it("falls back to the first free port when SS_DEV_PORT is unset", async () => {
    const first = await listenOn(0);
    const base = (first.address() as net.AddressInfo).port;
    const second = await listenOn(base + 1, "::1").catch(() => null);
    try {
      await expect(resolveDevPort({ startPort: base })).resolves.toBe(base + (second ? 2 : 1));
    } finally {
      await closeServer(first);
      if (second) await closeServer(second);
    }
  });
});
