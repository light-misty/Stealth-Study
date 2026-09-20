import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { findAvailablePort, findDevApi } from "./scripts/dev-port.mjs";

// `base: "./"` makes built asset URLs relative, so the bundle loads from the `tauri://`
// origin in the desktop shell (absolute `/assets` 404s there); a server-hosted build is
// unaffected. Dev resolves the first free port from 1420 upward (or `SS_DEV_PORT`) and pins
// it with strictPort; the Tauri dev wrapper keeps `tauri.conf.json` devUrl in sync.
export default defineConfig(async ({ command }) => {
  let devToken = "";
  let devPort = 1420;
  let devApiPort = "";
  if (command === "serve") {
    const state =
      process.env.COWORKER_STATE_DIR ||
      (process.platform === "win32"
        ? path.join(process.env.APPDATA || os.homedir(), "Stealth Study")
        : path.join(os.homedir(), ".config", "Stealth Study"));
    const envApiPort = Number(process.env.SS_API_PORT);
    if (Number.isInteger(envApiPort) && envApiPort > 0) {
      devApiPort = String(envApiPort);
      try {
        devToken = fs.readFileSync(path.join(state, `sidecar-${envApiPort}.token`), "utf8").trim();
      } catch {
        devToken = "";
      }
      console.log(`[dev-port] api server port: ${devApiPort} (SS_API_PORT)`);
    } else {
      const api = findDevApi(state);
      if (api) {
        devApiPort = String(api.port);
        devToken = api.token;
        console.log(`[dev-port] api server port: ${devApiPort} (sidecar token)`);
      }
    }
    if (devApiPort) {
      if (!process.env.VITE_COWORKER_HTTP)
        process.env.VITE_COWORKER_HTTP = `http://127.0.0.1:${devApiPort}`;
      if (!process.env.VITE_COWORKER_WS)
        process.env.VITE_COWORKER_WS = `ws://127.0.0.1:${devApiPort}`;
      if (!process.env.VITE_COWORKER_API_TOKEN && devToken)
        process.env.VITE_COWORKER_API_TOKEN = devToken;
    }
    const envPort = Number(process.env.SS_DEV_PORT);
    if (Number.isInteger(envPort) && envPort > 0) {
      devPort = envPort;
      console.log(`[dev-port] using port ${devPort} (SS_DEV_PORT)`);
    } else {
      devPort = await findAvailablePort({ startPort: 1420, logger: (m) => console.log(m) });
    }
  }
  return {
    base: "./",
    plugins: [react()],
    server: {
      port: devPort,
      strictPort: true,
      watch: {
        ignored: ["**/src-tauri/target/**"],
      },
    },
    define: { __COWORKER_DEV_TOKEN__: JSON.stringify(devToken) },
    // Tauri CLI looks for these; harmless for the browser build.
    clearScreen: false,
    envPrefix: ["VITE_", "TAURI_"],
  };
});
