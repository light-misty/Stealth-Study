import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { MAX_ENTRIES, MemoryLogStore, type LogEntry } from "../store";
import { formatTimestamp, initLogCapture } from "../capture";
import { createLogUploader } from "../upload";

vi.mock("../../api", () => ({
  uploadLogsBatch: vi.fn(),
}));

import { uploadLogsBatch } from "../../api";

const mockedUpload = vi.mocked(uploadLogsBatch);

function entry(message: string, level: LogEntry["level"] = "INFO"): LogEntry {
  return { ts: "2026-09-16 22:30:05,123", level, message };
}

describe("store", () => {
  it("adds, reads and deletes entries", async () => {
    const store = new MemoryLogStore();
    await store.add(entry("a"));
    await store.add(entry("b"));
    expect(await store.count()).toBe(2);
    const pending = await store.getPending(10);
    expect(pending.map((p) => p.entry.message)).toEqual(["a", "b"]);
    await store.deleteByKeys([pending[0].key]);
    expect(await store.count()).toBe(1);
    expect((await store.getPending(10))[0].entry.message).toBe("b");
  });

  it("trims oldest entries beyond the cap", async () => {
    const store = new MemoryLogStore();
    for (let i = 0; i < MAX_ENTRIES + 2; i++) {
      await store.add(entry(`m-${i}`));
    }
    expect(await store.count()).toBe(MAX_ENTRIES);
    const pending = await store.getPending(3);
    expect(pending[0].entry.message).toBe("m-2");
  });
});

describe("capture", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it("captures all console methods with correct levels and order", async () => {
    const store = new MemoryLogStore();
    const handle = initLogCapture(store);
    console.log("a");
    console.debug("b");
    console.info("c");
    console.warn("d");
    console.error("e");
    const pending = await store.getPending(10);
    expect(pending.map((p) => p.entry.level)).toEqual(["INFO", "DEBUG", "INFO", "WARN", "ERROR"]);
    expect(pending.map((p) => p.entry.message)).toEqual(["a", "b", "c", "d", "e"]);
    handle.stop();
  });

  it("formats timestamps with milliseconds", () => {
    const d = new Date(2026, 8, 16, 22, 30, 5, 123);
    expect(formatTimestamp(d)).toBe("2026-09-16 22:30:05,123");
  });

  it("captures window errors with stack", async () => {
    const store = new MemoryLogStore();
    const handle = initLogCapture(store);
    window.dispatchEvent(
      new ErrorEvent("error", { message: "boom", error: new TypeError("boom") }),
    );
    const pending = await store.getPending(10);
    expect(pending[0].entry.level).toBe("ERROR");
    expect(pending[0].entry.message).toBe("boom");
    expect(pending[0].entry.stack).toContain("TypeError");
    handle.stop();
  });

  it("captures unhandled rejections", async () => {
    const store = new MemoryLogStore();
    const handle = initLogCapture(store);
    const reason = new RangeError("too big");
    // jsdom 未实现 PromiseRejectionEvent，用普通事件附加 reason 触发
    const event = new Event("unhandledrejection");
    Object.defineProperty(event, "reason", { value: reason });
    window.dispatchEvent(event);
    const pending = await store.getPending(10);
    expect(pending[0].entry.level).toBe("ERROR");
    expect(pending[0].entry.message).toBe("too big");
    expect(pending[0].entry.stack).toContain("RangeError");
    handle.stop();
  });
});

describe("uploader", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    mockedUpload.mockReset();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("replays pending logs on startup and deletes them", async () => {
    const store = new MemoryLogStore();
    await store.add(entry("a"));
    mockedUpload.mockResolvedValue(true);
    const uploader = createLogUploader(store, { intervalMs: 30_000, batchSize: 10 });
    await vi.advanceTimersByTimeAsync(0);
    expect(mockedUpload).toHaveBeenCalledTimes(1);
    expect(await store.count()).toBe(0);
    uploader.stop();
  });

  it("uploads on the interval tick", async () => {
    const store = new MemoryLogStore();
    mockedUpload.mockResolvedValue(true);
    const uploader = createLogUploader(store, { intervalMs: 1000 });
    await store.add(entry("x"));
    await vi.advanceTimersByTimeAsync(1000);
    expect(mockedUpload).toHaveBeenCalled();
    expect(await store.count()).toBe(0);
    uploader.stop();
  });

  it("uploads immediately when the entry threshold is reached", async () => {
    const store = new MemoryLogStore();
    mockedUpload.mockResolvedValue(true);
    const uploader = createLogUploader(store, { minEntries: 3, intervalMs: 60_000, batchSize: 10 });
    await vi.advanceTimersByTimeAsync(0);
    for (let i = 0; i < 3; i++) {
      await store.add(entry(`m-${i}`));
      uploader.notify();
    }
    await vi.advanceTimersByTimeAsync(0);
    expect(mockedUpload).toHaveBeenCalledTimes(1);
    expect(await store.count()).toBe(0);
    uploader.stop();
  });

  it("keeps entries and backs off on failure, then retries until success", async () => {
    const store = new MemoryLogStore();
    await store.add(entry("x"));
    mockedUpload.mockResolvedValueOnce(false).mockResolvedValueOnce(false).mockResolvedValueOnce(true);
    const uploader = createLogUploader(store, { intervalMs: 30_000 });
    // 启动即回放，首次失败 → 退避翻倍为 600ms
    await vi.advanceTimersByTimeAsync(0);
    expect(mockedUpload).toHaveBeenCalledTimes(1);
    expect(await store.count()).toBe(1);
    // 600ms 后第二次尝试，再次失败 → 退避增至 1200ms
    await vi.advanceTimersByTimeAsync(600);
    expect(mockedUpload).toHaveBeenCalledTimes(2);
    // 再过 1200ms 第三次尝试成功：删除条目、退避重置
    await vi.advanceTimersByTimeAsync(1200);
    expect(mockedUpload).toHaveBeenCalledTimes(3);
    expect(await store.count()).toBe(0);
    uploader.stop();
  });

  it("caps the backoff delay", async () => {
    const store = new MemoryLogStore();
    await store.add(entry("x"));
    mockedUpload.mockResolvedValue(false);
    const uploader = createLogUploader(store, { maxBackoffMs: 600 });
    await vi.advanceTimersByTimeAsync(0);
    await vi.advanceTimersByTimeAsync(300);
    await vi.advanceTimersByTimeAsync(600);
    const base = mockedUpload.mock.calls.length;
    await vi.advanceTimersByTimeAsync(600);
    const next = mockedUpload.mock.calls.length;
    expect(next - base).toBe(1);
    uploader.stop();
  });
});