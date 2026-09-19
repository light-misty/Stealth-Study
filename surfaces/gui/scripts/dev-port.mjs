import net from "node:net";

const DEFAULT_START_PORT = 1420;
const PROBE_HOSTS = ["127.0.0.1", "::1"];
const DEFAULT_MAX_ATTEMPTS = 100;

function isHostAvailable(port, host) {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.once("error", (err) => {
      if (err.code === "EADDRINUSE" || err.code === "EACCES") {
        resolve(false);
      } else {
        reject(err);
      }
    });
    server.once("listening", () => {
      server.close(() => resolve(true));
    });
    server.listen(port, host);
  });
}

export async function isPortAvailable(port, hosts = PROBE_HOSTS) {
  for (const host of hosts) {
    if (!(await isHostAvailable(port, host))) return false;
  }
  return true;
}

export async function findAvailablePort(options = {}) {
  const {
    startPort = DEFAULT_START_PORT,
    maxAttempts = DEFAULT_MAX_ATTEMPTS,
    logger = null,
  } = options;
  for (let offset = 0; offset < maxAttempts; offset += 1) {
    const port = startPort + offset;
    if (await isPortAvailable(port)) {
      if (logger) logger(`[dev-port] using port ${port}`);
      return port;
    }
    if (logger) logger(`[dev-port] port ${port} is in use, trying ${port + 1}`);
  }
  throw new Error(
    `[dev-port] no available port between ${startPort} and ${startPort + maxAttempts - 1}`,
  );
}
