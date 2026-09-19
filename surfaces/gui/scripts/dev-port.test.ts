import { describe, expect, it, vi } from "vitest";
import net from "node:net";
import { findAvailablePort, isPortAvailable } from "./dev-port.mjs";

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
