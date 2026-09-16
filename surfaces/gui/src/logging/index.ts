// 前端日志模块入口：初始化控制台捕获与上传调度。

import { initLogCapture } from "./capture";
import { createLogStore, type LogStore } from "./store";
import { createLogUploader, type LogUploader } from "./upload";

export type { LogEntry, LogLevel, LogStore } from "./store";
export type { LogUploader, UploadOptions } from "./upload";
export { formatTimestamp } from "./capture";

export interface LoggingHandle {
  store: LogStore;
  uploader: LogUploader;
  stop(): void;
}

let handle: LoggingHandle | null = null;

// 初始化前端日志捕获与上传；重复调用幂等，返回当前句柄
export function startLogCapture(options?: Partial<import("./upload").UploadOptions>): LoggingHandle {
  if (handle) return handle;
  const store = createLogStore();
  const uploader = createLogUploader(store, options);
  const captured = initLogCapture(store, { onEntry: () => uploader.notify() });
  handle = { ...captured, uploader };
  return handle;
}

// 测试隔离用：恢复 console、停止上传并清空句柄
export function stopLogCapture(): void {
  if (handle) {
    handle.stop();
    handle.uploader.stop();
    handle = null;
  }
}