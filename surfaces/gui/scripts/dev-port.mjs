import net from "node:net";
import fs from "node:fs";
import path from "node:path";

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

const SIDECAR_TOKEN_PATTERN = /^sidecar-(\d+)\.token$/;

export function findDevApi(stateDir) {
  let names = [];
  try {
    names = fs.readdirSync(stateDir).filter((name) => SIDECAR_TOKEN_PATTERN.test(name));
  } catch {
    return null;
  }
  let newest = null;
  for (const name of names) {
    try {
      const mtimeMs = fs.statSync(path.join(stateDir, name)).mtimeMs;
      if (!newest || mtimeMs > newest.mtimeMs) newest = { name, mtimeMs };
    } catch {
      continue;
    }
  }
  if (!newest) return null;
  const port = Number(newest.name.match(SIDECAR_TOKEN_PATTERN)[1]);
  let token = "";
  try {
    token = fs.readFileSync(path.join(stateDir, newest.name), "utf8").trim();
  } catch {
    token = "";
  }
  return { port, token };
}
