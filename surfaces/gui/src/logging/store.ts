// 前端日志的本地存储：条目类型、统一存储接口、IndexedDB 实现与内存回退。
// IndexedDB 不可用（隐私模式 / jsdom 测试环境）时自动回退到内存队列。

// 级别与后端白名单保持一致
export type LogLevel = "DEBUG" | "INFO" | "WARN" | "ERROR" | "FATAL";

export interface LogEntry {
  // 与浏览器控制台一致的时间戳格式 "YYYY-MM-DD HH:MM:SS,mmm"
  ts: string;
  level: LogLevel;
  message: string;
  stack?: string;
}

// 本地缓存保留上限，超出丢弃最旧，防止无限增长
export const MAX_ENTRIES = 5000;

export interface LogBatch {
  key: unknown;
  entry: LogEntry;
}

export interface LogStore {
  add(entry: LogEntry): Promise<void>;
  // 按写入顺序取最早的 limit 条（供批量上传）
  getPending(limit: number): Promise<LogBatch[]>;
  // 删除已成功上传的条目
  deleteByKeys(keys: unknown[]): Promise<void>;
  count(): Promise<number>;
}

const DB_NAME = "stealth-study-logs";
const STORE_NAME = "entries";

export class IdbLogStore implements LogStore {
  private db: IDBDatabase | null = null;

  private async ready(): Promise<IDBDatabase> {
    if (this.db) return this.db;
    return new Promise((resolve, reject) => {
      const req = indexedDB.open(DB_NAME, 1);
      req.onupgradeneeded = () => {
        if (!req.result.objectStoreNames.contains(STORE_NAME)) {
          req.result.createObjectStore(STORE_NAME, { autoIncrement: true });
        }
      };
      req.onsuccess = () => {
        this.db = req.result;
        resolve(this.db);
      };
      req.onerror = () => reject(req.error);
    });
  }

  async add(entry: LogEntry): Promise<void> {
    const db = await this.ready();
    await new Promise<void>((resolve, reject) => {
      const tx = db.transaction(STORE_NAME, "readwrite");
      tx.objectStore(STORE_NAME).add(entry);
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
    await this.trimIfNeeded(db);
  }

  // 超出上限时按升序游标删除最旧的超出条目
  private async trimIfNeeded(db: IDBDatabase): Promise<void> {
    return new Promise<void>((resolve, reject) => {
      const tx = db.transaction(STORE_NAME, "readwrite");
      const store = tx.objectStore(STORE_NAME);
      const countReq = store.count();
      countReq.onsuccess = () => {
        const excess = countReq.result - MAX_ENTRIES;
        if (excess <= 0) return;
        const cursorReq = store.openCursor();
        let removed = 0;
        cursorReq.onsuccess = () => {
          const cursor = cursorReq.result;
          if (cursor && removed < excess) {
            cursor.delete();
            removed += 1;
            cursor.continue();
          }
        };
        cursorReq.onerror = () => reject(cursorReq.error);
      };
      countReq.onerror = () => reject(countReq.error);
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
  }

  async getPending(limit: number): Promise<LogBatch[]> {
    const db = await this.ready();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE_NAME, "readonly");
      const req = tx.objectStore(STORE_NAME).openCursor();
      const items: LogBatch[] = [];
      req.onsuccess = () => {
        const cursor = req.result;
        if (cursor && items.length < limit) {
          items.push({ key: cursor.key, entry: cursor.value as LogEntry });
          cursor.continue();
        } else {
          resolve(items);
        }
      };
      req.onerror = () => reject(req.error);
    });
  }

  async deleteByKeys(keys: unknown[]): Promise<void> {
    if (keys.length === 0) return;
    const db = await this.ready();
    await new Promise<void>((resolve, reject) => {
      const tx = db.transaction(STORE_NAME, "readwrite");
      const store = tx.objectStore(STORE_NAME);
      for (const key of keys) store.delete(key as IDBValidKey);
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
  }

  async count(): Promise<number> {
    const db = await this.ready();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE_NAME, "readonly");
      const req = tx.objectStore(STORE_NAME).count();
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });
  }
}

export class MemoryLogStore implements LogStore {
  private entries: LogBatch[] = [];
  private seq = 0;

  // 测试/压测可调整上限（如 Infinity 关闭裁剪）
  constructor(private maxEntries: number = MAX_ENTRIES) {}

  async add(entry: LogEntry): Promise<void> {
    this.entries.push({ key: ++this.seq, entry });
    this.trim();
  }

  async getPending(limit: number): Promise<LogBatch[]> {
    return this.entries.slice(0, limit);
  }

  async deleteByKeys(keys: unknown[]): Promise<void> {
    const removed = new Set(keys);
    this.entries = this.entries.filter((batch) => !removed.has(batch.key));
  }

  async count(): Promise<number> {
    return this.entries.length;
  }

  private trim(): void {
    if (this.entries.length > this.maxEntries) {
      this.entries = this.entries.slice(this.entries.length - this.maxEntries);
    }
  }
}

// 环境探测：jsdom / 隐私模式下无 IndexedDB，走内存队列
export function createLogStore(): LogStore {
  if (typeof indexedDB !== "undefined") return new IdbLogStore();
  return new MemoryLogStore();
}