"""影子组合的初始化和只读复盘接口。"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from src.modules.portfolio.portfolio_benchmark import _fetch_benchmark_series
from src.modules.portfolio.shadow_execution import initialize_shadow_positions
from src.modules.strategy.backtest.metrics import summarize
from src.platform.persistence.database import get_db
from src.platform.persistence.models import AppSettings, ShadowPortfolioNav, ShadowPosition, ShadowTrade

router = APIRouter()
_INITIALIZED_KEY = "shadow_portfolio_initialized_v1"


@router.post("/shadow/initialize")
def initialize_shadow(db: Session = Depends(get_db)):
    """从当前启用实盘持仓建立一次基线；历史交易不会回补。"""
    if db.query(AppSettings).filter_by(key=_INITIALIZED_KEY).first():
        raise HTTPException(409, "影子组合已初始化；为保证口径一致，不会重复导入后续持仓")
    created = initialize_shadow_positions(db)
    if not created:
        raise HTTPException(400, "没有启用账户的实盘持仓，无法建立影子组合")
    now = datetime.utcnow().isoformat()
    db.add(AppSettings(key=_INITIALIZED_KEY, value=now, description="AI 影子组合首次实仓快照"))
    db.commit()
    return {"created": created, "initialized_at": now}

@router.get("/shadow/summary")
def shadow_summary(db: Session = Depends(get_db)):
    navs = db.query(ShadowPortfolioNav).order_by(ShadowPortfolioNav.nav_date).all()
    if not navs:
        return {"empty": True, "curve": [], "metrics": summarize([], []), "baseline_metrics": summarize([], []), "coverage": {"executed": 0, "pending": 0}}
    baseline, shadow = [float(n.baseline_value) for n in navs], [float(n.shadow_value) for n in navs]
    dates, closes = _fetch_benchmark_series("000300", max(60, len(navs) + 10))
    benchmark_by_date = dict(zip(dates, closes))
    first_benchmark = next((benchmark_by_date.get(n.nav_date) for n in navs if benchmark_by_date.get(n.nav_date)), None)
    curve = [{"date": n.nav_date, "baseline": round(n.baseline_value / baseline[0] * 100, 2), "shadow": round(n.shadow_value / shadow[0] * 100, 2), "benchmark": round(float(benchmark_by_date[n.nav_date]) / first_benchmark * 100, 2) if benchmark_by_date.get(n.nav_date) and first_benchmark else None} for n in navs]
    trades = db.query(ShadowTrade).filter_by(status="executed").all()
    positions = {p.id: p for p in db.query(ShadowPosition).all()}
    pnls = [float((t.fill or {}).get("cash_delta") or 0) - float(t.quantity or 0) * positions[t.shadow_position_id].avg_cost for t in trades if t.shadow_position_id in positions]
    return {"empty": False, "curve": curve, "metrics": summarize(shadow, pnls), "baseline_metrics": summarize(baseline, []), "coverage": {"executed": len(trades), "pending": db.query(ShadowTrade).filter_by(status="pending").count()}}

@router.get("/shadow/{symbol}/{market}")
def shadow_stock(symbol: str, market: str, db: Session = Depends(get_db)):
    positions = db.query(ShadowPosition).filter_by(stock_symbol=symbol, stock_market=market.upper()).all()
    ids = [p.id for p in positions]
    trades = db.query(ShadowTrade).filter(ShadowTrade.shadow_position_id.in_(ids)).all() if ids else []
    return {"positions": [{"quantity": p.quantity, "initial_quantity": p.initial_quantity, "avg_cost": p.avg_cost, "status": p.status} for p in positions], "trades": [{"action": t.action, "quantity": t.quantity, "execution_price": t.execution_price, "status": t.status, "decision_source_id": t.decision_source_id, "signal_generated_at": t.signal_generated_at} for t in trades]}
