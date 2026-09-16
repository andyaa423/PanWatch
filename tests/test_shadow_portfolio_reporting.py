from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.modules.portfolio.api import shadow
from src.platform.persistence.database import Base
from src.platform.persistence.models import ShadowPortfolioNav


def test_summary_reads_formal_nav_rows_and_adds_benchmark(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    db.add_all([
        ShadowPortfolioNav(nav_date="2026-09-16", baseline_value=100, shadow_value=100),
        ShadowPortfolioNav(nav_date="2026-09-17", baseline_value=105, shadow_value=108),
    ])
    db.commit()
    monkeypatch.setattr(shadow, "_fetch_benchmark_series", lambda *_: (["2026-09-16", "2026-09-17"], [4000, 4040]))
    result = shadow.shadow_summary(db)
    assert result["empty"] is False
    assert result["curve"][-1] == {"date": "2026-09-17", "baseline": 105.0, "shadow": 108.0, "benchmark": 101.0}
    assert result["metrics"]["total_return"] == 0.08
