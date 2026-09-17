from types import SimpleNamespace
from marketdata.symbol import Symbol
from marketdata.vendors import tushare_corporate_actions as vendor
from marketdata.client import MarketData
from marketdata.defaults import StaticConfigProvider
from marketdata.ports import SourceConfig
from marketdata.registry import VENDOR_CLASSES_BY_TYPE
from marketdata.vendors.base import ShareholdersVendor
from marketdata.types import ShareholderItem

class F:
    empty = False
    def __init__(self, rows): self.rows = rows
    def to_dict(self, _): return self.rows

def test_shareholders_normalizes_code(monkeypatch):
    monkeypatch.setattr(vendor, 'get_tushare_pro', lambda _: SimpleNamespace(stk_holdernumber=lambda **_: F([{'end_date':'20260930','holder_num':123}])) )
    item = vendor.TushareShareholdersVendor().fetch([Symbol.parse('600519','CN')], {})[0]
    assert item.symbol == '600519' and item.holder_num == 123

def test_dividend_maps_tushare_fields(monkeypatch):
    monkeypatch.setattr(vendor, 'get_tushare_pro', lambda _: SimpleNamespace(dividend=lambda **_: F([{'ex_date':'20260916','cash_div_tax':1.2,'stk_bo_rate':0.1,'stk_co_rate':0.2,'div_proc':'实施'}])) )
    item = vendor.TushareDividendVendor().fetch([Symbol.parse('000001','CN')], {})[0]
    assert item.symbol == '000001' and item.dividend_per_share == 1.2 and item.bonus_ratio == 0.2

def test_shareholders_primary_and_fallback_paths(monkeypatch):
    class Tushare(ShareholdersVendor):
        name='tushare'; supports_markets={'CN'}
        def fetch(self, symbols, config): return [ShareholderItem(report_date='20260930', symbol=symbols[0].code, holder_num=2)]
    for failure, expected in ((None, 1), (RuntimeError('error'), 2), (TimeoutError('timeout'), 2), ([], 2)):
        class Eastmoney(ShareholdersVendor):
            name='eastmoney'; supports_markets={'CN'}
            def fetch(self, symbols, config):
                if isinstance(failure, Exception): raise failure
                return failure if failure == [] else [ShareholderItem(report_date='20260930', symbol=symbols[0].code, holder_num=1)]
        monkeypatch.setitem(VENDOR_CLASSES_BY_TYPE, 'shareholders', {'eastmoney': Eastmoney, 'tushare': Tushare})
        items = MarketData(StaticConfigProvider({'shareholders':[SourceConfig(vendor='eastmoney',priority=0),SourceConfig(vendor='tushare',priority=10)]})).shareholders(['000001'],market='CN')
        assert items[0].holder_num == expected
