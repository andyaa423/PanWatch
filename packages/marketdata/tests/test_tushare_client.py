import sys
import types

import pytest

from marketdata.vendors.tushare_client import (
    TushareRateLimiter,
    TushareUnavailableError,
    get_tushare_pro,
)


def test_get_tushare_pro_uses_datasource_token(monkeypatch):
    seen = []
    monkeypatch.setitem(sys.modules, "tushare", types.SimpleNamespace(pro_api=lambda token: seen.append(token) or "pro"))

    assert get_tushare_pro({"token": "from-source"}) == "pro"
    assert seen == ["from-source"]


def test_get_tushare_pro_requires_configured_token(monkeypatch):
    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
    with pytest.raises(TushareUnavailableError, match="Token"):
        get_tushare_pro({})


def test_limiter_records_calls_within_limit():
    limiter = TushareRateLimiter(limit=2)
    limiter.acquire()
    limiter.acquire()
    assert len(limiter._calls) == 2
