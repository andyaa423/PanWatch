"""Tushare Pro 官方 SDK 的共享客户端与限速器。"""

from __future__ import annotations

import os
import threading
import time
from collections import deque
from typing import Any


class TushareUnavailableError(RuntimeError):
    """Tushare SDK 或 token 不可用时给出可操作的错误。"""


class TushareRateLimiter:
    """滚动一分钟窗口限速器；默认与 10000 积分档 500 次/分钟对齐。"""

    def __init__(self, limit: int = 500, window_seconds: float = 60.0) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._calls: deque[float] = deque()
        self._lock = threading.Lock()

    def acquire(self) -> None:
        while True:
            with self._lock:
                now = time.monotonic()
                while self._calls and now - self._calls[0] >= self.window_seconds:
                    self._calls.popleft()
                if len(self._calls) < self.limit:
                    self._calls.append(now)
                    return
                wait_seconds = max(0.0, self.window_seconds - (now - self._calls[0]))
            time.sleep(wait_seconds)


_RATE_LIMITER = TushareRateLimiter()


def get_tushare_pro(config: dict[str, Any] | None = None):
    """按数据源 token（优先）或 ``TUSHARE_TOKEN`` 建立官方 Pro 客户端。

    依赖采用惰性导入，未启用 Tushare 的安装不受影响；调用前统一执行限速。
    """
    token = str((config or {}).get("token") or os.getenv("TUSHARE_TOKEN") or "").strip()
    if not token:
        raise TushareUnavailableError("未配置 Tushare Token，请在数据源设置中填写或设置 TUSHARE_TOKEN")
    try:
        import tushare as ts
    except ImportError as exc:
        raise TushareUnavailableError("未安装 tushare，请安装项目依赖后重试") from exc
    _RATE_LIMITER.acquire()
    return ts.pro_api(token)
