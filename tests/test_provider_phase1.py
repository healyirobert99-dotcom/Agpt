from pathlib import Path

from ashare_research.data.local_sqlite_provider import LocalSQLiteProvider


ROOT = Path(__file__).resolve().parents[1]
RESEARCH_DB = ROOT / "stock-data" / "ashare_research.sqlite3"
RAW_DB = ROOT / "stock-data" / "a_stock_selector.sqlite3"


def provider() -> LocalSQLiteProvider:
    return LocalSQLiteProvider(RESEARCH_DB, RAW_DB)


def test_provider_filters_dates_symbols_and_batches() -> None:
    p = provider()
    df = p.get_daily_bars("20240101", "20240131", symbols=["000001.SZ"], columns=["trade_date", "ts_code", "close"])
    assert not df.empty
    assert set(df["ts_code"]) == {"000001.SZ"}
    assert df["trade_date"].min() >= "20240101"
    batches = list(p.get_daily_bars("20240101", "20240131", symbols=["000001.SZ"], columns=["trade_date", "ts_code"], batch_size=3))
    assert batches
    assert all(len(b) <= 3 for b in batches)


def test_trade_calendar_and_derived_boundaries() -> None:
    p = provider()
    cal = p.get_trade_calendar("20240101", "20240110")
    assert not cal.empty
    flags = p.get_tradability_flags("20240101", "20240131", symbols=["000001.SZ"])
    if not flags.empty:
        assert "is_suspended" not in flags.columns
        assert set(flags["tradability_proxy"]).issubset({"unavailable"})
    limits = p.get_limit_prices("20240101", "20240131", symbols=["000001.SZ"])
    assert {"limit_derivation_status", "limit_rule_version", "rule_source"}.issubset(limits.columns)


def test_csi800_asof_no_future_backfill() -> None:
    p = provider()
    early = p.get_index_constituents("CSI800", "20190101", "20190110")
    assert early.empty
    df = p.get_index_constituents("CSI800", "20240102", "20240105")
    assert not df.empty
    assert (df["snapshot_date"] <= df["effective_trade_date"]).all()

