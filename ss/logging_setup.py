"""统一日志配置：日志目录、命名规范、轮转归档与请求上下文关联。

setup_logging() 会创建项目根目录下的 log/ 文件夹，配置根 logger 与
每日/大小轮转文件 handler，并通过 contextvars 向日志行注入
request_id / user_id。日志文件命名 {服务类型}_{YYYYMMDD_HHMMSS}.log，
服务类型仅 frontend / backend，两类日志完全分离。
"""

from __future__ import annotations

import logging
import os
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

# 大小轮转默认阈值：50MB
_DEFAULT_MAX_BYTES = 50 * 1024 * 1024

# 本模块安装到根 logger 的 handler，供重复配置时清理（幂等）
_installed_handlers: list[logging.Handler] = []


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
    # 先移除本模块先前安装的 handler，保证重复调用不叠加
    for handler in _installed_handlers:
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

    root.addHandler(console)
    root.addHandler(backend)
    _installed_handlers.extend([console, backend])

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
        "level": level,
    }


def get_logger(name: str) -> logging.Logger:
    """获取统一配置下的命名日志器。"""
    return logging.getLogger(name)