from __future__ import annotations

import json
import sys
import shutil
import time
from dataclasses import dataclass
from pathlib import Path

try:
    import resource
except ModuleNotFoundError:  # Windows does not provide the Unix resource module.
    resource = None

import numpy as np
import pandas as pd

from ashare_research.backtest.engine import BacktestConfig, DeterministicBacktestEngine
from ashare_research.config import load_simple_yaml
from ashare_research.data.local_sqlite_provider import LocalSQLiteProvider
from ashare_research.factors.expression import Expression
from ashare_research.mining.model import PositionLogitGenerator, UniformRandomGenerator
from ashare_research.mining.reward import reward_from_metrics
from ashare_research.registry.artifacts import stable_hash


@dataclass
class EvaluationRecord:
    formula_hash: str
    formula_text: str
    token_sequence: list[str]
    reward: float
    metrics: dict
    failure_reason: str | None
    elapsed_seconds: float


class CachedProvider:
    def __init__(self, source: LocalSQLiteProvider, start_date: str, end_date: str):
        self.bars = source.get_daily_bars(start_date, end_date)
        self.calendar = source.get_trade_calendar(start_date, end_date)
        self.constituents = source.get_index_constituents("CSI800", start_date, end_date)
        self.limits = source.get_limit_prices(start_date, end_date)
        self.tradability = source.get_tradability_flags(start_date, end_date)
        self.lifecycle = source.get_lifecycle()
        self.st_status = source.get_historical_st_status(start_date, end_date)

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
        if self.st_status.empty:
            return self.st_status.copy()
        return self.st_status[(self.st_status["start_date"] <= end_date) & (self.st_status["end_date"] >= start_date)].copy()


class FullBacktestBatchEvaluator:
    def __init__(self, provider, config: BacktestConfig, min_trade_count: int, keep_details: bool = False):
        self.provider = provider
        self.config = config
        self.min_trade_count = int(min_trade_count)
        self.keep_details = keep_details
        self.cache: dict[str, EvaluationRecord] = {}

    def evaluate(self, expression: Expression) -> EvaluationRecord:
        formula_hash = expression.sha256()
        if formula_hash in self.cache:
            return self.cache[formula_hash]
        start = time.perf_counter()
        try:
            result = DeterministicBacktestEngine(self.provider, self.config).run(expression)
            reward = reward_from_metrics(result["metrics"], min_trade_count=self.min_trade_count)
            failure = reward.failure_reason
            metrics = result["metrics"]
            if not self.keep_details and result.get("run_dir"):
                shutil.rmtree(result["run_dir"], ignore_errors=True)
        except Exception as exc:  # noqa: BLE001
            metrics = {"status": "failed", "failure_reason": str(exc)}
            reward = reward_from_metrics(metrics, min_trade_count=self.min_trade_count)
            failure = str(exc)
        record = EvaluationRecord(
            formula_hash=formula_hash,
            formula_text=expression.to_string(),
            token_sequence=list(expression.tokens),
            reward=float(reward.reward),
            metrics=metrics,
            failure_reason=failure,
            elapsed_seconds=time.perf_counter() - start,
        )
        self.cache[formula_hash] = record
        return record


def generate_unique(generator, target: int, max_attempts: int | None = None) -> tuple[list[Expression], int, int]:
    unique: dict[str, Expression] = {}
    generated = 0
    max_attempts = max_attempts or target * 20
    while len(unique) < target and generated < max_attempts:
        expr = generator.generate().expression
        generated += 1
        valid, _ = expr.validate()
        if valid:
            unique.setdefault(expr.sha256(), expr)
    return list(unique.values()), generated, generated - len(unique)


def summarize_records(records: list[EvaluationRecord], generated_count: int, duplicate_count: int, wall_clock_seconds: float, disk_output_mb: float) -> dict:
    rewards = np.array([r.reward for r in records], dtype=float)
    finite = rewards[np.isfinite(rewards)]
    sortinos = [r.metrics.get("sortino") for r in records if r.metrics.get("sortino") is not None]
    failure_reasons: dict[str, int] = {}
    lengths: dict[str, int] = {}
    feature_use: dict[str, int] = {}
    operator_use: dict[str, int] = {}
    for r in records:
        if r.failure_reason:
            failure_reasons[r.failure_reason] = failure_reasons.get(r.failure_reason, 0) + 1
        lengths[str(len(r.token_sequence))] = lengths.get(str(len(r.token_sequence)), 0) + 1
        for token in r.token_sequence:
            if token in {"RET1", "RET5", "VOL_RATIO20", "VOLUME_WEIGHTED_RET", "TREND60"}:
                feature_use[token] = feature_use.get(token, 0) + 1
            else:
                operator_use[token] = operator_use.get(token, 0) + 1
    top10 = sorted([r.reward for r in records], reverse=True)[: max(1, len(records) // 10)]
    return {
        "generated_count": generated_count,
        "syntax_valid_count": generated_count,
        "unique_formula_count": len(records),
        "duplicate_count": duplicate_count,
        "full_backtest_count": len(records),
        "cache_hit_count": duplicate_count,
        "valid_reward_count": int(sum(1 for r in records if r.failure_reason is None)),
        "invalid_reward_count": int(sum(1 for r in records if r.failure_reason is not None)),
        "positive_reward_count": int(sum(1 for r in records if r.reward > 0)),
        "best_train_sortino": None if not sortinos else float(max(sortinos)),
        "median_train_sortino": None if not sortinos else float(np.median(sortinos)),
        "reward_mean": None if len(finite) == 0 else float(finite.mean()),
        "reward_std": None if len(finite) == 0 else float(finite.std(ddof=0)),
        "top_10_mean_reward": float(np.mean(top10)) if top10 else None,
        "time_to_first_positive_reward": next((i + 1 for i, r in enumerate(records) if r.reward > 0), None),
        "evaluations_to_best_formula": int(np.argmax(rewards) + 1) if len(rewards) else None,
        "wall_clock_seconds": wall_clock_seconds,
        "peak_memory_mb": peak_memory_mb(),
        "disk_output_mb": disk_output_mb,
        "failure_reasons": failure_reasons,
        "formula_length_distribution": lengths,
        "feature_usage": feature_use,
        "operator_usage": operator_use,
        "no_trade_ratio": float(sum(1 for r in records if (r.metrics.get("trade_count") or 0) == 0) / len(records)) if records else 0.0,
        "sortino_unavailable_ratio": float(sum(1 for r in records if r.metrics.get("sortino") is None) / len(records)) if records else 0.0,
    }


def peak_memory_mb() -> float | None:
    if resource is None:
        return None
    usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if sys.platform == "darwin":
        return float(usage / 1024.0 / 1024.0)
    return float(usage / 1024.0)


def run_search_benchmark(config_path: str | Path, repo_root: Path) -> dict:
    cfg = load_simple_yaml(config_path)
    bench = cfg["benchmark_search"]
    run_id = "search_benchmark_" + time.strftime("%Y%m%d_%H%M%S")
    run_dir = repo_root / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    split = cfg["research_split"]["train"]
    data_cfg = cfg["data"]
    provider = CachedProvider(
        LocalSQLiteProvider(repo_root / data_cfg["sqlite_path"], repo_root / data_cfg.get("raw_sqlite_path", "stock-data/a_stock_selector.sqlite3")),
        split[0],
        cfg["research_split"].get("validation", split)[1],
    )
    base_bt = BacktestConfig(
        start_date=split[0],
        end_date=split[1],
        rebalance_frequency=int(cfg["backtest"]["rebalance_frequency"]),
        top_n=int(cfg["backtest"]["top_n"]),
        initial_cash=float(cfg["backtest"]["initial_cash"]),
        cost_bps=float(cfg["backtest"]["one_way_cost_bps"]),
        unknown_tradability_policy=str(cfg["backtest"]["unknown_tradability_policy"]),
        runs_dir=str(run_dir / "backtests"),
        temp_dir=str(run_dir / "tmp"),
        min_free_space_gb=float(cfg.get("storage", {}).get("min_free_space_gb", 0)),
        max_run_output_gb=float(cfg.get("storage", {}).get("max_run_output_gb", 1)),
    )
    target = int(bench["unique_formula_target"])
    results = []
    candidate_rows = []
    for generator_name in bench["generators"]:
        for seed in bench["random_seeds"]:
            generator = UniformRandomGenerator(seed=seed) if generator_name == "uniform_random" else PositionLogitGenerator(seed=seed)
            formulas, generated_count, duplicate_count = generate_unique(generator, target)
            evaluator = FullBacktestBatchEvaluator(provider, base_bt, min_trade_count=int(cfg["mining"]["min_trade_count"]))
            start = time.perf_counter()
            records = [evaluator.evaluate(expr) for expr in formulas]
            elapsed = time.perf_counter() - start
            rows = [record.__dict__ for record in records]
            candidate_rows.extend([{**row, "generator": generator_name, "seed": seed} for row in rows])
            summary = summarize_records(records, generated_count, duplicate_count, elapsed, disk_mb(run_dir))
            summary.update({"generator": generator_name, "seed": seed})
            results.append(summary)

    validation_results = []
    validation_split = cfg["research_split"].get("validation")
    if validation_split:
        val_bt = BacktestConfig(**{**base_bt.__dict__, "start_date": validation_split[0], "end_date": validation_split[1]})
        val_eval = FullBacktestBatchEvaluator(provider, val_bt, min_trade_count=int(cfg["mining"]["min_trade_count"]))
        for generator_name in bench["generators"]:
            subset = [r for r in candidate_rows if r["generator"] == generator_name]
            top = sorted(subset, key=lambda r: (-float(r["reward"]), r["formula_hash"]))[: int(bench.get("validation_top_n", 5))]
            for row in top:
                rec = val_eval.evaluate(Expression(tuple(row["token_sequence"])))
                validation_results.append({"generator": generator_name, "seed": row["seed"], "formula_hash": row["formula_hash"], "train_reward": row["reward"], "validation_reward": rec.reward, "validation_metrics": rec.metrics})

    conclusion = compare_generators(results, validation_results)
    output = {
        "run_id": run_id,
        "run_dir": str(run_dir),
        "config": cfg,
        "results": results,
        "validation_results": validation_results,
        "candidate_count": len(candidate_rows),
        "candidate_hash": stable_hash(candidate_rows),
        "conclusion": conclusion,
        "pytorch_route_decision": route_decision(conclusion),
    }
    (run_dir / "search_benchmark.json").write_text(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True, default=str), encoding="utf-8")
    pd.DataFrame(candidate_rows).to_parquet(run_dir / "candidate_metrics.parquet", index=False)
    return output


def compare_generators(results: list[dict], validation_results: list[dict]) -> str:
    by_gen: dict[str, list[float]] = {}
    for row in results:
        by_gen.setdefault(row["generator"], []).append(float(row.get("top_10_mean_reward") or -1e9))
    if set(by_gen) >= {"uniform_random", "position_logit"}:
        pos = np.array(by_gen["position_logit"])
        uni = np.array(by_gen["uniform_random"])
        if len(pos) == len(uni) and (pos > uni).sum() > len(pos) / 2:
            return "A"
        if len(pos) == len(uni) and (pos < uni).sum() > len(pos) / 2:
            return "C"
    return "B"


def route_decision(conclusion: str) -> str:
    if conclusion == "A":
        return "route_2_only_if_full_backtest_pressure_and_validation_stability_remain_positive"
    return "route_1_continue_simple_searchers"


def disk_mb(path: Path) -> float:
    total = sum(p.stat().st_size for p in path.rglob("*") if p.is_file())
    return float(total / 1024 / 1024)
