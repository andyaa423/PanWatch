"""Tushare Pro 的龙虎榜与融资融券备源。"""
from __future__ import annotations

from marketdata.symbol import Symbol
from marketdata.types import DragonTigerItem, MarginItem
from marketdata.vendors.base import DragonTigerVendor, MarginVendor
from marketdata.vendors.tushare_client import get_tushare_pro


def _rows(frame):
    return [] if frame is None or getattr(frame, "empty", True) else frame.to_dict("records")


def _number(value):
    try:
        return None if value in (None, "") else float(value)
    except (TypeError, ValueError):
        return None


def _ts_code(symbol: Symbol) -> str:
    if symbol.code.startswith(("6", "9")):
        exchange = "SH"
    elif symbol.code.startswith(("8", "4", "92")):
        exchange = "BJ"
    else:
        exchange = "SZ"
    return f"{symbol.code}.{exchange}"


class TushareDragonTigerVendor(DragonTigerVendor):
    name = "tushare"
    supports_markets = {"CN"}

    def fetch(self, symbols: list[Symbol], config: dict) -> list[DragonTigerItem]:
        date = str((config or {}).get("date") or "").replace("-", "")
        if not date:
            return []
        pro = get_tushare_pro(config)
        rows = _rows(pro.top_list(trade_date=date))
        institution = {}
        for row in _rows(pro.top_inst(trade_date=date)):
            code = str(row.get("ts_code") or "")
            institution[code] = (institution.get(code) or 0) + (_number(row.get("net_buy")) or 0)
        return [DragonTigerItem(
            trade_date=str(row.get("trade_date") or date), symbol=str(row.get("ts_code") or "").split(".")[0],
            name=str(row.get("name") or ""), reason=row.get("reason"), close=_number(row.get("close")),
            change_pct=_number(row.get("pct_change")), net_buy=_number(row.get("net_amount")),
            buy_amt=_number(row.get("buy")), sell_amt=_number(row.get("sell")), turnover_pct=_number(row.get("turnover_rate")),
        ) for row in rows]


class TushareMarginVendor(MarginVendor):
    name = "tushare"
    supports_markets = {"CN"}

    def fetch(self, symbols: list[Symbol], config: dict) -> list[MarginItem]:
        pro = get_tushare_pro(config)
        out = []
        for symbol in symbols:
            rows = _rows(pro.margin_detail(ts_code=_ts_code(symbol)))
            if not rows:
                continue
            row = rows[0]
            out.append(MarginItem(date=str(row.get("trade_date") or ""), symbol=symbol.code,
                rz_balance=_number(row.get("rzye")), rz_buy=_number(row.get("rzmre")),
                rz_repay=_number(row.get("rzche")), rq_balance=_number(row.get("rqye")),
                rq_sell_vol=_number(row.get("rqmcl")), rq_repay_vol=_number(row.get("rqchl")),
                total_balance=_number(row.get("rzrqye"))))
        return out
