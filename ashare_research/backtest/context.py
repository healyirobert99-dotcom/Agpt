from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from ashare_research.backtest.engine import BacktestConfig
from ashare_research.data.local_sqlite_provider import LocalSQLiteProvider
from ashare_research.factors.base_features import compute_base_features, robust_cross_sectional_standardize
from ashare_research.registry.artifacts import stable_hash


@dataclass(frozen=True)
class ResearchContext:
    config: BacktestConfig
    bars: pd.DataFrame
    calendar: pd.DataFrame
    constituents: pd.DataFrame
    limits: pd.DataFrame
    tradability: pd.DataFrame
    lifecycle: pd.DataFrame
    st_status: pd.DataFrame
    features: pd.DataFrame
    standardized_features: pd.DataFrame
    dates: tuple[str, ...]
    rebalance_dates: frozenset[str]
    context_hash: str
    profile: dict[str, float] = field(default_factory=dict)

    @classmethod
    def build(cls, provider: LocalSQLiteProvider, config: BacktestConfig, *, data_snapshot_hash: str = "unknown", progress_path: str | Path | None = None) -> "ResearchContext":
        profile: dict[str, float] = {}
        progress = Path(progress_path) if progress_path else None

        def write_progress(stage: str, **payload) -> None:
            if progress is None:
                return
            progress.parent.mkdir(parents=True, exist_ok=True)
            progress.write_text(json.dumps({"stage": stage, **payload}, ensure_ascii=False, indent=2, sort_keys=True, default=str), encoding="utf-8")

        stage_names = {
            "sqlite_daily_bars_seconds": "daily_bars_query",
            "sqlite_trade_calendar_seconds": "calendar_query",
            "sqlite_constituents_seconds": "constituents_query",
            "sqlite_limit_prices_seconds": "limit_prices",
            "sqlite_tradability_seconds": "tradability_query",
            "sqlite_lifecycle_seconds": "lifecycle_query",
            "sqlite_st_status_seconds": "historical_st_query",
            "base_features_seconds": "base_features",
            "standardized_features_seconds": "normalization",
        }

        def timed(name: str, fn):
            stage = stage_names.get(name, name.replace("_seconds", ""))
            write_progress(stage + "_started")
            start = time.perf_counter()
            value = fn()
            elapsed = time.perf_counter() - start
            profile[name] = elapsed
            rows = len(value) if hasattr(value, "__len__") else None
            write_progress(stage + "_completed", rows=rows, elapsed_seconds=elapsed)
            return value

        bars = timed("sqlite_daily_bars_seconds", lambda: provider.get_daily_bars(config.start_date, config.end_date))
        if bars.empty:
            raise ValueError("no_daily_bars")
        calendar = timed("sqlite_trade_calendar_seconds", lambda: provider.get_trade_calendar(config.start_date, config.end_date))
        constituents = timed("sqlite_constituents_seconds", lambda: provider.get_index_constituents("CSI800", config.start_date, config.end_date))
        limits = timed("sqlite_limit_prices_seconds", lambda: provider.get_limit_prices(config.start_date, config.end_date))
        tradability = timed("sqlite_tradability_seconds", lambda: provider.get_tradability_flags(config.start_date, config.end_date))
        lifecycle = timed("sqlite_lifecycle_seconds", provider.get_lifecycle)
        st_status = timed("sqlite_st_status_seconds", lambda: provider.get_historical_st_status(config.start_date, config.end_date))
        write_progress("features_started")
        features = timed("base_features_seconds", lambda: compute_base_features(bars))
        write_progress("features_completed", rows=len(features), elapsed_seconds=profile["base_features_seconds"])
        write_progress("normalization_started")
        standardized = timed("standardized_features_seconds", lambda: robust_cross_sectional_standardize(features, min_count=2))
        write_progress("normalization_completed", rows=len(standardized), elapsed_seconds=profile["standardized_features_seconds"])
        dates = tuple(calendar["trade_date"].astype(str))
        write_progress("context_hash_started")
        payload = {
            "config": config.__dict__,
            "data_snapshot_hash": data_snapshot_hash,
            "row_counts": {
                "bars": len(bars),
                "calendar": len(calendar),
                "constituents": len(constituents),
                "limits": len(limits),
                "tradability": len(tradability),
                "lifecycle": len(lifecycle),
                "st_status": len(st_status),
            },
        }
        context_hash = stable_hash(payload)
        write_progress("context_hash_completed", context_hash=context_hash)
        return cls(
            config=config,
            bars=bars,
            calendar=calendar,
            constituents=constituents,
            limits=limits,
            tradability=tradability,
            lifecycle=lifecycle,
            st_status=st_status,
            features=features,
            standardized_features=standardized,
            dates=dates,
            rebalance_dates=frozenset(dates[:: config.rebalance_frequency]),
            context_hash=context_hash,
            profile=profile,
        )

    def metadata_json(self) -> str:
        return json.dumps({"context_hash": self.context_hash, "config": self.config.__dict__, "profile": self.profile}, sort_keys=True)
