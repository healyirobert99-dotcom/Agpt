import sqlite3
from pathlib import Path

from ashare_research.data.local_sqlite_provider import LocalSQLiteProvider


def _make_sqlite(path: Path) -> None:
    with sqlite3.connect(path) as con:
        con.executescript(
            """
            CREATE TABLE daily_price (
              trade_date TEXT, ts_code TEXT, open REAL, high REAL, low REAL, close REAL,
              raw_open REAL, raw_high REAL, raw_low REAL, raw_close REAL,
              volume REAL, amount REAL, adj_factor REAL, source TEXT
            );
            CREATE TABLE daily_basic (ts_code TEXT, trade_date TEXT, turnover_rate REAL);
            CREATE TABLE derived_limit_price (ts_code TEXT, trade_date TEXT, pre_close REAL);
            CREATE INDEX idx_daily_price_date ON daily_price(trade_date);
            CREATE INDEX idx_daily_basic_pk ON daily_basic(ts_code, trade_date);
            CREATE INDEX idx_derived_limit_price_code_date ON derived_limit_price(ts_code, trade_date);
            """
        )
        rows = [
            ("20240102", "000001.SZ", 1, 2, 1, 2, 1, 2, 1, 2, 100, 200, 1, "tushare_raw"),
            ("20240102", "000002.SZ", 2, 3, 2, 3, 2, 3, 2, 3, 110, 220, 1, "tushare_raw"),
            ("20240103", "000001.SZ", 3, 4, 3, 4, 3, 4, 3, 4, 120, 240, 1, "other"),
            ("20240103", "000003.SZ", 4, 5, 4, 5, 4, 5, 4, 5, 130, 260, 1, "tushare_raw"),
        ]
        con.executemany("INSERT INTO daily_price VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
        con.executemany("INSERT INTO daily_basic VALUES (?,?,?)", [(r[1], r[0], 1.5) for r in rows])
        con.executemany("INSERT INTO derived_limit_price VALUES (?,?,?)", [(r[1], r[0], r[3]) for r in rows])


def test_diagnostic_sql_matches_formal_daily_bar_query(tmp_path: Path) -> None:
    db = tmp_path / "test.sqlite3"
    _make_sqlite(db)
    provider = LocalSQLiteProvider(db)

    query = provider.daily_bars_query("20240102", "20240103")
    formal = provider.get_daily_bars("20240102", "20240103")

    assert query["params"] == ["20240102", "20240103"]
    assert query["source_filter"] == "p.source = 'tushare_raw'"
    assert "p.source = 'tushare_raw'" in query["sql"]
    assert "ORDER BY trade_date, ts_code" in query["sql"]
    assert len(formal) == 3
    assert set(formal["source"]) == {"tushare_raw"}


def test_fetchmany_probe_matches_formal_rows_and_writes_progress(tmp_path: Path) -> None:
    db = tmp_path / "test.sqlite3"
    _make_sqlite(db)
    provider = LocalSQLiteProvider(db)
    progress = tmp_path / "progress.json"

    formal = provider.get_daily_bars("20240102", "20240103")
    probe = provider.probe_daily_bars_fetchmany("20240102", "20240103", batch_size=2, progress_path=progress)

    assert probe["rows"] == len(formal)
    assert probe["columns"] == list(formal.columns)
    assert probe["last_trade_date"] == formal.iloc[-1]["trade_date"]
    assert probe["last_ts_code"] == formal.iloc[-1]["ts_code"]
    assert probe["content_hash"]
    assert progress.exists()
    assert "daily_bars_query_completed" in progress.read_text(encoding="utf-8")
