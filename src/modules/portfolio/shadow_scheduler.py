"""每日影子组合收盘净值任务。"""
from __future__ import annotations

import logging
from datetime import date

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from src.modules.portfolio.shadow_execution import execute_pending_trades, record_daily_nav
from src.platform.marketdata.collectors.kline_collector import KlineCollector
from src.platform.marketdata.models import MarketCode
from src.platform.persistence.database import SessionLocal

logger = logging.getLogger(__name__)


class ShadowPortfolioScheduler:
    def __init__(self, timezone: str = "Asia/Shanghai"):
        self.scheduler = AsyncIOScheduler(timezone=timezone)

    async def _execute_then_record(self):
        """按固定顺序处理已初始化组合：先成交，再记录当日净值。"""
        db = SessionLocal()
        try:
            def bars(symbol, market):
                return KlineCollector(MarketCode(market)).get_klines(symbol, days=10)

            def close(symbol, market, nav_date):
                return next((float(bar.close) for bar in bars(symbol, market) if bar.date == nav_date), None)

            executed = execute_pending_trades(db, bars)
            nav = record_daily_nav(db, date.today().isoformat(), close)
            if executed or nav:
                db.commit()
        except Exception:
            db.rollback()
            logger.exception("影子组合日净值记录失败")
        finally:
            db.close()

    def start(self):
        self.scheduler.add_job(self._execute_then_record, "cron", hour=15, minute=20, id="shadow_portfolio_execution_and_nav", replace_existing=True, coalesce=True)
        self.scheduler.start()

    def shutdown(self):
        self.scheduler.shutdown(wait=False)
