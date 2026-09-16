// 前端日志模块入口：初始化控制台捕获（上传调度由 index 后续阶段接入）。

import { initLogCapture, type LoggerHandle } from "./capture";
import { createLogStore } from "./store";

export type { LogEntry, LogLevel, LogStore } from "./store";
export { formatTimestamp } from "./capture";

let handle: LoggerHandle | null = null;

// 初始化前端日志捕获；重复调用幂等，返回当前句柄
export function startLogCapture(): LoggerHandle {
  if (handle) return handle;
  handle = initLogCapture(createLogStore());
  return handle;
}

// 测试隔离用：恢复 console 并清空句柄
export function stopLogCapture(): void {
  if (handle) {
    handle.stop();
    handle = null;
  }
}