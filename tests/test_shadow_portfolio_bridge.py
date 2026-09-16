from src.modules.portfolio.shadow_bridge import DEFAULT_REDUCE_TARGET_PCT, normalize_shadow_decision


def test_sell_and_reduce_default_to_quarter_target():
    """没有结构化比例时，卖出和减仓建议都保留四分之一仓位。"""
    assert normalize_shadow_decision(action="sell") == normalize_shadow_decision(action="reduce")
    assert normalize_shadow_decision(action="sell").target_weight_pct == DEFAULT_REDUCE_TARGET_PCT


def test_stop_loss_context_exits_without_parsing_free_text_numbers():
    """止损语境直接清仓，不从说明中的数字猜测仓位。"""
    rule = normalize_shadow_decision(action="sell", reason="跌破支撑，执行止损，建议关注 20 日线")
    assert rule.action == "exit"
    assert rule.target_weight_pct == 0


def test_hold_does_not_create_shadow_trade():
    """持有建议不产生无意义的影子成交。"""
    assert normalize_shadow_decision(action="hold") is None
