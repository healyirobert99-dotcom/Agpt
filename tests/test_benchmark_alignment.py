from ashare_research.backtest.benchmark import benchmark_status


def test_missing_formal_benchmark_is_explicit() -> None:
    status = benchmark_status(None, None)

    assert status["benchmark_unavailable"] is True
    assert "not configured" in status["reason"]
