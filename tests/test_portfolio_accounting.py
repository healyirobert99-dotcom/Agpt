import pytest

from ashare_research.backtest.portfolio import Account


def test_buy_sell_cash_cost_and_positions() -> None:
    account = Account(10000.0)

    buy_cost = account.buy("000001.SZ", 300, 10.0, "20240102", 20)
    assert buy_cost == pytest.approx(6.0)
    assert account.cash == pytest.approx(6994.0)
    assert account.positions["000001.SZ"].quantity == 300
    assert account.positions["000001.SZ"].available_quantity == 0

    account.refresh_available("20240103")
    sell_cost = account.sell("000001.SZ", 100, 11.0, 20)
    assert sell_cost == pytest.approx(2.2)
    assert account.cash == pytest.approx(8091.8)
    assert account.positions["000001.SZ"].quantity == 200
    assert account.cumulative_cost == pytest.approx(8.2)


def test_failed_buy_does_not_create_negative_cash() -> None:
    account = Account(1000.0)

    with pytest.raises(ValueError, match="insufficient_cash"):
        account.buy("000001.SZ", 200, 10.0, "20240102", 20)

    assert account.cash == 1000.0
    assert account.positions == {}


def test_missing_close_carries_last_price_with_explicit_flag() -> None:
    account = Account(10000.0)
    account.buy("000001.SZ", 300, 10.0, "20240102", 20)

    market_value, rows = account.mark_to_market({})

    assert market_value == 3000.0
    assert rows[0]["valuation_status"] == "missing_close_carried_last_price"
