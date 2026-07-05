from ashare_research.backtest.tradability import check_trade


def test_limit_up_open_blocks_buy() -> None:
    decision = check_trade(
        side="buy",
        price=12.10,
        limit_up=12.10,
        limit_down=9.90,
        limit_status="verified_rule",
        limit_rule_version="test",
    )

    assert not decision.can_trade
    assert decision.reason == "limit_up_open"


def test_limit_down_open_blocks_sell() -> None:
    decision = check_trade(
        side="sell",
        price=8.98,
        limit_up=10.98,
        limit_down=8.98,
        limit_status="verified_rule",
        limit_rule_version="test",
    )

    assert not decision.can_trade
    assert decision.reason == "limit_down_open"
