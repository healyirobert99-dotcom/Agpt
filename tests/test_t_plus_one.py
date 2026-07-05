import pytest

from ashare_research.backtest.portfolio import Account


def test_same_day_buy_is_not_available_to_sell() -> None:
    account = Account(10000.0)
    account.buy("000001.SZ", 300, 10.0, "20240102", 20)
    account.refresh_available("20240102")

    with pytest.raises(ValueError, match="unavailable_quantity"):
        account.sell("000001.SZ", 100, 10.5, 20)

    account.refresh_available("20240103")
    account.sell("000001.SZ", 100, 10.5, 20)
    assert account.positions["000001.SZ"].quantity == 200
