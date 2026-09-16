// 前端日志压力测试：万条日志队列批量排空，验证零丢失与调度收敛。

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { MemoryLogStore, type LogEntry } from "../store";
import { createLogUploader } from "../upload";

vi.mock("../../api", () => ({
  uploadLogsBatch: vi.fn(),
}));

import { uploadLogsBatch } from "../../api";

const mockedUpload = vi.mocked(uploadLogsBatch);

const TOTAL = 10_000;

function entry(message: string): LogEntry {
  return { ts: "2026-09-16 22:30:05,123", level: "INFO", message };
}

describe("stress", () => {
  beforeEach(() => {
    mockedUpload.mockReset();
    mockedUpload.mockResolvedValue(true);
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("drains 10000 queued entries in batches without loss", async () => {
    // 使用真实计时器：mock 上传即时成功，让调度循环自然消化（避免 fake timers 与
    // 异步 run 链的竞态），最多等待 2 秒内完成 100 批；无上限队列排除裁剪干扰
    const store = new MemoryLogStore(Infinity);
    const uploader = createLogUploader(store, {
      batchSize: 100,
      minEntries: 200,
      intervalMs: 30_000,
    });

    const start = performance.now();
    for (let i = 0; i < TOTAL; i++) {
      await store.add(entry(`m-${i}`));
    }
    uploader.notify();
    for (let i = 0; i < 200; i++) {
      if ((await store.count()) === 0) break;
      await new Promise((resolve) => setTimeout(resolve, 5));
    }
    const elapsed = performance.now() - start;

    expect(await store.count()).toBe(0);
    expect(mockedUpload).toHaveBeenCalledTimes(TOTAL / 100);
    // 单批内条数完整：所有请求的条目总数等于 TOTAL
    const sent = mockedUpload.mock.calls.reduce(
      (sum, call) => sum + call[0].length,
      0,
    );
    expect(sent).toBe(TOTAL);
    // 供报告使用：万条日志批量排空耗时（mock 网络，反映调度与存储开销）
    console.info(`stress: ${TOTAL} entries drained in ${elapsed.toFixed(1)} ms`);
    uploader.stop();
  });
});