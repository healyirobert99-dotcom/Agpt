from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from ashare_research.backtest.engine import BacktestConfig, DeterministicBacktestEngine
from ashare_research.factors.expression import Expression
from ashare_research.mining.model import AlphaGPTLite, GeneratedFormula
from ashare_research.mining.trainer import ReinforceTrainer
from ashare_research.registry.artifacts import stable_hash


SYNTHETIC_CODES = ["000001.SZ", "000002.SZ", "300001.SZ", "600001.SH", "688001.SH"]


class SyntheticMomentumProvider:
    """Small deterministic market where recent 5-day winners tend to keep leading."""

    def __init__(self, days: int = 90):
        self.dates = pd.date_range("2024-01-02", periods=days, freq="B").strftime("%Y%m%d").tolist()
        self.bars = self._make_bars()
        self.calendar = pd.DataFrame({"trade_date": self.dates})
        self.constituents = pd.DataFrame(
            [
                {
                    "snapshot_date": self.dates[0],
                    "effective_trade_date": date,
                    "ts_code": code,
                    "is_member": 1,
                    "weight": 1.0,
                    "membership_source": "synthetic_csi800",
                }
                for date in self.dates
                for code in SYNTHETIC_CODES
            ]
        )
        self.limits = pd.DataFrame(
            [
                {
                    "trade_date": row.trade_date,
                    "ts_code": row.ts_code,
                    "pre_close": row.pre_close,
                    "limit_up": None,
                    "limit_down": None,
                    "limit_ratio": 0.1,
                    "limit_rule_version": "synthetic",
                    "rule_source": "synthetic",
                    "limit_derivation_status": "verified_rule",
                    "source": "synthetic",
                    "source_record_id": f"{row.ts_code}-{row.trade_date}",
                    "derivation_method": "synthetic",
                }
                for row in self.bars.itertuples(index=False)
            ]
        )
        self.tradability = pd.DataFrame(columns=["trade_date", "ts_code", "tradability_proxy"])
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
                    "source": "synthetic",
                    "source_record_id": code,
                    "derivation_method": "synthetic",
                    "rule_version": "synthetic",
                }
                for code in SYNTHETIC_CODES
            ]
        )
        self.st_status = pd.DataFrame(columns=["ts_code", "start_date", "end_date", "historical_is_st", "source"])

    def _make_bars(self) -> pd.DataFrame:
        prices = {code: 10.0 + i for i, code in enumerate(SYNTHETIC_CODES)}
        rows = []
        leader_cycle = [0, 1, 2, 3, 4, 0, 2, 4, 1]
        for i, date in enumerate(self.dates):
            leader = leader_cycle[i // 10 % len(leader_cycle)]
            for j, code in enumerate(SYNTHETIC_CODES):
                prev = prices[code]
                if j == leader:
                    ret = 0.018 if i % 17 else -0.006
                else:
                    ret = -0.004 + 0.001 * ((i + j) % 3)
                close = prev * (1.0 + ret)
                prices[code] = close
                volume = 100000 + 1000 * j + i
                rows.append(
                    {
                        "trade_date": date,
                        "ts_code": code,
                        "open": prev,
                        "high": max(prev, close),
                        "low": min(prev, close),
                        "close": close,
                        "raw_open": prev,
                        "raw_high": max(prev, close),
                        "raw_low": min(prev, close),
                        "raw_close": close,
                        "pre_close": prev,
                        "volume": volume,
                        "amount": volume * close,
                        "adj_factor": 1.0,
                        "turnover_rate": 1.0,
                        "source": "synthetic",
                    }
                )
        return pd.DataFrame(rows)

    def get_daily_bars(self, start_date: str, end_date: str, *args, **kwargs) -> pd.DataFrame:
        return self.bars[(self.bars["trade_date"] >= start_date) & (self.bars["trade_date"] <= end_date)].copy()

    def get_trade_calendar(self, start_date: str, end_date: str) -> pd.DataFrame:
        return self.calendar[(self.calendar["trade_date"] >= start_date) & (self.calendar["trade_date"] <= end_date)].copy()

    def get_index_constituents(self, index_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        return self.constituents[(self.constituents["effective_trade_date"] >= start_date) & (self.constituents["effective_trade_date"] <= end_date)].copy()

    def get_limit_prices(self, start_date: str, end_date: str) -> pd.DataFrame:
        return self.limits[(self.limits["trade_date"] >= start_date) & (self.limits["trade_date"] <= end_date)].copy()

    def get_tradability_flags(self, start_date: str, end_date: str) -> pd.DataFrame:
        return self.tradability.copy()

    def get_lifecycle(self) -> pd.DataFrame:
        return self.lifecycle.copy()

    def get_historical_st_status(self, start_date: str, end_date: str) -> pd.DataFrame:
        return self.st_status.copy()


def synthetic_backtest_config(run_dir: Path) -> BacktestConfig:
    return BacktestConfig(
        start_date="20240102",
        end_date="20240506",
        rebalance_frequency=5,
        top_n=1,
        initial_cash=100000.0,
        cost_bps=20.0,
        unknown_tradability_policy="reject_trade",
        runs_dir=str(run_dir / "backtests"),
        temp_dir=str(run_dir / "tmp"),
        min_free_space_gb=0.0,
        max_run_output_gb=1.0,
    )


def evaluate_on_synthetic(expression: Expression, run_dir: Path) -> dict:
    provider = SyntheticMomentumProvider()
    result = DeterministicBacktestEngine(provider, synthetic_backtest_config(run_dir)).run(expression)
    return result["metrics"]


def reward_distribution(rewards: list[float]) -> dict:
    arr = np.array(rewards, dtype=float)
    finite = arr[np.isfinite(arr)]
    if len(finite) == 0:
        return {"count": len(rewards), "finite_count": 0}
    return {
        "count": int(len(rewards)),
        "finite_count": int(len(finite)),
        "mean": float(finite.mean()),
        "std": float(finite.std(ddof=0)),
        "p10": float(np.quantile(finite, 0.1)),
        "p50": float(np.quantile(finite, 0.5)),
        "p90": float(np.quantile(finite, 0.9)),
        "positive_count": int((finite > 0).sum()),
        "negative_count": int((finite < 0).sum()),
    }


def run_stage3_5_validation(repo_root: Path) -> dict:
    run_id = "validation_" + time.strftime("%Y%m%d_%H%M%S")
    run_dir = repo_root / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    target = Expression(("RET1",))
    baseline = Expression(("RET5",))
    target_metrics = evaluate_on_synthetic(target, run_dir)
    baseline_metrics = evaluate_on_synthetic(baseline, run_dir)
    seeds = [0, 1, 2, 3, 4]
    seed_results = []
    for seed in seeds:
        model = AlphaGPTLite(seed=seed, learning_rate=0.2)
        trainer = ReinforceTrainer(model)
        before = model.formula_probability(target.tokens)
        target_generated = GeneratedFormula(target, [])
        distractor = GeneratedFormula(baseline, [])
        for _ in range(25):
            trainer.update_batch([(target_generated, 1.0), (distractor, -0.5)])
        after = model.formula_probability(target.tokens)
        seed_results.append({"seed": seed, "target_probability_before": before, "target_probability_after": after})

    pressure_rows = []
    for tier, count in [("tiny", 50), ("small", 150), ("medium", 600)]:
        model = AlphaGPTLite(seed=11)
        seen = set()
        generated = []
        start = time.perf_counter()
        for _ in range(count):
            expr = model.generate().expression
            generated.append(expr)
            seen.add(expr.sha256())
        elapsed = time.perf_counter() - start
        pressure_rows.append(
            {
                "tier": tier,
                "generated_count": count,
                "syntax_valid_count": sum(1 for e in generated if e.validate()[0]),
                "unique_count": len(seen),
                "duplicate_count": count - len(seen),
                "actual_backtest_count": 0,
                "cache_hit_count": count - len(seen),
                "avg_generation_seconds": elapsed / count,
            }
        )

    rewards = [float(target_metrics.get("sortino") or -1.0), float(baseline_metrics.get("sortino") or -1.0)]
    result = {
        "run_id": run_id,
        "run_dir": str(run_dir),
        "model_structure": "position_dependent_logits_with_action_mask_not_transformer",
        "target_formula": target.to_string(),
        "baseline_formula": baseline.to_string(),
        "target_metrics": target_metrics,
        "baseline_metrics": baseline_metrics,
        "multi_seed_probability": seed_results,
        "reward_distribution": reward_distribution(rewards),
        "pressure": pressure_rows,
        "dedup_cache_hash": stable_hash([row["unique_count"] for row in pressure_rows]),
        "conclusion": "C",
        "conclusion_text": "AlphaGPTLite currently proves probability updates on controlled rewards, but this validation does not prove autonomous discovery beyond random formula search.",
    }
    (run_dir / "stage3_5_validation_report.json").write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return result
