from ashare_research.mining.reward import INVALID_REWARD, invalid_reward, reward_from_metrics


def test_reward_uses_sortino_when_trade_count_is_sufficient() -> None:
    result = reward_from_metrics({"sortino": 1.25, "trade_count": 3}, min_trade_count=2)

    assert result.reward == 1.25
    assert result.validity_status == "valid"


def test_reward_rejects_invalid_and_insufficient_trades() -> None:
    assert invalid_reward("bad_formula").reward == INVALID_REWARD

    result = reward_from_metrics({"sortino": 2.0, "trade_count": 0}, min_trade_count=1)

    assert result.reward == INVALID_REWARD
    assert result.failure_reason == "insufficient_trade_count"
