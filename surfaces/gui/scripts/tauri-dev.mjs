import { spawn } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { findAvailablePort } from "./dev-port.mjs";

const DEV_CONFIG_NAME = "tauri.dev.conf.json";
const DEV_CONFIG_DIR = path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "src-tauri");

export function buildDevConfig(port) {
  return { build: { devUrl: `http://localhost:${port}` } };
}

export function writeDevConfig(port, outDir = DEV_CONFIG_DIR) {
  const filePath = path.join(outDir, DEV_CONFIG_NAME);
  fs.writeFileSync(filePath, `${JSON.stringify(buildDevConfig(port), null, 2)}\n`);
  return filePath;
}

export async function resolveDevPort(options = {}) {
  const envPort = Number(process.env.SS_DEV_PORT);
  if (Number.isInteger(envPort) && envPort > 0) {
    console.log(`[tauri-dev] using port ${envPort} (SS_DEV_PORT)`);
    return envPort;
  }
  return findAvailablePort({ startPort: 1420, logger: (m) => console.log(m), ...options });
}

function runTauri(args, extraEnv) {
  const child = spawn("tauri", args, {
    stdio: "inherit",
    shell: process.platform === "win32",
    env: { ...process.env, ...extraEnv },
  });
  child.on("exit", (code) => {
    process.exit(code ?? 1);
  });
  child.on("error", (err) => {
    console.error(`[tauri-dev] failed to launch tauri: ${err.message}`);
    process.exit(1);
  });
}

async function main() {
  const args = process.argv.slice(2);
  if (args[0] !== "dev") {
    runTauri(args, {});
    return;
  }
  const port = await resolveDevPort();
  console.log(`[tauri-dev] dev server port: ${port}`);
  const configPath = writeDevConfig(port);
  console.log(`[tauri-dev] wrote ${path.relative(process.cwd(), configPath)}`);
  runTauri(["dev", "-c", path.relative(process.cwd(), configPath), ...args.slice(1)], {
    SS_DEV_PORT: String(port),
  });
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  await main();
}
