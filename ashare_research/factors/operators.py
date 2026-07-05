from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class OperatorSpec:
    name: str
    arity: int
    required_history: int
    description: str
    implementation: Callable


def _safe_div(x: pd.Series, y: pd.Series) -> pd.Series:
    denom = y.where(y.abs() > 1e-12)
    return x / denom


def _delta5(x: pd.Series) -> pd.Series:
    return x.groupby(level="ts_code", sort=False).diff(5)


def _decay_linear20(x: pd.Series) -> pd.Series:
    weights = np.arange(1, 21, dtype=float)
    weights = weights / weights.sum()
    return x.groupby(level="ts_code", sort=False).transform(
        lambda s: s.rolling(20, min_periods=20).apply(lambda a: float(np.dot(a, weights)), raw=True)
    )


def _zscore20(x: pd.Series) -> pd.Series:
    def calc(s: pd.Series) -> pd.Series:
        mean = s.rolling(20, min_periods=20).mean()
        std = s.rolling(20, min_periods=20).std(ddof=0)
        return (s - mean) / std.replace(0, np.nan)

    return x.groupby(level="ts_code", sort=False).transform(calc)


OPERATORS: dict[str, OperatorSpec] = {
    "ADD": OperatorSpec("ADD", 2, 0, "x + y", lambda x, y: x + y),
    "SUB": OperatorSpec("SUB", 2, 0, "x - y", lambda x, y: x - y),
    "MUL": OperatorSpec("MUL", 2, 0, "x * y", lambda x, y: x * y),
    "DIV": OperatorSpec("DIV", 2, 0, "safe x / y; zero denominator becomes NaN", _safe_div),
    "NEG": OperatorSpec("NEG", 1, 0, "-x", lambda x: -x),
    "ABS": OperatorSpec("ABS", 1, 0, "absolute value", lambda x: x.abs()),
    "SIGN": OperatorSpec("SIGN", 1, 0, "sign of x", lambda x: np.sign(x)),
    "DELTA5": OperatorSpec("DELTA5", 1, 5, "x - value 5 valid rows ago", _delta5),
    "DECAY_LINEAR20": OperatorSpec("DECAY_LINEAR20", 1, 20, "20-row linear decay with recent values weighted higher", _decay_linear20),
    "ZSCORE20": OperatorSpec("ZSCORE20", 1, 20, "20-row time-series z-score per stock", _zscore20),
}

