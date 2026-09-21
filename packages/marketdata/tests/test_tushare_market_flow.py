from types import SimpleNamespace

from marketdata.symbol import Symbol
from marketdata.vendors import tushare_market_flow as flow
from marketdata.client import MarketData
from marketdata.defaults import StaticConfigProvider
from marketdata.ports import SourceConfig
from marketdata.registry import VENDOR_CLASSES_BY_TYPE
from marketdata.vendors.base import MarginVendor
from marketdata.types import MarginItem


class _Frame:
    empty = False
    def __init__(self, rows): self.rows = rows
    def to_dict(self, orient): return self.rows


def test_dragon_tiger_normalizes_tushare_code(monkeypatch):
    pro = SimpleNamespace(
        top_list=lambda **_: _Frame([{"trade_date": "20260916", "ts_code": "600000.SH", "name": "浦发银行", "net_amount": 123456.0}]),
        top_inst=lambda **_: _Frame([]),
    )
    monkeypatch.setattr(flow, "get_tushare_pro", lambda _: pro)
    item = flow.TushareDragonTigerVendor().fetch([], {"date": "2026-09-16"})[0]
    assert item.symbol == "600000"
    assert item.net_buy == 123456.0


def test_margin_keeps_tushare_amounts_in_yuan(monkeypatch):
    pro = SimpleNamespace(margin_detail=lambda **_: _Frame([{
        "trade_date": "20260916", "rzye": 120000000.0, "rqye": 3000000.0,
        "rzmre": 8000000.0, "rzche": 6000000.0, "rqmcl": 100.0, "rqchl": 80.0,
        "rzrqye": 123000000.0,
    }]))
    monkeypatch.setattr(flow, "get_tushare_pro", lambda _: pro)
    item = flow.TushareMarginVendor().fetch([Symbol.parse("000001", "CN")], {})[0]
    assert item.symbol == "000001"
    assert item.rz_balance == 120000000.0
    assert item.total_balance == 123000000.0


def test_margin_falls_back_to_tushare_when_eastmoney_fails(monkeypatch):
    class BrokenEastmoney(MarginVendor):
        name = "eastmoney"; supports_markets = {"CN"}
        def fetch(self, symbols, config): raise RuntimeError("eastmoney down")
    class TushareFallback(MarginVendor):
        name = "tushare"; supports_markets = {"CN"}
        def fetch(self, symbols, config): return [MarginItem(date="2026-09-16", symbol=symbols[0].code, total_balance=1.0)]
    monkeypatch.setitem(VENDOR_CLASSES_BY_TYPE, "margin", {"eastmoney": BrokenEastmoney, "tushare": TushareFallback})
    data = MarketData(StaticConfigProvider({"margin": [
        SourceConfig(vendor="eastmoney", priority=0), SourceConfig(vendor="tushare", priority=10),
    ]})).margin(["000001"], market="CN")
    assert data[0].total_balance == 1.0


def test_margin_keeps_eastmoney_when_primary_is_healthy(monkeypatch):
    class HealthyEastmoney(MarginVendor):
        name = "eastmoney"; supports_markets = {"CN"}
        def fetch(self, symbols, config): return [MarginItem(date="2026-09-16", symbol=symbols[0].code, total_balance=2.0)]
    class MustNotRunTushare(MarginVendor):
        name = "tushare"; supports_markets = {"CN"}
        def fetch(self, symbols, config): raise AssertionError("不应切换到 Tushare")
    monkeypatch.setitem(VENDOR_CLASSES_BY_TYPE, "margin", {"eastmoney": HealthyEastmoney, "tushare": MustNotRunTushare})
    data = MarketData(StaticConfigProvider({"margin": [SourceConfig(vendor="eastmoney", priority=0), SourceConfig(vendor="tushare", priority=10)]})).margin(["000001"], market="CN")
    assert data[0].total_balance == 2.0


def test_margin_falls_back_on_timeout_or_empty_data(monkeypatch):
    class TushareFallback(MarginVendor):
        name = "tushare"; supports_markets = {"CN"}
        def fetch(self, symbols, config): return [MarginItem(date="2026-09-16", symbol=symbols[0].code, total_balance=3.0)]
    for failure in (TimeoutError("eastmoney timeout"), []):
        class EastmoneyFailure(MarginVendor):
            name = "eastmoney"; supports_markets = {"CN"}
            def fetch(self, symbols, config):
                if isinstance(failure, Exception): raise failure
                return failure
        monkeypatch.setitem(VENDOR_CLASSES_BY_TYPE, "margin", {"eastmoney": EastmoneyFailure, "tushare": TushareFallback})
        data = MarketData(StaticConfigProvider({"margin": [SourceConfig(vendor="eastmoney", priority=0), SourceConfig(vendor="tushare", priority=10)]})).margin(["000001"], market="CN")
        assert data[0].total_balance == 3.0
