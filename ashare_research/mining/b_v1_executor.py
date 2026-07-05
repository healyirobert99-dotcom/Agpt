"""B-v1.0 Composite portfolio executor using Phase 2 DeterministicBacktestEngine.

Replaces the previous _try_execute independent implementation with
direct integration into the validated Phase 2 execution pipeline.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from ashare_research.backtest.batch import BatchBacktestResult
from ashare_research.backtest.context import ResearchContext
from ashare_research.backtest.engine import (
    BacktestConfig,
    DeterministicBacktestEngine,
)
from ashare_research.backtest.records import ExternalTarget
from ashare_research.factors.executor import FormulaExecutor
from ashare_research.factors.expression import parse_formula_text
from ashare_research.recommendation.protocol_b_v1 import (
    EXPECTED_FORMULA_TEXTS,
    TOP_N,
    TARGET_WEIGHT_PER_STOCK,
    cross_sectional_percentile,
    composite_percentile,
    WeeklySchedule,
)


def build_weekly_schedule(trade_calendar: list[str]) -> list[WeeklySchedule]:
    """Build weekly schedule using only (year, week) comparison.

    Ensures exactly one signal per ISO week — the last trading day.
    Entry = first trading day of next week.
    Exit = first trading day of the week after that.
    """
    if len(trade_calendar) < 3:
        return []
    from datetime import datetime as dt

    schedules: list[WeeklySchedule] = []
    i = 0
    while i < len(trade_calendar):
        base_dt = dt.strptime(trade_calendar[i], "%Y%m%d")
        base_key = (base_dt.year, base_dt.isocalendar()[1])
        # Find last trading day of this ISO week
        j = i
        while j + 1 < len(trade_calendar):
            nxt = dt.strptime(trade_calendar[j + 1], "%Y%m%d")
            nxt_key = (nxt.year, nxt.isocalendar()[1])
            if nxt_key != base_key:
                break
            j += 1
        signal_date = trade_calendar[j]
        # Need at least entry (next day) and exit (following week's first day)
        if j + 1 >= len(trade_calendar) - 1:
            break
        entry_date = trade_calendar[j + 1]
        # Find first trading day of the week after entry's week
        entry_dt = dt.strptime(entry_date, "%Y%m%d")
        entry_key = (entry_dt.year, entry_dt.isocalendar()[1])
        k = j + 1
        while k < len(trade_calendar):
            ck = dt.strptime(trade_calendar[k], "%Y%m%d")
            ck_key = (ck.year, ck.isocalendar()[1])
            if ck_key != entry_key:
                break
            k += 1
        if k >= len(trade_calendar):
            break
        exit_date = trade_calendar[k]
        schedules.append(WeeklySchedule(signal_date, entry_date, exit_date))
        i = j + 1  # start at next week's first day
    return schedules


def compute_composite_factor(
    context: ResearchContext,
    signal_date: str,
    formula_texts: tuple[str, ...] = EXPECTED_FORMULA_TEXTS,
    stock_codes: list[str] | None = None,
) -> pd.Series:
    """Compute the 5-formula equal-weighted composite percentile for one signal date.

    Returns a Series with ts_code index and composite_percentile values.
    Only stocks where all 5 formulas produce finite values are included.
    """
    if stock_codes is None:
        bars_date = context.bars[context.bars["trade_date"] == signal_date]
        stock_codes = sorted(bars_date["ts_code"].unique())

    # Compute per-formula factor values
    formula_scores: list[list[float | None]] = []
    for text in formula_texts:
        expr = parse_formula_text(text)
        exec_result = FormulaExecutor(min_valid_rows=10).execute(expr, context.features)
        if not exec_result.valid or exec_result.values is None:
            formula_scores.append([None] * len(stock_codes))
            continue
        factor_series = exec_result.values
        # Match to stock_codes for this date
        factor_df = factor_series.reset_index()
        factor_df.columns = ["ts_code", "trade_date", "factor_value"]
        factor_date = factor_df[factor_df["trade_date"] == signal_date]
        code_map = dict(zip(factor_date["ts_code"].values, factor_date["factor_value"].values))
        scores = [float(code_map.get(c)) if c in code_map else None for c in stock_codes]
        formula_scores.append(cross_sectional_percentile(scores))

    # Composite (require all 5 finite)
    composite = composite_percentile(formula_scores, require_all_finite=True)

    # Build result Series
    result = pd.Series(index=pd.Index(stock_codes, name="ts_code"), data=composite, name="composite_percentile")
    return result


def build_composite_factor_dataframe(
    context: ResearchContext,
    signal_dates: list[str],
    formula_texts: tuple[str, ...] = EXPECTED_FORMULA_TEXTS,
) -> pd.DataFrame:
    """Build a multi-date composite factor DataFrame.

    Returns DataFrame with columns [trade_date, ts_code, factor_value]
    where factor_value = composite_percentile (0..1 range).
    """
    rows: list[dict] = []
    for sd in signal_dates:
        bars_date = context.bars[context.bars["trade_date"] == sd]
        codes = sorted(bars_date["ts_code"].unique())
        composite = compute_composite_factor(context, sd, formula_texts, codes)
        for code in codes:
            val = composite.get(code)
            if val is not None:
                rows.append({"trade_date": sd, "ts_code": code, "factor_value": float(val)})

    return pd.DataFrame(rows)


class CompositeBacktestExecutor:
    """Run B-v1.0 weekly composite portfolio through Phase 2 engine.

    Uses precomputed composite factor values with a standard
    deterministic backtest execution path (Plan/Execute/Account).
    """

    def __init__(self, context: ResearchContext, config: BacktestConfig):
        self.context = context
        self.config = config
        self._engine = DeterministicBacktestEngine(provider=None, config=config)

    def run_composite(
        self,
        composite_factor: pd.DataFrame,
        signal_dates: list[str],
        schedule: list[WeeklySchedule],
        run_dir: Path | None = None,
    ) -> BatchBacktestResult:
        """Run a full Phase 2 backtest using the composite factor values.

        The composite_factor must have columns [trade_date, ts_code, factor_value].
        Signal dates determine rebalance points.
        Schedule provides entry/exit dates for trade-stats tracking.
        """
        targets = self.build_external_targets(composite_factor, schedule)
        market_data = {
            "bars": self.context.bars,
            "calendar": self.context.calendar,
            "constituents": self.context.constituents,
            "limits": self.context.limits,
            "tradability": self.context.tradability,
            "lifecycle": self.context.lifecycle,
            "st_status": self.context.st_status,
        }
        result = self._engine.run_external_target_schedule(
            targets,
            market_data=market_data,
            run_id="composite_b_v1",
            run_dir=run_dir,
            write_outputs=run_dir is not None,
        )

        return BatchBacktestResult(
            formula_hash="composite_b_v1",
            formula_text="B-v1.0 composite (5 formulas)",
            metrics=result["metrics"],
            failure_reason=None,
            planned=result["planned"],
            trades=result["trades"],
            holdings=result["holdings"],
            accounts=result["accounts"],
            profile={},
            detail_dir=None,
        )

    def build_external_targets(
        self,
        composite_factor: pd.DataFrame,
        schedule: list[WeeklySchedule],
    ) -> list[ExternalTarget]:
        """Build B-v1.0 target windows for the Phase 2 public plan API."""
        targets: list[ExternalTarget] = []
        for item in schedule:
            factor_date = composite_factor[composite_factor["trade_date"] == item.signal_date]
            if factor_date.empty:
                continue
            selected = factor_date.sort_values(
                ["factor_value", "ts_code"],
                ascending=[False, True],
                kind="mergesort",
            ).head(TOP_N)
            for rank, row in enumerate(selected.itertuples(index=False), 1):
                code = str(row.ts_code)
                window_id = f"{item.signal_date}:{item.entry_date}:{item.exit_date}:{rank}:{code}"
                targets.append(
                    ExternalTarget(
                        window_id=window_id,
                        signal_date=item.signal_date,
                        entry_date=item.entry_date,
                        planned_exit_date=item.exit_date,
                        ts_code=code,
                        target_weight=TARGET_WEIGHT_PER_STOCK,
                        factor_value=float(row.factor_value),
                        rank=rank,
                    )
                )
        return targets


def deprecated_try_execute_marker() -> None:
    """Deprecated — this execution path is no longer used."""
    pass
