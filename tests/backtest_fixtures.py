from __future__ import annotations

from pathlib import Path

import pandas as pd

from ashare_research.backtest.engine import BacktestConfig


DATES = [
    "20240101",
    "20240102",
    "20240103",
    "20240104",
    "20240105",
    "20240108",
    "20240109",
    "20240110",
    "20240111",
    "20240112",
    "20240115",
    "20240116",
]
CODES = ["000001.SZ", "300001.SZ", "600001.SH", "688001.SH"]


class FakeProvider:
    def __init__(self) -> None:
        self.bars = _bars()
        self.calendar = pd.DataFrame({"trade_date": DATES})
        self.constituents = _constituents()
        self.limits = _limits()
        self.tradability = pd.DataFrame(
            [
                {
                    "trade_date": "20240116",
                    "ts_code": "688001.SH",
                    "missing_bar_on_open_day": 1,
                    "tradability_proxy": "unavailable",
                    "proxy_reason": "missing_bar_on_open_day",
                    "source_coverage_status": "stock_missing_market_ok",
                    "source": "derived_tradability",
                    "source_record_id": "688001.SH-20240116",
                    "derivation_method": "calendar_open_missing_bar",
                    "rule_version": "test",
                }
            ]
        )
        self.lifecycle = pd.DataFrame(
            [
                {
                    "ts_code": code,
                    "symbol": code[:6],
                    "name": code,
                    "area": None,
                    "industry": None,
                    "market": None,
                    "list_date": "20200101",
                    "delist_date": None,
                    "exchange": code[-2:],
                    "board": None,
                    "list_status": "L",
                    "source": "fixture",
                    "source_record_id": code,
                    "derivation_method": "fixture",
                    "rule_version": "test",
                }
                for code in CODES
            ]
        )
        self.st_status = pd.DataFrame(
            [
                {
                    "ts_code": "300001.SZ",
                    "start_date": "20240101",
                    "end_date": "20240131",
                    "name": "*ST TEST",
                    "historical_is_st": 1,
                    "st_basis": "name_contains_st",
                    "derivation_status": "verified",
                    "source": "historical_st_status",
                    "source_record_id": "300001.SZ-ST",
                    "derivation_method": "namechange_interval",
                    "rule_version": "test",
                }
            ]
        )

    def get_daily_bars(self, start_date: str, end_date: str, *args, **kwargs) -> pd.DataFrame:
        return self.bars[(self.bars["trade_date"] >= start_date) & (self.bars["trade_date"] <= end_date)].copy()

    def get_trade_calendar(self, start_date: str, end_date: str) -> pd.DataFrame:
        return self.calendar[(self.calendar["trade_date"] >= start_date) & (self.calendar["trade_date"] <= end_date)].copy()

    def get_index_constituents(self, index_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        return self.constituents[(self.constituents["effective_trade_date"] >= start_date) & (self.constituents["effective_trade_date"] <= end_date)].copy()

    def get_limit_prices(self, start_date: str, end_date: str) -> pd.DataFrame:
        return self.limits[(self.limits["trade_date"] >= start_date) & (self.limits["trade_date"] <= end_date)].copy()

    def get_tradability_flags(self, start_date: str, end_date: str) -> pd.DataFrame:
        return self.tradability[(self.tradability["trade_date"] >= start_date) & (self.tradability["trade_date"] <= end_date)].copy()

    def get_lifecycle(self) -> pd.DataFrame:
        return self.lifecycle.copy()

    def get_historical_st_status(self, start_date: str, end_date: str) -> pd.DataFrame:
        return self.st_status[(self.st_status["start_date"] <= end_date) & (self.st_status["end_date"] >= start_date)].copy()


def make_backtest_config(tmp_path: Path, *, top_n: int = 3) -> BacktestConfig:
    return BacktestConfig(
        start_date=DATES[0],
        end_date=DATES[-1],
        rebalance_frequency=5,
        top_n=top_n,
        initial_cash=10000.0,
        cost_bps=20.0,
        unknown_tradability_policy="reject_trade",
        runs_dir=str(tmp_path / "runs"),
        temp_dir=str(tmp_path / "runs" / "tmp"),
        min_free_space_gb=0.0,
        max_run_output_gb=1.0,
    )


def _bars() -> pd.DataFrame:
    close_by_code = {
        "000001.SZ": [10, 10.1, 10.2, 10.3, 10.4, 10.92, 10.9, 11.0, 11.1, 11.2, 11.872, 11.7],
        "300001.SZ": [10, 10.0, 10.0, 10.0, 10.0, 11.0, 11.0, 11.0, 11.0, 11.0, 11.55, 11.4],
        "600001.SH": [10, 10.0, 10.0, 10.0, 10.0, 10.4, 10.5, 10.5, 10.5, 10.5, 9.975, 9.0],
        "688001.SH": [10, 10.0, 10.0, 10.0, 10.0, 10.1, 10.1, 10.1, 10.1, 10.1, 11.11, 11.11],
    }
    rows = []
    for code, closes in close_by_code.items():
        for i, trade_date in enumerate(DATES):
            if code == "688001.SH" and trade_date == "20240116":
                continue
            close = closes[i]
            raw_open = close
            if code == "300001.SZ" and trade_date == "20240109":
                raw_open = 12.10
            if code == "600001.SH" and trade_date == "20240116":
                raw_open = 8.98
            rows.append(
                {
                    "trade_date": trade_date,
                    "ts_code": code,
                    "open": raw_open,
                    "high": max(raw_open, close),
                    "low": min(raw_open, close),
                    "close": close,
                    "raw_open": raw_open,
                    "raw_high": max(raw_open, close),
                    "raw_low": min(raw_open, close),
                    "raw_close": close,
                    "pre_close": closes[i - 1] if i else close,
                    "volume": 100000 + i,
                    "amount": (100000 + i) * close,
                    "adj_factor": 1.0,
                    "turnover_rate": 1.0,
                    "source": "fixture",
                }
            )
    return pd.DataFrame(rows)


def _constituents() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "snapshot_date": "20231229",
                "effective_trade_date": trade_date,
                "ts_code": code,
                "is_member": 1,
                "weight": 1.0,
                "membership_source": "fixture_csi800",
            }
            for trade_date in DATES
            for code in CODES
        ]
    )


def _limits() -> pd.DataFrame:
    rows = []
    bars = _bars()
    for row in bars.itertuples(index=False):
        limit_up = None
        limit_down = None
        if row.ts_code == "300001.SZ" and row.trade_date == "20240109":
            limit_up = 12.10
        if row.ts_code == "600001.SH" and row.trade_date == "20240116":
            limit_down = 8.98
        rows.append(
            {
                "trade_date": row.trade_date,
                "ts_code": row.ts_code,
                "pre_close": row.pre_close,
                "limit_up": limit_up,
                "limit_down": limit_down,
                "limit_ratio": 0.1,
                "limit_rule_version": "test-limit-v1",
                "rule_source": "fixture",
                "limit_derivation_status": "verified_rule",
                "source": "derived_limit_price",
                "source_record_id": f"{row.ts_code}-{row.trade_date}",
                "derivation_method": "fixture",
            }
        )
    return pd.DataFrame(rows)
