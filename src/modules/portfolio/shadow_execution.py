"""影子组合初始化、次一可交易价格执行和每日净值记录。"""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime

from sqlalchemy.orm import Session

from src.modules.strategy.backtest.cost_model import DEFAULT_COST_MODEL
from src.platform.persistence.models import Account, Position, ShadowPortfolioNav, ShadowPosition, ShadowTrade, Stock


def initialize_shadow_positions(db: Session) -> int:
    """一次性导入当前启用实盘账户持仓；已有影子仓位保持不变。"""
    rows = (db.query(Position, Stock, Account).select_from(Position)
        .join(Stock, Stock.id == Position.stock_id).join(Account, Account.id == Position.account_id)
        .filter(Account.enabled.is_(True)).all())
    created = 0
    for real, stock, account in rows:
        if db.query(ShadowPosition.id).filter_by(account_id=account.id, stock_id=stock.id).first():
            continue
        db.add(ShadowPosition(account_id=account.id, stock_id=stock.id, real_position_id=real.id,
            stock_symbol=stock.symbol, stock_market=stock.market, stock_name=stock.name,
            initial_quantity=int(real.quantity), quantity=int(real.quantity), avg_cost=float(real.cost_price), status="open"))
        created += 1
    return created


def next_tradable_open(bars: list, generated_at: datetime | None) -> tuple[str, float] | None:
    """日K数据下，严格选择信号生成日之后的第一根开盘价。"""
    signal_date = generated_at.date().isoformat() if generated_at else ""
    for bar in sorted(bars, key=lambda item: item.date):
        if bar.date > signal_date and float(bar.open or 0) > 0:
            return bar.date, float(bar.open)
    return None


def execute_pending_trades(db: Session, kline_fetch) -> int:
    """按下一根可交易日K开盘价执行待处理减仓/清仓建议并复用 CostModel。"""
    executed = 0
    for trade in db.query(ShadowTrade).filter_by(status="pending").all():
        position = db.get(ShadowPosition, trade.shadow_position_id)
        if not position or position.quantity <= 0:
            trade.status, trade.skip_reason = "skipped", "影子仓位不存在或已清仓"
            continue
        fill_at = next_tradable_open(kline_fetch(position.stock_symbol, position.stock_market), trade.signal_generated_at)
        if not fill_at:
            continue
        _, price = fill_at
        target = round(position.initial_quantity * float(trade.target_weight_pct or 0) / 100)
        quantity = max(0, int(position.quantity) - target)
        if quantity <= 0:
            trade.status, trade.skip_reason = "skipped", "已达到目标仓位"
            continue
        fill = DEFAULT_COST_MODEL.fill("sell", price, quantity)
        trade.quantity, trade.execution_price, trade.fill = quantity, fill.fill_price, asdict(fill)
        trade.status, trade.executed_at = "executed", datetime.utcnow()
        position.quantity -= quantity
        position.status = "closed" if position.quantity == 0 else "partial"
        executed += 1
    return executed


def record_daily_nav(db: Session, nav_date: str, close_fetch) -> ShadowPortfolioNav | None:
    """使用当日收盘价记录基线和影子净值；现金来自已执行卖出成交。"""
    positions = db.query(ShadowPosition).all()
    if not positions:
        return None
    baseline = shadow = cash = realized = 0.0
    for pos in positions:
        price = close_fetch(pos.stock_symbol, pos.stock_market, nav_date)
        if not price or price <= 0:
            return None
        baseline += pos.initial_quantity * price
        shadow += pos.quantity * price
    for trade in db.query(ShadowTrade).filter_by(status="executed").all():
        fill = trade.fill or {}
        cash += float(fill.get("cash_delta") or 0)
        realized += float(fill.get("cash_delta") or 0) - float(trade.quantity or 0) * db.get(ShadowPosition, trade.shadow_position_id).avg_cost
    shadow += cash
    nav = db.query(ShadowPortfolioNav).filter_by(nav_date=nav_date).first()
    if not nav:
        nav = ShadowPortfolioNav(nav_date=nav_date, baseline_value=baseline, shadow_value=shadow, cash=cash, realized_pnl=realized)
        db.add(nav)
    else:
        nav.baseline_value, nav.shadow_value, nav.cash, nav.realized_pnl = baseline, shadow, cash, realized
    return nav
