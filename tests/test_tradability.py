from ashare_research.backtest.tradability import check_trade


def test_missing_bar_proxy_blocks_trade() -> None:
    decision = check_trade(
        side="buy",
        price=10.0,
        limit_up=None,
        limit_down=None,
        limit_status="verified_rule",
        limit_rule_version="test",
        tradability_proxy="unavailable",
    )

    assert not decision.can_trade
    assert decision.reason == "missing_bar_on_open_day"


def test_unknown_limit_status_rejected_by_policy() -> None:
    decision = check_trade(
        side="buy",
        price=10.0,
        limit_up=None,
        limit_down=None,
        limit_status="special_case_unknown",
        limit_rule_version="test",
        unknown_policy="reject_trade",
    )

    assert not decision.can_trade
    assert decision.reason == "special_case_unknown"
