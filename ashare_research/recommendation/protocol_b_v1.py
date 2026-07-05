"""Trade Recommendation Protocol B-v1.0 — Deterministic pure logic.

This module implements the frozen B-v1.0 protocol rules:
  - Validates shortlist manifest (freeze_id, formula count, formula hashes)
  - Cross-sectional percentile ranking per formula
  - NaN/Inf filtering
  - Equal-weighted 5-formula composite percentile
  - Top-5 selection with deterministic tie-breaks
  - Weekly calendar mapping (last/first/following trade day)
  - Fixed 20% position weights
  - Trade win-rate computation (pure function)

NOT allowed in this module:
  - SQLite or market data access
  - ResearchContext creation
  - Phase-2 backtesting
  - Validation or blind_test access
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Sequence


# ---------------------------------------------------------------------------
# Constants — frozen per protocol
# ---------------------------------------------------------------------------

PROTOCOL_ID = "trade_recommendation_b_v1"

EXPECTED_SHORTLIST_FREEZE_ID = "d0d4d84f0670724c"
EXPECTED_FORMULA_COUNT = 5
EXPECTED_FORMULA_HASHES: tuple[str, ...] = (
    "ab77e24ae75d07207c219f5db88c8886f4f46016ced1b18757ce47a22453bb4d",
    "d5e1cb68d4ac7b78da893a37e3ad24b4de5ae74ee3d3bb0d61dae1468ced87c2",
    "84bed41d0741c6ce5ffab0feb8cf656e3d6cb70ccd8e940b78103caa21774709",
    "c890670e67dde87b34f7aae4e5878474276a89c54070ef7d280430765bdae45e",
    "0593939032ea015fe8a9f86b07477200844114235905b5c54071aa11e32abde4",
)

EXPECTED_FORMULA_TEXTS: tuple[str, ...] = (
    "DIV(ABS(ADD(ADD(VOLUME_WEIGHTED_RET,RET5),RET5)),RET5)",
    "ABS(MUL(DELTA5(DIV(ZSCORE20(RET5),VOL_RATIO20)),VOL_RATIO20))",
    "ZSCORE20(DELTA5(RET5))",
    "DIV(SUB(SIGN(ABS(VOLUME_WEIGHTED_RET)),ABS(RET5)),RET1)",
    "ADD(SIGN(SUB(VOLUME_WEIGHTED_RET,RET5)),DELTA5(SIGN(VOLUME_WEIGHTED_RET)))",
)

TOP_N = 5
TARGET_WEIGHT_PER_STOCK = 0.20


# ---------------------------------------------------------------------------
# Shortlist validation
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ShortlistValidation:
    """Result of validating a shortlist manifest against frozen protocol."""

    valid: bool
    freeze_id_match: bool
    formula_count_match: bool
    all_hashes_match: bool
    mismatched_hashes: list[str]
    extra_formulas: int
    missing_formulas: int

    @property
    def reason(self) -> str | None:
        if self.valid:
            return None
        parts: list[str] = []
        if not self.freeze_id_match:
            parts.append("freeze_id_mismatch")
        if not self.formula_count_match:
            parts.append(f"formula_count:{self.missing_formulas}_missing_{self.extra_formulas}_extra")
        if not self.all_hashes_match:
            parts.append("formula_hash_mismatch")
        return "/".join(parts) if parts else None


def validate_shortlist(
    freeze_id: str,
    formula_hashes: Sequence[str],
    *,
    expected_freeze_id: str = EXPECTED_SHORTLIST_FREEZE_ID,
    expected_count: int = EXPECTED_FORMULA_COUNT,
    expected_hashes: tuple[str, ...] | None = None,
) -> ShortlistValidation:
    """Validate a shortlist manifest against frozen protocol constants.

    Pure function. No file I/O.
    """
    if expected_hashes is None:
        expected_hashes = EXPECTED_FORMULA_HASHES

    freeze_match = freeze_id == expected_freeze_id
    provider_hashes = list(formula_hashes)
    count_match = len(provider_hashes) == expected_count

    mismatched: list[str] = []
    if expected_hashes:
        expected_set = set(expected_hashes)
        for h in provider_hashes:
            if h not in expected_set:
                mismatched.append(h)
        for h in expected_hashes:
            if h not in provider_hashes:
                mismatched.append(h)

    extra = max(0, len(provider_hashes) - expected_count)
    missing = max(0, expected_count - len(provider_hashes))

    valid = freeze_match and count_match and not mismatched

    return ShortlistValidation(
        valid=valid,
        freeze_id_match=freeze_match,
        formula_count_match=count_match,
        all_hashes_match=not mismatched,
        mismatched_hashes=mismatched,
        extra_formulas=extra,
        missing_formulas=missing,
    )


def validate_shortlist_from_manifest(manifest: dict) -> ShortlistValidation:
    """Validate a shortlist manifest dict against frozen protocol."""
    freeze_id = str(manifest.get("shortlist_id", ""))
    formulas = manifest.get("formulas", [])
    formula_hashes = [f.get("formula_hash", "") for f in formulas]
    return validate_shortlist(freeze_id, formula_hashes)


# ---------------------------------------------------------------------------
# Cross-sectional percentile ranking
# ---------------------------------------------------------------------------


def cross_sectional_percentile(values: list[float]) -> list[float | None]:
    """Compute cross-sectional percentile rank for each value.

    Higher values map to higher percentiles.
    NaN / Inf values return None (excluded).
    Ties receive equal percentile (fraction of values <= this value).
    """
    n = len(values)
    if n == 0:
        return []

    # Determine which values are finite
    valid_indices: list[int] = []
    valid_values: list[float] = []
    for i, v in enumerate(values):
        if v is not None and _isfinite(v):
            valid_indices.append(i)
            valid_values.append(v)

    if not valid_values:
        return [None] * n

    # Sort for ranking
    sorted_pairs = sorted(enumerate(valid_values), key=lambda x: x[1])
    result: list[float | None] = [None] * n

    for rank_in_valid, (orig_idx, _) in enumerate(sorted_pairs):
        # Percentile = fraction of valid values <= this value
        count_le = sum(1 for v in valid_values if v <= valid_values[rank_in_valid])
        result[valid_indices[orig_idx]] = count_le / len(valid_values)

    return result


def _isfinite(v: float) -> bool:
    import math
    return math.isfinite(v)


# ---------------------------------------------------------------------------
# Multi-formula aggregation
# ---------------------------------------------------------------------------


def composite_percentile(
    formula_scores: list[list[float | None]],
    *,
    require_all_finite: bool = True,
) -> list[float | None]:
    """Aggregate multiple formula cross-sectional percentiles.

    Each entry in formula_scores is the per-stock percentile list for one formula.
    Returns one composite score per stock (mean of available formula percentiles).
    If require_all_finite=True and any formula has None/NaN/Inf, the stock is excluded.
    """
    if not formula_scores:
        return []

    n_stocks = len(formula_scores[0])
    result: list[float | None] = []

    for stock_idx in range(n_stocks):
        vals: list[float] = []
        excluded = False
        for formula_percentiles in formula_scores:
            val = formula_percentiles[stock_idx]
            if val is None or not _isfinite(val):
                if require_all_finite:
                    excluded = True
                    break
                continue
            vals.append(float(val))

        if excluded or not vals:
            result.append(None)
        else:
            result.append(sum(vals) / len(vals))

    return result


# ---------------------------------------------------------------------------
# Top-k selection with tie-break
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SelectedStock:
    composite_percentile: float
    ts_code: str


def select_top_n(
    ts_codes: list[str],
    composite_scores: list[float | None],
    *,
    top_n: int = TOP_N,
) -> list[SelectedStock]:
    """Select top-N stocks by composite_percentile (desc), then ts_code (asc).

    Returns at most top_n entries. Does not pad if fewer candidates exist.
    """
    candidates: list[tuple[float, str]] = []
    for code, score in zip(ts_codes, composite_scores):
        if score is not None and _isfinite(score):
            candidates.append((float(score), str(code)))

    # Sort: composite_percentile desc, ts_code asc
    candidates.sort(key=lambda x: (-x[0], x[1]))

    return [SelectedStock(composite_percentile=s, ts_code=c) for s, c in candidates[:top_n]]


# ---------------------------------------------------------------------------
# Weekly schedule mapping
# ---------------------------------------------------------------------------

WEIGHT_PER_WINDOW = TARGET_WEIGHT_PER_STOCK  # 0.20


@dataclass(frozen=True)
class WeeklySchedule:
    """Trading schedule for one recommendation window."""

    signal_date: str       # last trading day of week
    entry_date: str        # first trading day of next week
    exit_date: str         # first trading day of following week


def map_weekly_schedule(
    trade_calendar: list[str],
) -> list[WeeklySchedule]:
    """Map a sorted list of trading dates (YYYYMMDD) to weekly windows.

    Each week's signal is the last trading day of that week.
    Entry is the first trading day of the following week.
    Exit is the first trading day of the week after that.

    Pure function; operates only on the calendar list.
    """
    if len(trade_calendar) < 2:
        return []

    schedules: list[WeeklySchedule] = []
    i = 0
    while i < len(trade_calendar):
        current_date = trade_calendar[i]
        # Find last trading day of this week
        week_last = _find_week_last(trade_calendar, i)
        if week_last is None or week_last >= len(trade_calendar) - 2:
            break

        signal_date = trade_calendar[week_last]
        entry_candidate = _find_next_week_first(trade_calendar, week_last)
        exit_candidate = _find_following_week_first(trade_calendar, week_last)

        if entry_candidate is None or exit_candidate is None:
            break

        schedules.append(WeeklySchedule(
            signal_date=signal_date,
            entry_date=trade_calendar[entry_candidate],
            exit_date=trade_calendar[exit_candidate],
        ))

        # Move to next week's first trading day
        i = entry_candidate

    return schedules


def _find_week_last(cal: list[str], start: int) -> int | None:
    """Find the index of the last trading day in the week starting at start."""
    from datetime import datetime

    if start >= len(cal):
        return None
    base_dt = datetime.strptime(cal[start], "%Y%m%d")
    # Same week: Mon=0..Sun=6; last weekday trading day is Friday (4) or last before weekend
    i = start
    while i + 1 < len(cal):
        next_dt = datetime.strptime(cal[i + 1], "%Y%m%d")
        # If next date is in a different ISO week, stop
        if next_dt.isocalendar()[1] != base_dt.isocalendar()[1] or next_dt.year != base_dt.year:
            break
        i += 1
    return i


def _find_next_week_first(cal: list[str], after_idx: int) -> int | None:
    """Find the first trading day of the week following after_idx."""
    from datetime import datetime

    if after_idx + 1 >= len(cal):
        return None
    after_dt = datetime.strptime(cal[after_idx], "%Y%m%d")
    i = after_idx + 1
    if i >= len(cal):
        return None
    next_dt = datetime.strptime(cal[i], "%Y%m%d")
    # The next trading day might be in the same ISO week if the last was not Friday
    # We need the first trading day of the NEXT ISO week
    # If after_idx was already the last of its week, then i is already the first of next week
    # If not, skip to the next ISO week
    while i < len(cal):
        dt = datetime.strptime(cal[i], "%Y%m%d")
        if dt.isocalendar()[1] != after_dt.isocalendar()[1] or dt.year != after_dt.year:
            return i
        i += 1
    return None


def _find_following_week_first(cal: list[str], after_idx: int) -> int | None:
    """Find the first trading day of the week following the week after after_idx."""
    next_week = _find_next_week_first(cal, after_idx)
    if next_week is None:
        return None
    return _find_next_week_first(cal, next_week)


# ---------------------------------------------------------------------------
# Position weight generation
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PositionAllocation:
    ts_code: str
    target_weight: float
    entry_date: str
    exit_date: str
    signal_date: str


def generate_positions(
    selected: list[SelectedStock],
    schedule: WeeklySchedule,
    *,
    target_weight: float = TARGET_WEIGHT_PER_STOCK,
) -> list[PositionAllocation]:
    """Generate fixed-weight position allocations from selected stocks.

    Each stock gets target_weight. If fewer than TOP_N stocks are selected,
    the remaining weight stays as cash (no redistribution).
    """
    return [
        PositionAllocation(
            ts_code=s.ts_code,
            target_weight=target_weight,
            entry_date=schedule.entry_date,
            exit_date=schedule.exit_date,
            signal_date=schedule.signal_date,
        )
        for s in selected
    ]


# ---------------------------------------------------------------------------
# Trade statistics (pure functions)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TradeRecord:
    """One completed stock-level trade (entry + exit)."""

    ts_code: str
    entry_date: str
    exit_date: str
    net_return: float | None    # after cost; None if incomplete


@dataclass(frozen=True)
class TradeStatistics:
    """Trade win-rate and related statistics."""

    trade_win_rate: float | None
    completed_trade_count: int
    planned_recommendation_count: int
    executed_entry_count: int
    unfilled_entry_count: int
    mean_net_trade_return: float | None
    mean_winning_trade_return: float | None
    mean_losing_trade_return: float | None


def compute_trade_statistics(trades: list[TradeRecord]) -> TradeStatistics:
    """Compute trade win-rate and related statistics.

    Win definition: net_return > 0 after all costs.
    Only completed trades (net_return is not None) enter the denominator.
    """
    total_planned = len(trades)
    completed = [t for t in trades if t.net_return is not None]
    wins = [t for t in completed if t.net_return is not None and t.net_return > 0]
    losses = [t for t in completed if t.net_return is not None and t.net_return <= 0]

    completed_count = len(completed)
    win_rate = len(wins) / completed_count if completed_count > 0 else None

    winning_returns = [t.net_return for t in wins if t.net_return is not None]
    losing_returns = [t.net_return for t in losses if t.net_return is not None]
    all_returns = [t.net_return for t in completed if t.net_return is not None]

    unfilled = total_planned - len([t for t in trades if t.entry_date])

    return TradeStatistics(
        trade_win_rate=win_rate,
        completed_trade_count=completed_count,
        planned_recommendation_count=total_planned,
        executed_entry_count=len(completed),
        unfilled_entry_count=unfilled,
        mean_net_trade_return=_safe_mean(all_returns),
        mean_winning_trade_return=_safe_mean(winning_returns),
        mean_losing_trade_return=_safe_mean(losing_returns),
    )


def _safe_mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


# ---------------------------------------------------------------------------
# Report field definitions
# ---------------------------------------------------------------------------

REQUIRED_REPORT_FIELDS = (
    "trade_win_rate",
    "completed_trade_count",
    "mean_net_trade_return",
    "mean_winning_trade_return",
    "mean_losing_trade_return",
    "portfolio_max_drawdown",
    "planned_recommendation_count",
    "executed_entry_count",
    "unfilled_entry_count",
    "delayed_exit_count",
)


def empty_report_fields() -> dict:
    """Return a dict with all report fields set to None/0."""
    return {
        "trade_win_rate": None,
        "completed_trade_count": 0,
        "mean_net_trade_return": None,
        "mean_winning_trade_return": None,
        "mean_losing_trade_return": None,
        "portfolio_max_drawdown": None,
        "planned_recommendation_count": 0,
        "executed_entry_count": 0,
        "unfilled_entry_count": 0,
        "delayed_exit_count": 0,
    }
