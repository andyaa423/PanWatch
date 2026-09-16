"""TradingAgents 决策到影子组合待执行交易的桥接。

本模块只入队，成交时间、价格和费用由后续执行引擎处理。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from src.platform.persistence.models import AnalysisHistory, ShadowPosition, ShadowTrade

DEFAULT_REDUCE_TARGET_PCT = 25.0
_STOP_LOSS_TERMS = ("止损", "破位")


@dataclass(frozen=True)
class ShadowDecision:
    action: str
    target_weight_pct: float


def normalize_shadow_decision(*, action: str, reason: str = "", rating: str = "") -> ShadowDecision | None:
    """把风险类建议归一化为影子组合规则，不从自由文本提取比例。"""
    normalized = (action or "").strip().lower()
    text = f"{reason or ''} {rating or ''}"
    if any(term in text for term in _STOP_LOSS_TERMS):
        return ShadowDecision("exit", 0.0)
    if normalized in {"sell", "reduce", "underweight"}:
        return ShadowDecision("reduce", DEFAULT_REDUCE_TARGET_PCT)
    return None


def enqueue_shadow_decision(db: Session, decision_source: AnalysisHistory) -> int:
    """为已有影子仓位写入待执行记录，返回实际入队数。"""
    raw = decision_source.raw_data if isinstance(decision_source.raw_data, dict) else {}
    suggestion = raw.get("suggestion") if isinstance(raw.get("suggestion"), dict) else {}
    rule = normalize_shadow_decision(
        action=str(suggestion.get("action") or raw.get("decision") or ""),
        reason=str(suggestion.get("reason") or raw.get("final_decision") or ""),
        rating=str(suggestion.get("rating_raw") or raw.get("rating") or ""),
    )
    if not rule:
        return 0
    market = str(raw.get("market_snapshot", {}).get("market") or "CN").upper()
    positions = (
        db.query(ShadowPosition)
        .filter(
            ShadowPosition.stock_symbol == decision_source.stock_symbol,
            ShadowPosition.stock_market == market,
            ShadowPosition.status.in_(("open", "partial")),
        )
        .all()
    )
    created = 0
    for position in positions:
        exists = db.query(ShadowTrade.id).filter(
            ShadowTrade.shadow_position_id == position.id,
            ShadowTrade.decision_source_id == decision_source.id,
        ).first()
        if exists:
            continue
        db.add(ShadowTrade(
            shadow_position_id=position.id,
            decision_source_id=decision_source.id,
            action=rule.action,
            target_weight_pct=rule.target_weight_pct,
            signal_generated_at=decision_source.created_at or datetime.utcnow(),
            status="pending",
        ))
        created += 1
    return created
