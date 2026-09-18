from datetime import datetime, timedelta, timezone

from src.modules.strategy import intraday_event_gate as gate


def _kline(*, trend="多头排列", macd="金叉", kdj="金叉", obv=5, mfi=60, close=11, support=10, resistance=12):
    return {"trend": trend, "macd_status": macd, "kdj_status": kdj, "macd_hist": 1,
            "obv_change": obv, "mfi": mfi, "last_close": close, "support": support, "resistance": resistance}


def test_only_first_run_and_meaningful_change_trigger_ai(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    now = datetime(2026, 9, 18, 2, tzinfo=timezone.utc)
    first = gate.check_trigger(symbol="600226", change_pct=0.2, volume_ratio=1, kline_summary=_kline(), price_threshold=3, volume_threshold=2, now=now)
    assert first.should_analyze and "first_analysis" in first.reasons
    gate.mark_analyzed("600226", first.snapshot, now)
    quiet = gate.check_trigger(symbol="600226", change_pct=0.2, volume_ratio=1, kline_summary=_kline(), price_threshold=3, volume_threshold=2, now=now + timedelta(minutes=5))
    assert not quiet.should_analyze
    changed = gate.check_trigger(symbol="600226", change_pct=0.2, volume_ratio=1, kline_summary=_kline(obv=-1, mfi=60), price_threshold=3, volume_threshold=2, now=now + timedelta(minutes=10))
    assert changed.should_analyze and "volume_confirmation_changed" in changed.reasons


def test_heartbeat_and_support_cross_trigger(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    now = datetime(2026, 9, 18, 2, tzinfo=timezone.utc)
    first = gate.check_trigger(symbol="1", change_pct=0, volume_ratio=1, kline_summary=_kline(), price_threshold=3, volume_threshold=2, now=now)
    gate.mark_analyzed("1", first.snapshot, now)
    heartbeat = gate.check_trigger(symbol="1", change_pct=0, volume_ratio=1, kline_summary=_kline(), price_threshold=3, volume_threshold=2, now=now + timedelta(minutes=121))
    assert "heartbeat" in heartbeat.reasons
    crossed = gate.check_trigger(symbol="1", change_pct=0, volume_ratio=1, kline_summary=_kline(close=9), price_threshold=3, volume_threshold=2, now=now + timedelta(minutes=5))
    assert "support_resistance_crossed" in crossed.reasons
