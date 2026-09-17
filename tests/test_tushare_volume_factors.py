from __future__ import annotations

from src.platform.marketdata.collectors import kline_collector as kc


class _Frame:
    def __init__(self, rows):
        self.rows = rows

    def to_dict(self, orient):
        assert orient == "records"
        return list(self.rows)


class _Pro:
    def __init__(self):
        self.calls = []

    def stk_factor_pro(self, **kwargs):
        self.calls.append(kwargs)
        # 故意倒序以外的输入，验证实现按 trade_date 而非返回顺序取最新值。
        return _Frame([
            {"trade_date": "20260915", "obv_qfq": 100.0, "mfi_qfq": 51.0},
            {"trade_date": "20260916", "obv_qfq": 125.0, "mfi_qfq": 58.0},
        ])


def test_tushare_ts_code_maps_internal_a_share_codes():
    assert kc._tushare_ts_code("600000") == "600000.SH"
    assert kc._tushare_ts_code("000001") == "000001.SZ"
    assert kc._tushare_ts_code("300750.SZ") == "300750.SZ"
    assert kc._tushare_ts_code("HK.00700") is None


def test_volume_factor_mapping_uses_two_rows_for_obv_direction(monkeypatch):
    kc.clear_kline_cache()
    pro = _Pro()
    monkeypatch.setattr(kc, "_get_tushare_pro", lambda: pro)

    out = kc._latest_tushare_volume_factors("000001")

    assert pro.calls == [{
        "ts_code": "000001.SZ",
        "limit": 2,
        "fields": "ts_code,trade_date,obv_qfq,mfi_qfq",
    }]
    assert out == {
        "obv": 125.0,
        "obv_change": 25.0,
        "mfi": 58.0,
        "factor_trade_date": "20260916",
        "factor_source": "tushare_stk_factor_pro",
    }


def test_volume_factors_fail_soft_when_provider_is_unavailable(monkeypatch):
    kc.clear_kline_cache()
    monkeypatch.setattr(kc, "_get_tushare_pro", lambda: (_ for _ in ()).throw(RuntimeError("offline")))
    assert kc._latest_tushare_volume_factors("600000") is None
