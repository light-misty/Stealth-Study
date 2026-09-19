// @vitest-environment node
import { describe, expect, it, vi } from "vitest";
import net from "node:net";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { findAvailablePort, findDevApi, isPortAvailable } from "./dev-port.mjs";

type AnyServer = net.Server;

function listenOn(port = 0): Promise<AnyServer> {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.once("error", reject);
    server.listen(port, "127.0.0.1", () => resolve(server));
  });
}

function portOf(server: AnyServer): number {
  const address = server.address();
  if (typeof address === "object" && address !== null) return address.port;
  throw new Error("server has no port");
}

function closeServer(server: AnyServer): Promise<void> {
  return new Promise((resolve) => server.close(() => resolve()));
}

function listenOnIpv6(): Promise<AnyServer> {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.once("error", reject);
    server.listen(0, "::1", () => resolve(server));
  });
}

async function occupyConsecutivePorts(count: number): Promise<{ servers: AnyServer[]; start: number }> {
  for (;;) {
    const first = await listenOn();
    const start = portOf(first);
    const servers = [first];
    let ok = true;
    for (let offset = 1; offset < count; offset += 1) {
      try {
        servers.push(await listenOn(start + offset));
      } catch {
        ok = false;
        break;
      }
    }
    if (ok) return { servers, start };
    for (const server of servers) await closeServer(server);
  }
}

describe("isPortAvailable", () => {
  it("returns false when the port is occupied", async () => {
    const server = await listenOn();
    const port = portOf(server);
    await expect(isPortAvailable(port)).resolves.toBe(false);
    await closeServer(server);
  });

  it("returns true when the port is free", async () => {
    const server = await listenOn();
    const port = portOf(server);
    await closeServer(server);
    await expect(isPortAvailable(port)).resolves.toBe(true);
  });

  it("treats a port occupied only on IPv6 localhost as unavailable", async () => {
    const server = await listenOnIpv6();
    const port = portOf(server);
    try {
      await expect(isPortAvailable(port)).resolves.toBe(false);
    } finally {
      await closeServer(server);
    }
  });
});

describe("findDevApi", () => {
  function makeTempStateDir(): string {
    return fs.mkdtempSync(path.join(os.tmpdir(), "dev-api-test-"));
  }

  it("returns the port and token of the newest sidecar token file", () => {
    const dir = makeTempStateDir();
    try {
      fs.writeFileSync(path.join(dir, "sidecar-8765.token"), "old-token\n");
      fs.writeFileSync(path.join(dir, "sidecar-8766.token"), "new-token\n");
      fs.utimesSync(
        path.join(dir, "sidecar-8765.token"),
        new Date(),
        new Date(Date.now() - 60_000),
      );
      expect(findDevApi(dir)).toEqual({ port: 8766, token: "new-token" });
    } finally {
      fs.rmSync(dir, { recursive: true, force: true });
    }
  });

  it("returns null when the state dir has no token file", () => {
    const dir = makeTempStateDir();
    try {
      expect(findDevApi(dir)).toBeNull();
    } finally {
      fs.rmSync(dir, { recursive: true, force: true });
    }
  });

  it("returns null when the state dir does not exist", () => {
    expect(findDevApi(path.join(os.tmpdir(), "dev-api-missing-dir-xyz"))).toBeNull();
  });
});

describe("findAvailablePort", () => {
  it("returns the start port when it is free", async () => {
    const server = await listenOn();
    const port = portOf(server);
    await closeServer(server);
    await expect(findAvailablePort({ startPort: port })).resolves.toBe(port);
  });

  it("skips occupied ports and returns the first free port", async () => {
    const { servers, start } = await occupyConsecutivePorts(2);
    try {
      await expect(findAvailablePort({ startPort: start })).resolves.toBe(start + 2);
    } finally {
      for (const server of servers) await closeServer(server);
    }
  });

  it("reports each occupied port and the final port through the logger", async () => {
    const { servers, start } = await occupyConsecutivePorts(2);
    try {
      const messages: string[] = [];
      const port = await findAvailablePort({
        startPort: start,
        logger: (message: string) => messages.push(message),
      });
      expect(port).toBe(start + 2);
      expect(messages.some((m) => m.includes(`${start}`) && m.includes("in use"))).toBe(true);
      expect(messages.some((m) => m.includes(`${start + 1}`) && m.includes("in use"))).toBe(true);
      expect(messages.some((m) => m.includes(`${start + 2}`) && m.includes("using port"))).toBe(true);
    } finally {
      for (const server of servers) await closeServer(server);
    }
  });

  it("stays silent when no logger is provided", async () => {
    const server = await listenOn();
    const port = portOf(server);
    try {
      const spy = vi.spyOn(console, "log");
      await findAvailablePort({ startPort: port });
      expect(spy).not.toHaveBeenCalled();
      spy.mockRestore();
    } finally {
      await closeServer(server);
    }
  });

  it("throws when no port is available within maxAttempts", async () => {
    const server = await listenOn();
    const start = portOf(server);
    try {
      await expect(findAvailablePort({ startPort: start, maxAttempts: 1 })).rejects.toThrow();
    } finally {
      await closeServer(server);
    }
  });
});
