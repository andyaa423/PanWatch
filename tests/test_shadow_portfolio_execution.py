from datetime import datetime
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.modules.portfolio.shadow_execution import (
    execute_pending_trades,
    initialize_shadow_positions,
    next_tradable_open,
    record_daily_nav,
)
from src.platform.persistence.database import Base
from src.platform.persistence.models import Account, Position, ShadowPosition, ShadowTrade, Stock


def test_next_tradable_open_never_uses_signal_day_close_or_open():
    """执行价格使用信号日之后的第一根日K开盘价。"""
    bars = [SimpleNamespace(date="2026-09-16", open=10, close=10.5), SimpleNamespace(date="2026-09-17", open=11, close=10.8)]
    assert next_tradable_open(bars, datetime(2026, 9, 16, 14, 30)) == ("2026-09-17", 11.0)


def test_shadow_positions_execute_then_record_nav_end_to_end():
    """实盘导入后，待执行建议按次日开盘成交，随后可产生日终净值。"""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    account = Account(name="测试账户", enabled=True)
    stock = Stock(symbol="600000", name="浦发银行", market="CN")
    db.add_all([account, stock])
    db.flush()
    db.add(Position(account_id=account.id, stock_id=stock.id, cost_price=10, quantity=100))
    db.commit()

    assert initialize_shadow_positions(db) == 1
    shadow = db.query(ShadowPosition).one()
    db.add(ShadowTrade(
        shadow_position_id=shadow.id,
        action="reduce",
        target_weight_pct=25,
        signal_generated_at=datetime(2026, 9, 16, 14, 30),
    ))
    db.commit()

    bars = [
        SimpleNamespace(date="2026-09-16", open=10, close=10.5),
        SimpleNamespace(date="2026-09-17", open=11, close=11.3),
    ]
    assert execute_pending_trades(db, lambda *_: bars) == 1
    db.flush()
    trade = db.query(ShadowTrade).one()
    assert trade.execution_price < 11  # CostModel 的卖出滑点也已生效。
    assert trade.fill["price"] == 11
    assert shadow.quantity == 25

    nav = record_daily_nav(db, "2026-09-17", lambda *_: 11.3)
    assert nav is not None
    assert nav.baseline_value == 1130
    assert nav.shadow_value > 0
