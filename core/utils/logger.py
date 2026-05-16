"""
统一日志管理模块（支持彩色控制台输出）

使用方式：
    from core.utils import get_logger
    logger = get_logger(__name__)
    logger.info("这是一条信息")
    logger.error("发生错误: %s", error)
"""
import logging
import sys
import os
from pathlib import Path
from typing import Optional


# 尝试导入 colorlog，失败则用纯文本
try:
    import colorlog
    _HAS_COLORLOG = True
except ImportError:
    _HAS_COLORLOG = False


# 全局日志格式（文件用纯文本，控制台用彩色）
_CONSOLE_FORMAT_COLOR = "%(log_color)s[%(asctime)s] [%(levelname)s] [%(name)s]%(reset)s %(message)s"
_CONSOLE_FORMAT_PLAIN = "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s"
_FILE_FORMAT = "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# 日志级别颜色映射
_LOG_COLORS = {
    "DEBUG": "cyan",
    "INFO": "green",
    "WARNING": "yellow",
    "ERROR": "red",
    "CRITICAL": "red,bg_white",
}

# 缓存已创建的 logger
_loggers: dict = {}


def _enable_windows_ansi():
    """启用 Windows 控制台 ANSI 转义序列支持"""
    if sys.platform != 'win32':
        return
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        # 获取标准输出句柄
        STD_OUTPUT_HANDLE = -11
        handle = kernel32.GetStdHandle(STD_OUTPUT_HANDLE)
        # 启用虚拟终端处理 (ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004)
        mode = ctypes.c_uint32()
        kernel32.GetConsoleMode(handle, ctypes.byref(mode))
        kernel32.SetConsoleMode(handle, mode.value | 0x0004)
    except Exception:
        pass


def setup_logging(
    level: int = logging.INFO,
    log_file: Optional[str] = None,
    console: bool = True,
) -> None:
    """
    配置全局日志系统

    Args:
        level: 日志级别 (logging.DEBUG/INFO/WARNING/ERROR/CRITICAL)
        log_file: 日志文件路径，为 None 则不写入文件
        console: 是否输出到控制台
    """
    handlers = []

    # 文件处理器（纯文本，不含颜色）
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(logging.Formatter(_FILE_FORMAT, datefmt=_DATE_FORMAT))
        handlers.append(file_handler)

    # 控制台处理器（彩色输出，不支持则回退纯文本）
    if console:
        console_handler = logging.StreamHandler(sys.stdout)
        if _HAS_COLORLOG:
            _enable_windows_ansi()
            try:
                formatter = colorlog.ColoredFormatter(
                    _CONSOLE_FORMAT_COLOR,
                    datefmt=_DATE_FORMAT,
                    log_colors=_LOG_COLORS,
                    reset=True,
                    style="%",
                )
            except Exception:
                formatter = logging.Formatter(_CONSOLE_FORMAT_PLAIN, datefmt=_DATE_FORMAT)
        else:
            formatter = logging.Formatter(_CONSOLE_FORMAT_PLAIN, datefmt=_DATE_FORMAT)
        console_handler.setFormatter(formatter)
        handlers.append(console_handler)

    # 配置根 logger
    root_logger = logging.getLogger("Tale")
    root_logger.setLevel(level)

    # 清除旧的 handlers
    for h in root_logger.handlers[:]:
        root_logger.removeHandler(h)

    for h in handlers:
        root_logger.addHandler(h)

    root_logger.info("Logging system initialized (level=%s)", logging.getLevelName(level))


def get_logger(name: str) -> logging.Logger:
    """
    获取一个以 Tale 为父级的 logger

    Args:
        name: 模块名，通常传 __name__

    Returns:
        配置好的 Logger 实例
    """
    if name in _loggers:
        return _loggers[name]

    # 统一挂在 Tale 命名空间下
    logger_name = name if name.startswith("Tale") else f"Tale.{name}"
    logger = logging.getLogger(logger_name)
    _loggers[name] = logger
    return logger
