"""Tushare Pro 的股东户数与分红备源。"""
from __future__ import annotations

from marketdata.symbol import Symbol
from marketdata.types import DividendItem, ShareholderItem
from marketdata.vendors.base import DividendVendor, ShareholdersVendor
from marketdata.vendors.tushare_client import get_tushare_pro


def _ts_code(symbol: Symbol) -> str:
    return f"{symbol.code}.{'SH' if symbol.code.startswith(('6', '9')) else 'SZ'}"


def _rows(frame):
    return [] if frame is None or getattr(frame, 'empty', True) else frame.to_dict('records')


def _number(value):
    try: return None if value in (None, '') else float(value)
    except (TypeError, ValueError): return None


class TushareShareholdersVendor(ShareholdersVendor):
    name = 'tushare'; supports_markets = {'CN'}
    def fetch(self, symbols, config):
        pro = get_tushare_pro(config); out = []
        for symbol in symbols:
            rows = _rows(pro.stk_holdernumber(ts_code=_ts_code(symbol)))
            if rows:
                row = rows[0]
                out.append(ShareholderItem(report_date=str(row.get('end_date') or ''), symbol=symbol.code, holder_num=int(row['holder_num']) if row.get('holder_num') is not None else None))
        return out


class TushareDividendVendor(DividendVendor):
    name = 'tushare'; supports_markets = {'CN'}
    def fetch(self, symbols, config):
        pro = get_tushare_pro(config); out = []
        for symbol in symbols:
            for row in _rows(pro.dividend(ts_code=_ts_code(symbol))):
                out.append(DividendItem(ex_date=str(row.get('ex_date') or ''), symbol=symbol.code, dividend_per_share=_number(row.get('cash_div_tax')), transfer_ratio=_number(row.get('stk_bo_rate')), bonus_ratio=_number(row.get('stk_co_rate')), progress=str(row.get('div_proc') or '')))
        return out
