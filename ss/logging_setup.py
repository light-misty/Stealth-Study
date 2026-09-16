"""统一日志配置：日志目录、命名规范、轮转归档与请求上下文关联。

setup_logging() 会创建项目根目录下的 log/ 文件夹，配置根 logger 与
每日/大小轮转文件 handler，并通过 contextvars 向日志行注入
request_id / user_id。日志文件命名 {服务类型}_{YYYYMMDD_HHMMSS}.log，
服务类型仅 frontend / backend，两类日志完全分离。
"""

from __future__ import annotations

import logging
import os
import re
import tempfile
from contextvars import ContextVar
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Callable

# 需求的 FATAL 级别使用 Python 标准库的 CRITICAL 实现（语义一致）
FATAL = logging.CRITICAL

# 请求上下文：日志格式化时未设置则显示 "-"
request_id_var: ContextVar[str] = ContextVar("request_id", default="")
user_id_var: ContextVar[str] = ContextVar("user_id", default="")

# 单条日志格式："2026-09-16 14:30:05,123 [INFO] [模块] [req=xx] [user=xx] 消息"
_RECORD_FMT = (
    "%(asctime)s,%(msecs)03d [%(levelname)s] [%(name)s] "
    "[req=%(request_id)s] [user=%(user_id)s] %(message)s"
)
_DATEFMT = "%Y-%m-%d %H:%M:%S"

# 前端日志允许的级别白名单（与前端 console 映射一致）
_FRONTEND_LEVELS = {"DEBUG", "INFO", "WARN", "ERROR", "FATAL"}

# 单次上传允许的最大日志条数
_MAX_FRONTEND_BATCH = 10000

# 大小轮转默认阈值：50MB
_DEFAULT_MAX_BYTES = 50 * 1024 * 1024

# 本模块安装到根 logger 的 handler，供重复配置时清理（幂等）
_installed_handlers: list[logging.Handler] = []

# 独立的 frontend 文件 handler：不挂到根 logger，仅由 write_frontend_logs 使用
_frontend: DailyRotatingSizeHandler | None = None


class _ContextFilter(logging.Filter):
    """从 contextvars 读取 request_id / user_id 注入日志记录。"""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get() or "-"
        record.user_id = user_id_var.get() or "-"
        return True


class DailyRotatingSizeHandler(RotatingFileHandler):
    """按文件大小（默认 50MB）轮转并按日归档的文件 handler。

    主文件命名 {service}_{YYYYMMDD_HHMMSS}.log（活动时间戳在启动与跨日时
    更新）；大小超限归档为 {主文件}.1 / .2 …；跨日时旧文件保留、新开当日
    文件；cleanup_old_files() 确保仅保留最近 keep_files 个文件。
    """

    def __init__(
        self,
        service: str,
        log_dir: str | os.PathLike,
        max_bytes: int = _DEFAULT_MAX_BYTES,
        backup_count: int = 5,
        keep_files: int = 14,
        now: Callable[[], datetime] = datetime.now,
    ) -> None:
        self._service = service
        self._log_dir = Path(log_dir)
        self._keep_files = keep_files
        self._now = now
        # 活动文件时间戳：启动时确定，跨日时更新为当前时间
        self._active_ts = now().strftime("%Y%m%d_%H%M%S")
        self._file_date = now().date()
        filename = str(self._log_dir / f"{service}_{self._active_ts}.log")
        super().__init__(
            filename,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )

    def emit(self, record: logging.LogRecord) -> None:
        # 跨日检测：日期变化则切换到当日新文件
        today = self._now().date()
        if today != self._file_date:
            self._roll_to_new_day(today)
        super().emit(record)

    def _roll_to_new_day(self, today: Any) -> None:
        # 关闭旧文件流，以当前时间戳命名并重开当日文件
        if self.stream is not None:
            self.stream.close()
            self.stream = None
        self._active_ts = self._now().strftime("%Y%m%d_%H%M%S")
        self.baseFilename = os.path.abspath(
            str(self._log_dir / f"{self._service}_{self._active_ts}.log")
        )
        self._file_date = today
        self.stream = self._open()
        self.cleanup_old_files()

    def cleanup_old_files(self) -> None:
        """按修改时间删除超出保留数量的最旧日志文件，防止日志无限增长。"""
        if self._keep_files <= 0:
            return
        files = sorted(
            self._log_dir.glob(f"{self._service}_*.log*"),
            key=lambda p: p.stat().st_mtime,
        )
        stale = files[: max(0, len(files) - self._keep_files)]
        for path in stale:
            try:
                path.unlink()
            except OSError:
                pass

    def write_line(self, text: str) -> bool:
        """直接写入一行文本（自动补换行），并按大小/跨日规则轮转。

        供前端日志等非标准 logging 记录使用；返回本次写入是否触发了
        大小轮转，便于端点感知归档动作。
        """
        with self.lock:
            today = self._now().date()
            if today != self._file_date:
                self._roll_to_new_day(today)
            if self.stream is None:
                self.stream = self._open()
            line = text if text.endswith("\n") else text + "\n"
            rotated = False
            if (
                self.maxBytes > 0
                and self.stream.tell() + len(line.encode("utf-8")) > self.maxBytes
            ):
                self.doRollover()
                rotated = True
            self.stream.write(line)
            self.stream.flush()
            return rotated


def _parse_level(level: int | str) -> int:
    """将整数或字符串级别（如 DEBUG/INFO/WARN/ERROR/FATAL）解析为 logging 级别。"""
    names = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARN": logging.WARNING,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
        "FATAL": logging.CRITICAL,
        "CRITICAL": logging.CRITICAL,
    }
    if isinstance(level, int):
        return level
    if level.isdigit():
        return int(level)
    return names.get(level.strip().upper(), logging.INFO)


def setup_logging(project_root: str | os.PathLike, level: int | str = "INFO") -> dict[str, Any]:
    """初始化全局日志配置（幂等，可重复调用，便于测试隔离）。

    project_root 为项目根目录，日志写入其下 log/ 文件夹；路径与阈值均可
    通过环境变量 SS_LOG_DIR / SS_LOG_MAX_BYTES / SS_LOG_BACKUP_COUNT /
    SS_LOG_KEEP_FILES / SS_LOG_LEVEL 覆盖（测试隔离使用）。
    """
    env = os.environ.get
    # 日志目录不可创建时降级到系统临时目录，避免影响主业务流程
    try:
        log_dir = Path(env("SS_LOG_DIR") or Path(project_root) / "log")
        log_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        log_dir = Path(tempfile.gettempdir()) / "ss-log"
        log_dir.mkdir(parents=True, exist_ok=True)

    try:
        max_bytes = int(env("SS_LOG_MAX_BYTES", "") or _DEFAULT_MAX_BYTES)
    except ValueError:
        max_bytes = _DEFAULT_MAX_BYTES
    backup_count = int(env("SS_LOG_BACKUP_COUNT", "5"))
    keep_files = int(env("SS_LOG_KEEP_FILES", "14"))
    level = _parse_level(env("SS_LOG_LEVEL", "") or level)

    fmt = logging.Formatter(_RECORD_FMT, datefmt=_DATEFMT)
    root = logging.getLogger()
    root.setLevel(level)
    # 先关闭并移除本模块先前安装的 handler，保证重复调用不叠加也不占文件句柄
    for handler in _installed_handlers:
        handler.close()
        if handler in root.handlers:
            root.removeHandler(handler)
    _installed_handlers.clear()

    backend = DailyRotatingSizeHandler(
        "backend", log_dir, max_bytes=max_bytes, backup_count=backup_count, keep_files=keep_files
    )
    backend.setLevel(level)
    backend.setFormatter(fmt)
    backend.addFilter(_ContextFilter())

    console = logging.StreamHandler()
    console.setLevel(level)
    console.setFormatter(fmt)
    console.addFilter(_ContextFilter())

    global _frontend
    _frontend = DailyRotatingSizeHandler(
        "frontend", log_dir, max_bytes=max_bytes, backup_count=backup_count, keep_files=keep_files
    )

    root.addHandler(console)
    root.addHandler(backend)
    _installed_handlers.extend([console, backend, _frontend])

    # 关键第三方 logger 保持统一级别与格式：清掉自带 handler，交由根 logger 输出
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "httpx", "httpcore"):
        third = logging.getLogger(name)
        third.handlers.clear()
        third.setLevel(level)
        third.propagate = True

    return {
        "log_dir": str(log_dir),
        "backend_handler": backend,
        "console_handler": console,
        "frontend_handler": _frontend,
        "level": level,
    }


def get_logger(name: str) -> logging.Logger:
    """获取统一配置下的命名日志器。"""
    return logging.getLogger(name)


def _normalize_ts(value: object) -> str | None:
    """将前端上传的时间戳归一化为 "YYYY-MM-DD HH:MM:SS,mmm"。

    支持已规范化的行前缀格式与 ISO 8601（Python 3.10 的 fromisoformat 不识别
    Z 结尾，先替换为 +00:00）；无法解析时返回 None 表示该条目跳过。
    """
    if not isinstance(value, str):
        return None
    text = value.strip()
    match = re.match(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}", text)
    if match:
        return match.group(0)
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt.strftime("%Y-%m-%d %H:%M:%S,") + f"{dt.microsecond // 1000:03d}"


def write_frontend_logs(entries: object) -> tuple[int, int, bool]:
    """校验并写入前端日志条目到 frontend 文件，返回 (accepted, skipped, rotated)。

    条目结构：{"ts": 时间戳字符串, "level": 白名单级别, "message": 消息, "stack": 可选栈}。
    非法条目跳过并计数；一次上传超过 _MAX_FRONTEND_BATCH 条时截断并计入跳过。
    """
    handler = _frontend
    if handler is None:
        # 日志尚未初始化时整体视为跳过
        return 0, len(entries) if isinstance(entries, list) else 0, False
    if not isinstance(entries, list):
        return 0, 0, False
    if len(entries) > _MAX_FRONTEND_BATCH:
        skipped_extra = len(entries) - _MAX_FRONTEND_BATCH
        entries = entries[:_MAX_FRONTEND_BATCH]
    else:
        skipped_extra = 0

    accepted = 0
    skipped = skipped_extra
    rotated_flag = False
    for entry in entries:
        if not isinstance(entry, dict):
            skipped += 1
            continue
        ts = _normalize_ts(entry.get("ts"))
        level = str(entry.get("level", "")).upper()
        message = entry.get("message")
        if (
            ts is None
            or level not in _FRONTEND_LEVELS
            or not isinstance(message, str)
            or not message.strip()
        ):
            skipped += 1
            continue
        line = f"{ts} [{level}] {message}"
        stack = entry.get("stack")
        if isinstance(stack, str) and stack.strip():
            line += "\n" + stack
        rotated_flag = handler.write_line(line) or rotated_flag
        accepted += 1
    return accepted, skipped, rotated_flag