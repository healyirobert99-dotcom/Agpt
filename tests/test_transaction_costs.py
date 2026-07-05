import pytest

from ashare_research.backtest.costs import bps_to_rate, transaction_cost


def test_one_way_bps_costs() -> None:
    assert bps_to_rate(10) == pytest.approx(0.001)
    assert bps_to_rate(20) == pytest.approx(0.002)
    assert bps_to_rate(40) == pytest.approx(0.004)
    assert transaction_cost(12345.0, 20) == pytest.approx(24.69)
    assert transaction_cost(-12345.0, 20) == pytest.approx(24.69)
