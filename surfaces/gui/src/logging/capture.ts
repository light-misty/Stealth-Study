// 前端控制台捕获：劫持 console 全部方法并捕获运行时错误，写入本地缓存。
// 捕获过程先调用原始 console 方法，保证浏览器控制台输出不受影响且顺序一致。

import type { LogEntry, LogLevel, LogStore } from "./store";

// 保留原始 console 方法引用：劫持后内部必须继续调用原始方法，避免重复捕获
const original = { ...console };

function pad(n: number, width = 2): string {
  return String(n).padStart(width, "0");
}

// 生成与浏览器控制台一致的时间戳 "YYYY-MM-DD HH:MM:SS,mmm"
export function formatTimestamp(d = new Date()): string {
  return (
    `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ` +
    `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())},` +
    `${pad(d.getMilliseconds(), 3)}`
  );
}

function formatValue(value: unknown): string {
  if (value instanceof Error) return value.stack ?? value.message;
  if (typeof value === "string") return value;
  try {
    const json = JSON.stringify(value);
    return json === undefined ? String(value) : json;
  } catch {
    // 循环引用等无法序列化的对象退化为 String 显示
    return String(value);
  }
}

function formatArgs(args: unknown[]): string {
  return args.map(formatValue).join(" ");
}

export interface LoggerHandle {
  store: LogStore;
  // 恢复原始 console 并移除全局监听，供测试隔离使用
  stop(): void;
}

export function initLogCapture(store: LogStore): LoggerHandle {
  const stopFns: Array<() => void> = [];

  function record(level: LogLevel, args: unknown[], stack?: string): void {
    const entry: LogEntry = {
      ts: formatTimestamp(),
      level,
      message: formatArgs(args),
      ...(stack ? { stack } : {}),
    };
    // 异步入队：异常时也不阻塞主流程
    void store.add(entry);
  }

  function wrap(method: "log" | "debug" | "info" | "warn" | "error", level: LogLevel): void {
    const prev = console[method];
    // console 的方法联合签名对任意参数 spread 不友好，统一走宽松子类型调用原始方法
    const originalCall = (...data: unknown[]) => {
      (original[method] as unknown as (...args: unknown[]) => void).apply(console, data);
    };
    // 先走原始输出保证控制台可见性，再记录日志条目
    const wrapped = (...data: unknown[]): void => {
      originalCall(...data);
      record(level, data);
    };
    const assign = (fn: unknown) => {
      (console as unknown as Record<string, unknown>)[method] = fn;
    };
    assign(wrapped);
    stopFns.push(() => {
      assign(prev);
    });
  }

  wrap("log", "INFO");
  wrap("debug", "DEBUG");
  wrap("info", "INFO");
  wrap("warn", "WARN");
  wrap("error", "ERROR");

  const onError = (event: ErrorEvent) => {
    record(
      "ERROR",
      [event.message],
      event.error instanceof Error ? event.error.stack : undefined,
    );
  };
  const onRejection = (event: PromiseRejectionEvent) => {
    const reason = event.reason instanceof Error ? event.reason.message : String(event.reason);
    record("ERROR", [reason], event.reason instanceof Error ? event.reason.stack : undefined);
  };
  window.addEventListener("error", onError);
  window.addEventListener("unhandledrejection", onRejection);
  stopFns.push(() => {
    window.removeEventListener("error", onError);
    window.removeEventListener("unhandledrejection", onRejection);
  });

  return {
    store,
    stop() {
      for (const fn of stopFns.splice(0)) fn();
    },
  };
}