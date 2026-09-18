import React from "react";
import ReactDOM from "react-dom/client";
import { App } from "./App";
import { initTheme } from "./theme";
import { platformOS } from "./tauri";
import { initI18n } from "./i18n";
import { startLogCapture } from "./logging";
import "./tailwind.css";
import "./styles.css";

initTheme();
// Platform hook for CSS (html[data-platform="windows"] scrollbar styling etc.).
document.documentElement.dataset.platform = platformOS();

// 初始化前端日志捕获：劫持 console 全量输出并在本地缓存，随后周期上传后端。
// 周期与条数阈值调短，确保前端日志尽快落盘（否则浏览器 30s/20 条默认偏慢）。
startLogCapture({ intervalMs: 10_000, minEntries: 5 });

// A file dropped OUTSIDE a drop target (the composer) must never navigate the webview to the
// file itself — the browser/WKWebView default. Drop targets stopPropagation-free preventDefault
// in their own handlers; these guards only catch the misses. (The desktop shell disables Tauri's
// native drag-drop interception so HTML5 drag events reach the DOM at all — see lib.rs.)
window.addEventListener("dragover", (e) => e.preventDefault());
window.addEventListener("drop", (e) => e.preventDefault());

// Initialize i18n before the first render so t() resolves everywhere.
initI18n().finally(() => {
  ReactDOM.createRoot(document.getElementById("root")!).render(
    <React.StrictMode>
      <App />
    </React.StrictMode>,
  );
});
