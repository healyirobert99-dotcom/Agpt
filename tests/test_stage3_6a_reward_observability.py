from ashare_research.mining.stage3_6a import reward_distribution_summary, sortino_diagnostic


def test_sortino_unavailable_reason_no_negative_returns(tmp_path) -> None:
    run_dir = tmp_path / "bt"
    run_dir.mkdir()
    (run_dir / "daily_account.csv").write_text("trade_date,net_return\n20240101,0.0\n20240102,0.01\n", encoding="utf-8")

    diag = sortino_diagnostic({"sortino": None, "trade_count": 1}, str(run_dir))

    assert diag["sortino_status"] == "unavailable"
    assert diag["failure_reason"] == "no_negative_return_observation"


def test_reward_distribution_does_not_turn_unavailable_into_zero() -> None:
    summary = reward_distribution_summary([{"reward": None}, {"reward": float("nan")}, {"reward": -1.0}, {"reward": 2.0}])

    assert summary["finite_count"] == 2
    assert summary["zero_reward_count"] == 0
    assert summary["mean"] == 0.5
