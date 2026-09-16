// 前端日志上传调度：周期 + 条数触发批量上传，失败指数退避重试，
// 成功后删除本地已上传条目，保证网络不稳定时日志零丢失。

import { uploadLogsBatch } from "../api";
import type { LogStore } from "./store";

export interface UploadOptions {
  // 单批最大条数
  batchSize: number;
  // 周期上传间隔（毫秒）
  intervalMs: number;
  // 条数触发阈值：新条目数达到即立即上传
  minEntries: number;
  // 退避上限（毫秒）
  maxBackoffMs: number;
}

const DEFAULT_OPTIONS: UploadOptions = {
  batchSize: 20,
  intervalMs: 30_000,
  minEntries: 20,
  maxBackoffMs: 300_000,
};

export interface LogUploader {
  // 有新条目入队时通知，达到阈值立即触发上传
  notify(): void;
  stop(): void;
}

export function createLogUploader(
  store: LogStore,
  options: Partial<UploadOptions> = {},
): LogUploader {
  const opts: UploadOptions = { ...DEFAULT_OPTIONS, ...options };

  let timer: ReturnType<typeof setTimeout> | undefined;
  let stopped = false;
  let running = false;
  // 初始退避 300ms，逐次翻倍，上限 maxBackoffMs
  let backoffMs = 300;

  function schedule(delay: number): void {
    if (stopped) return;
    timer = setTimeout(() => void run(), delay);
  }

  async function run(): Promise<void> {
    if (running || stopped) return;
    running = true;
    try {
      const batches = await store.getPending(opts.batchSize);
      if (batches.length === 0) {
        // 无积压：回到周期轮询
        schedule(opts.intervalMs);
        return;
      }
      const ok = await uploadLogsBatch(
        batches.map((b) => ({
          ts: b.entry.ts,
          level: b.entry.level,
          message: b.entry.message,
          ...(b.entry.stack ? { stack: b.entry.stack } : {}),
        })),
      );
      if (!ok) {
        // 上传失败：指数退避后重试，本地条目保留
        backoffMs = Math.min(backoffMs * 2, opts.maxBackoffMs);
        schedule(backoffMs);
        return;
      }
      // 上传成功：删除已上传条目并重置退避
      await store.deleteByKeys(batches.map((b) => b.key));
      backoffMs = 300;
      const remaining = await store.count();
      if (remaining > 0) {
        // 仍有积压：立即消化下一批
        schedule(0);
        return;
      }
      schedule(opts.intervalMs);
    } catch {
      backoffMs = Math.min(backoffMs * 2, opts.maxBackoffMs);
      schedule(backoffMs);
    } finally {
      running = false;
    }
  }

  function notify(): void {
    if (running || stopped) return;
    void store.count().then((n) => {
      if (n >= opts.minEntries) void run();
    });
  }

  // 启动：立即回放本地残留日志（跨会话/崩溃恢复）
  schedule(0);

  return {
    notify,
    stop() {
      stopped = true;
      if (timer !== undefined) clearTimeout(timer);
    },
  };
}