import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { findAvailablePort } from "./scripts/dev-port.mjs";

// `base: "./"` makes built asset URLs relative, so the bundle loads from the `tauri://`
// origin in the desktop shell (absolute `/assets` 404s there); a server-hosted build is
// unaffected. Dev resolves the first free port from 1420 upward (or `SS_DEV_PORT`) and pins
// it with strictPort; the Tauri dev wrapper keeps `tauri.conf.json` devUrl in sync.
export default defineConfig(async ({ command }) => {
  let devToken = "";
  let devPort = 1420;
  if (command === "serve") {
    const state =
      process.env.COWORKER_STATE_DIR ||
      (process.platform === "win32"
        ? path.join(process.env.APPDATA || os.homedir(), "coworker")
        : path.join(os.homedir(), ".config", "coworker"));
    try {
      devToken = fs.readFileSync(path.join(state, "sidecar-8765.token"), "utf8").trim();
    } catch {
      // The Tauri dev shell injects its in-memory token at runtime. Plain browser dev
      // shows the normal startup retry until the standalone server/token file exists.
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
