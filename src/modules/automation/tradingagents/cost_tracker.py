"""TradingAgents 月度成本预算与单次成本估算。

总成本存于 ``AnalysisHistory.raw_data[\"cost_usd\"]``；深度模型成本另外存于
``deep_cost_usd``。后者只统计实际使用 deep_model 的阶段，供硬预算闸门使用。
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any

from src.platform.persistence.database import SessionLocal
from src.platform.persistence.models import AnalysisHistory, LogEntry

logger = logging.getLogger(__name__)


def _month_records(agent_name: str) -> list[AnalysisHistory]:
    """读取本月 TradingAgents 分析记录。"""
    month_prefix = datetime.now(timezone.utc).strftime("%Y-%m")
    db = SessionLocal()
    try:
        return (
            db.query(AnalysisHistory)
            .filter(
                AnalysisHistory.agent_name == agent_name,
                AnalysisHistory.analysis_date.like(f"{month_prefix}-%"),
            )
            .all()
        )
    finally:
        db.close()


def _budget_status(used: float, monthly_budget_usd: float, runs_this_month: int) -> dict:
    limit = float(monthly_budget_usd)
    used = round(float(used), 4)
    return {
        "used": used,
        "remaining": round(max(0.0, limit - used), 4),
        "limit": limit,
        "exceeded": bool(limit > 0 and used >= limit),
        "runs_this_month": int(runs_this_month),
    }


def check_budget(monthly_budget_usd: float, agent_name: str = "tradingagents") -> dict:
    """统计本月所有模型的累计成本。保留给历史报表兼容使用。"""
    if float(monthly_budget_usd) <= 0:
        return _budget_status(0.0, 0.0, 0)
    try:
        records = _month_records(agent_name)
        return _budget_status(
            sum(_extract_cost(r.raw_data) for r in records),
            monthly_budget_usd,
            len(records),
        )
    except Exception as exc:
        logger.warning("[TA成本] 总预算查询失败,默认放行: %s", exc)
        return _budget_status(0.0, monthly_budget_usd, 0)


def check_deep_budget(monthly_budget_usd: float, agent_name: str = "tradingagents") -> dict:
    """统计本月实际深度模型的成本，供下一次图构建前的硬闸门使用。

    历史记录没有 ``deep_cost_usd`` 时按 0 处理：旧记录无法可靠地从总成本反推
    深度/快速模型占比，因此宁可不把它们误计入深度模型预算。
    """
    if float(monthly_budget_usd) <= 0:
        return _budget_status(0.0, 0.0, 0)
    try:
        now = datetime.now(timezone.utc)
        month_start = datetime(now.year, now.month, 1)
        db = SessionLocal()
        try:
            # 每个 on_llm_end 都有一条独立日志，因此同日复跑、失败或超时前
            # 已经完成的深度调用也不会被 AnalysisHistory 的日级覆盖语义吞掉。
            rows = (
                db.query(LogEntry)
                .filter(
                    LogEntry.agent_name == agent_name,
                    LogEntry.event == "ta_progress",
                    LogEntry.timestamp >= month_start,
                )
                .all()
            )
        finally:
            db.close()
        deep_calls = [
            _extract_deep_log_cost(row.tags)
            for row in rows
            if _is_deep_cost_log(row.tags)
        ]
        if deep_calls:
            return _budget_status(sum(deep_calls), monthly_budget_usd, len(deep_calls))

        # 首次升级前没有逐调用日志时，回退到已经保存的深度成本字段。
        records = _month_records(agent_name)
        return _budget_status(
            sum(_extract_deep_cost(r.raw_data) for r in records),
            monthly_budget_usd,
            len(records),
        )
    except Exception as exc:
        # 成本闸门查询失败时必须降级，不能以“默认放行”绕过硬上限。
        logger.exception("[TA成本] 深度预算查询失败,为保护预算改用 quick_model: %s", exc)
        status = _budget_status(monthly_budget_usd, monthly_budget_usd, 0)
        status["query_failed"] = True
        return status


def choose_deep_model(
    *,
    deep_model: str,
    quick_model: str,
    budget: dict[str, Any],
    action: str = "fallback_quick",
) -> tuple[str, dict[str, Any]]:
    """在创建 TradingAgents 图之前决定本轮深度阶段应使用的模型。

    上游会在图启动时一次性构造 LLM 客户端，因而此处是每次深度分析发起
    *任何* deep_model 请求之前唯一可靠的切换点。达到上限后，所有原本深度
    阶段统一降到 quick_model，避免某个后续节点静默继续消费昂贵模型。
    """
    requested = (deep_model or "").strip()
    fallback = (quick_model or requested).strip()
    if not requested or requested == fallback or not budget.get("exceeded"):
        return requested, {
            "mode": "deep" if requested and requested != fallback else "single_model",
            "requested_model": requested,
            "effective_model": requested or fallback,
            "budget": budget,
        }

    if action != "fallback_quick":
        raise ValueError(f"不支持的 deep_budget_action: {action}")
    if not fallback:
        raise RuntimeError("深度预算已耗尽，但未配置 quick_model，无法安全降级")

    logger.warning(
        "[TA预算] 深度模型月度上限已达 ($%.4f / $%.4f)，本次改用 quick_model=%s",
        budget.get("used", 0.0), budget.get("limit", 0.0), fallback,
    )
    return fallback, {
        "mode": "fallback_quick",
        "requested_model": requested,
        "effective_model": fallback,
        "budget": budget,
        "warning": "deep_model 月度预算已达上限，本次深度阶段已降级为 quick_model。",
    }


def _extract_cost(raw_data: Any) -> float:
    """从 AnalysisHistory.raw_data 提取总 cost_usd。"""
    return _as_float(raw_data.get("cost_usd")) if isinstance(raw_data, dict) else 0.0


def _extract_deep_cost(raw_data: Any) -> float:
    """从 AnalysisHistory.raw_data 提取 deep_cost_usd。"""
    return _as_float(raw_data.get("deep_cost_usd")) if isinstance(raw_data, dict) else 0.0


def _is_deep_cost_log(tags: Any) -> bool:
    return isinstance(tags, dict) and tags.get("action") == "llm_end" and bool(tags.get("is_deep_model"))


def _extract_deep_log_cost(tags: Any) -> float:
    return _as_float(tags.get("call_cost")) if isinstance(tags, dict) else 0.0


def _as_float(value: Any) -> float:
    try:
        return float(value) if value is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def estimate_cost(
    *,
    debate_rounds: int,
    selected_analysts: list[str],
    model: str = "deepseek-chat",
) -> dict:
    """单次分析成本估算；只用于展示，预算闸门依赖实际落库成本。"""
    n_analysts = len(selected_analysts or [])
    prompt_tokens = n_analysts * 5000 + max(1, debate_rounds) * 12000 + 15000
    completion_tokens = n_analysts * 2000 + max(1, debate_rounds) * 4000 + 3000
    pricing = {
        "deepseek-flash": (0.15, 0.60),
        "deepseek-chat": (0.14, 0.28),
        "deepseek-v4-pro": (1.32, 3.96),
        "deepseek-reasoner": (0.55, 2.19),
        "gpt-4o-mini": (0.15, 0.60),
        "gpt-4o": (2.50, 10.00),
        "claude-sonnet-4": (3.00, 15.00),
        "glm-4-flash": (0.05, 0.20),
    }
    input_rate, output_rate = pricing.get(model.lower(), pricing["deepseek-chat"])
    cost = (prompt_tokens / 1_000_000 * input_rate) + (completion_tokens / 1_000_000 * output_rate)
    return {
        "model": model,
        "prompt_tokens_est": prompt_tokens,
        "completion_tokens_est": completion_tokens,
        "cost_low_usd": round(cost * 2, 4),
        "cost_high_usd": round(cost * 5, 4),
    }


def get_today_cache_key(symbol: str, market: str, debate_rounds: int, model: str) -> str:
    """生成同标的同日的缓存键,用于跳过重复 LLM 调用。"""
    today = date.today().isoformat()
    return f"{market}:{symbol}:{today}:r{debate_rounds}:{model}"
