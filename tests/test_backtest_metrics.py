import pytest
import pandas as pd

from ashare_research.backtest.metrics import compute_metrics


def test_metrics_use_net_equity_and_actual_filled_trades() -> None:
    accounts = pd.DataFrame(
        [
            {"trade_date": "20240101", "cash": 1000, "total_equity": 1000, "gross_return": 0.0, "net_return": 0.0, "turnover": 0.0, "cumulative_cost": 0.0},
            {"trade_date": "20240102", "cash": 900, "total_equity": 1010, "gross_return": 0.012, "net_return": 0.01, "turnover": 0.1, "cumulative_cost": 2.0},
            {"trade_date": "20240103", "cash": 900, "total_equity": 990, "gross_return": -0.018, "net_return": -0.0198019802, "turnover": 0.0, "cumulative_cost": 2.0},
        ]
    )
    trades = pd.DataFrame(
        [
            {"side": "buy", "status": "filled"},
            {"side": "buy", "status": "unfilled"},
            {"side": "sell", "status": "unfilled"},
        ]
    )

    metrics = compute_metrics(accounts, trades)

    assert metrics["total_return"] == pytest.approx(-0.01)
    assert metrics["trade_count"] == 1
    assert metrics["unfilled_buy_count"] == 1
    assert metrics["unfilled_sell_count"] == 1
    assert metrics["cumulative_cost"] == 2.0
