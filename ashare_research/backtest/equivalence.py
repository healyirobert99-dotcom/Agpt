from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from pandas.errors import EmptyDataError


FLOAT_TOLERANCE = 1e-9
MONEY_TOLERANCE = 1e-8


SORT_COLUMNS = {
    "planned_orders": ["signal_date", "planned_trade_date", "ts_code", "side", "formula_hash"],
    "executions": ["actual_trade_date", "ts_code", "side", "requested_quantity", "executed_quantity"],
    "daily_holdings": ["trade_date", "ts_code"],
    "daily_account": ["trade_date"],
}


CORE_FILES = {
    "planned_orders": "planned_orders.csv",
    "executions": "executions.csv",
    "daily_holdings": "daily_holdings.csv",
    "daily_account": "daily_account.csv",
}


METRIC_KEYS = [
    "total_return",
    "annualized_return",
    "annualized_volatility",
    "sharpe",
    "sortino",
    "max_drawdown",
    "calmar",
    "turnover",
    "trade_count",
    "win_rate",
    "gross_return",
    "net_return",
    "cumulative_cost",
    "unfilled_buy_count",
    "unfilled_sell_count",
    "cash_ratio",
]


@dataclass(frozen=True)
class SectionComparison:
    equal: bool
    difference_count: int
    first_difference: str | None


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except EmptyDataError:
        return pd.DataFrame()


def _stable_sort(df: pd.DataFrame, section: str) -> pd.DataFrame:
    if df.empty:
        return df.reset_index(drop=True)
    present = [col for col in SORT_COLUMNS.get(section, []) if col in df.columns]
    if present:
        return df.sort_values(present, kind="mergesort").reset_index(drop=True)
    return df.sort_index(axis=1).reset_index(drop=True)


def _values_equal(left: Any, right: Any, column: str) -> bool:
    if pd.isna(left) and pd.isna(right):
        return True
    if pd.isna(left) or pd.isna(right):
        return False
    if isinstance(left, (int, float, np.integer, np.floating)) or isinstance(right, (int, float, np.integer, np.floating)):
        tol = MONEY_TOLERANCE if any(token in column for token in ("cash", "price", "cost", "notional", "market_value", "equity")) else FLOAT_TOLERANCE
        return abs(float(left) - float(right)) <= tol
    return str(left) == str(right)


def compare_dataframes(left: pd.DataFrame, right: pd.DataFrame, section: str) -> SectionComparison:
    left = _stable_sort(left, section)
    right = _stable_sort(right, section)
    if list(left.columns) != list(right.columns):
        return SectionComparison(False, 1, f"{section}:columns:{list(left.columns)} != {list(right.columns)}")
    if len(left) != len(right):
        return SectionComparison(False, abs(len(left) - len(right)) or 1, f"{section}:row_count:{len(left)} != {len(right)}")
    differences = 0
    first: str | None = None
    for row_idx in range(len(left)):
        for col in left.columns:
            if not _values_equal(left.iloc[row_idx][col], right.iloc[row_idx][col], str(col)):
                differences += 1
                if first is None:
                    first = f"{section}:row={row_idx}:column={col}:left={left.iloc[row_idx][col]!r}:right={right.iloc[row_idx][col]!r}"
    return SectionComparison(differences == 0, differences, first)


def _read_metrics(path: Path) -> dict:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("metrics", data)


def compare_metrics(left: dict, right: dict) -> SectionComparison:
    differences = 0
    first: str | None = None
    for key in METRIC_KEYS:
        if key not in left and key not in right:
            continue
        if not _values_equal(left.get(key), right.get(key), key):
            differences += 1
            if first is None:
                first = f"metrics:key={key}:left={left.get(key)!r}:right={right.get(key)!r}"
    return SectionComparison(differences == 0, differences, first)


def compare_backtest_dirs(legacy_dir: str | Path, batch_dir: str | Path) -> dict:
    legacy = Path(legacy_dir)
    batch = Path(batch_dir)
    sections: dict[str, dict] = {}
    total_differences = 0
    first_difference: str | None = None
    for section, filename in CORE_FILES.items():
        result = compare_dataframes(_read_csv(legacy / filename), _read_csv(batch / filename), section)
        sections[section] = result.__dict__
        total_differences += result.difference_count
        first_difference = first_difference or result.first_difference
    metrics_result = compare_metrics(_read_metrics(legacy / "metrics.json"), _read_metrics(batch / "metrics.json"))
    sections["metrics"] = metrics_result.__dict__
    total_differences += metrics_result.difference_count
    first_difference = first_difference or metrics_result.first_difference
    return {
        "planned_orders_equal": sections["planned_orders"]["equal"],
        "executions_equal": sections["executions"]["equal"],
        "daily_holdings_equal": sections["daily_holdings"]["equal"],
        "daily_account_equal": sections["daily_account"]["equal"],
        "metrics_equal": sections["metrics"]["equal"],
        "difference_count": total_differences,
        "first_difference": first_difference,
        "sections": sections,
        "equivalent": total_differences == 0,
    }
