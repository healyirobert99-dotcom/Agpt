from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

try:
    import resource
except ModuleNotFoundError:  # Windows does not provide the Unix resource module.
    resource = None

import numpy as np

from ashare_research.backtest.batch import BatchBacktestEvaluator
from ashare_research.backtest.context import ResearchContext
from ashare_research.backtest.golden import current_git_commit
from ashare_research.backtest.progress import FormulaProgressStore, atomic_write_json
from ashare_research.config import load_simple_yaml
from ashare_research.data.local_sqlite_provider import LocalSQLiteProvider
from ashare_research.factors.expression import Expression, parse_formula_text
from ashare_research.mining.model import GeneratedFormula, PositionLogitGenerator, UniformRandomGenerator
from ashare_research.mining.reward import reward_from_metrics
from ashare_research.registry.artifacts import stable_hash


WARNING_LINES = (
    "ENGINEERING SEARCHER TRAINING BENCHMARK ONLY (STAGE 3.6D-1)",
    "NOT A VALIDATED INVESTMENT STRATEGY",
    "B-READY DATA WITH APPROXIMATE TRADABILITY",
    "NO VALIDATION OR BLIND TEST ACCESS",
    "TRAINING-SET SEARCH COMPARISON ONLY",
)


def peak_memory_mb() -> float | None:
    if resource is None:
        return None
    usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if sys.platform == "darwin":
        return float(usage / 1024.0 / 1024.0)
    return float(usage / 1024.0)


def disk_mb(path: Path) -> float:
    total = sum(p.stat().st_size for p in path.rglob("*") if p.is_file())
    return float(total / 1024 / 1024)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


def _load_config(config_path: str | Path):
    """Load YAML and return raw dict."""
    import yaml as _yaml
    path = Path(config_path)
    text = path.read_text(encoding="utf-8")
    return _yaml.safe_load(text)


@dataclass(frozen=True)
class SearcherBenchmarkConfig:
    completed_full_backtest_target: int
    max_unique_formula_attempts: int
    max_generation_attempts: int
    save_detail_policy: str
    random_seeds: tuple[int, ...]
    generators: tuple[str, ...]
    position_logit_batch_size: int

    @property
    def groups(self) -> list[dict]:
        groups = []
        for gen in self.generators:
            for seed in self.random_seeds:
                groups.append({"generator": gen, "seed": int(seed)})
        return groups

    @property
    def n_groups(self) -> int:
        return len(self.groups)


def parse_benchmark_config(cfg: dict) -> SearcherBenchmarkConfig:
    bench = cfg["searcher_benchmark"]
    return SearcherBenchmarkConfig(
        completed_full_backtest_target=int(bench["completed_full_backtest_target"]),
        max_unique_formula_attempts=int(bench["max_unique_formula_attempts"]),
        max_generation_attempts=int(bench["max_generation_attempts"]),
        save_detail_policy=str(bench["save_detail_policy"]),
        random_seeds=tuple(int(s) for s in bench["random_seeds"]),
        generators=tuple(str(g) for g in bench["generators"]),
        position_logit_batch_size=int(bench.get("position_logit_batch_size", 5)),
    )


# ---------------------------------------------------------------------------
# Budget counting helpers (mirrors stage3_6c2.budget_counts)
# ---------------------------------------------------------------------------


def _budget_counts(records: dict) -> dict:
    status_counts: dict[str, int] = {}
    for record in records.values():
        status_counts[record.status] = status_counts.get(record.status, 0) + 1
    failed = [record for record in records.values() if record.status == "failed"]
    return {
        "completed_full_backtest_count": status_counts.get("completed", 0),
        "unique_formula_attempt_count": len(records),
        "failed_count": status_counts.get("failed", 0),
        "pending_count": status_counts.get("pending", 0),
        "running_count": status_counts.get("running", 0),
        "interrupted_count": status_counts.get("interrupted", 0),
        "formula_execution_invalid_count": sum(
            1 for record in failed if (record.failure_reason or "").startswith("invalid_formula:")
        ),
        "backtest_failed_count": sum(
            1 for record in failed if not (record.failure_reason or "").startswith("invalid_formula:")
        ),
    }


def _should_stop(counts: dict, generation_attempt_count: int, config: SearcherBenchmarkConfig) -> tuple[bool, str | None]:
    if counts["completed_full_backtest_count"] >= config.completed_full_backtest_target:
        return True, "completed_full_backtest_target_reached"
    if counts["unique_formula_attempt_count"] >= config.max_unique_formula_attempts:
        return True, "max_unique_formula_attempts_reached"
    if generation_attempt_count >= config.max_generation_attempts:
        return True, "max_generation_attempts_reached"
    return False, None


# ---------------------------------------------------------------------------
# PositionLogit batch update searcher wrapper
# ---------------------------------------------------------------------------


class PositionLogitSearcher:
    """Wraps PositionLogitGenerator with batched REINFORCE update."""

    def __init__(self, generator: PositionLogitGenerator, batch_size: int):
        self.generator = generator
        self.batch_size = batch_size
        self._pending: list[tuple[GeneratedFormula, float]] = []
        self.update_count = 0
        self.skipped_count = 0
        self.skip_reasons: dict[str, int] = {}
        self.parameter_hashes: list[str] = []

    def record_hash(self) -> None:
        self.parameter_hashes.append(self.generator.state_hash())

    def accept(self, generated: GeneratedFormula, reward: float) -> str | None:
        self._pending.append((generated, reward))
        if len(self._pending) >= self.batch_size:
            return self._flush()
        return None

    def flush(self) -> str | None:
        if not self._pending:
            return None
        return self._flush()

    def _flush(self) -> str | None:
        items = self._pending[:]
        self._pending = []
        rewards = [float(r) for _, r in items]
        if len(set(round(r, 12) for r in rewards)) <= 1:
            self.skipped_count += 1
            reason = "constant_or_invalid_rewards"
            self.skip_reasons[reason] = self.skip_reasons.get(reason, 0) + 1
            return reason
        baseline = sum(rewards) / len(rewards)
        for gen, rew in items:
            self.generator.update(gen, rew - baseline)
        self.update_count += len(items)
        return None


# ---------------------------------------------------------------------------
# Generator factory
# ---------------------------------------------------------------------------


def _create_generator(gen_type: str, seed: int) -> PositionLogitGenerator:
    if gen_type == "uniform_random":
        return UniformRandomGenerator(seed=seed)
    if gen_type == "position_logit":
        return PositionLogitGenerator(seed=seed)
    raise ValueError(f"unknown_generator:{gen_type}")


# ---------------------------------------------------------------------------
# Run one group (with optional interrupt)
# ---------------------------------------------------------------------------


def run_one_group(
    gen_type: str,
    seed: int,
    evaluator: BatchBacktestEvaluator,
    store: FormulaProgressStore,
    config: SearcherBenchmarkConfig,
    group_dir: Path,
    *,
    interrupt_after_completed: int | None = None,
    stop_after_interrupt: bool = False,
) -> dict:
    """Run generation-evaluation loop for one group until budget stop.

    Returns a dict with group-level results including:
    - generation_attempt_count, duplicate_count, syntax_invalid_count
    - formula_evaluation_seconds
    - generated_sequence, completed_sequence, failed_sequence
    - update/update_skipped stats (for position_logit)
    - budget counts (completed_full_backtest_count, etc.)
    - generator_state_hash
    """
    generator = _create_generator(gen_type, seed)
    pl_s = PositionLogitSearcher(generator, config.position_logit_batch_size) if gen_type == "position_logit" else None

    stats = {
        "generation_attempt_count": 0,
        "syntax_invalid_count": 0,
        "duplicate_count": 0,
        "formula_evaluation_seconds": 0.0,
        "cache_hit_count": 0,
        "actual_full_backtest_execution_count": 0,
        "generated_sequence": [],
        "completed_sequence": [],
        "failed_sequence": [],
        "interrupted_hash": None,
        "update_count": 0,
        "update_skipped_count": 0,
        "update_skipped_reason_distribution": {},
        "parameter_hashes_before": [],
        "parameter_hashes_after": [],
    }

    while True:
        atomic_write_json(group_dir / "generator_state.json", generator.state_dict())
        records = store.load()
        counts = _budget_counts(records)
        stop, reason = _should_stop(counts, stats["generation_attempt_count"], config)
        if stop:
            if pl_s:
                pl_s.flush()
                stats["update_count"] = pl_s.update_count
                stats["update_skipped_count"] = pl_s.skipped_count
                stats["update_skipped_reason_distribution"] = dict(pl_s.skip_reasons)
                stats["parameter_hashes_after"] = list(pl_s.parameter_hashes)
            return {"stop_reason": reason, "gen_type": gen_type, "seed": seed, **stats, **counts}

        generated = generator.generate()
        atomic_write_json(group_dir / "generator_state.json", generator.state_dict())
        expr = generated.expression
        stats["generation_attempt_count"] += 1
        stats["generated_sequence"].append(
            {"formula_hash": expr.sha256(), "formula_text": expr.to_string(), "tokens": list(expr.tokens)}
        )

        # Syntax validation
        valid, val_reason = expr.validate()
        if not valid:
            stats["syntax_invalid_count"] += 1
            continue

        # Cross-group cache check (evaluator's internal cache)
        cache_key = stable_hash(
            {
                "formula": expr.sha256(),
                "context": evaluator.context.context_hash,
                "config": evaluator.context.config.__dict__,
            }
        )
        is_cache_hit = cache_key in evaluator._cache

        # Group-level dedup (within this group's FormulaProgressStore)
        if expr.sha256() in records:
            stats["duplicate_count"] += 1
            continue

        # Initialize in progress store
        store.initialize_queue([(expr.sha256(), expr.to_string())])

        # Simulated interrupt
        if interrupt_after_completed is not None and counts.get("completed_full_backtest_count", 0) >= interrupt_after_completed:
            store.mark_running(expr.sha256())
            store.mark_interrupted_running()
            stats["interrupted_hash"] = expr.sha256()
            if pl_s:
                pl_s.record_hash()
            if stop_after_interrupt:
                if pl_s:
                    stats["update_count"] = pl_s.update_count
                    stats["update_skipped_count"] = pl_s.skipped_count
                    stats["update_skipped_reason_distribution"] = dict(pl_s.skip_reasons)
                return {"stop_reason": "simulated_interrupt", "gen_type": gen_type, "seed": seed, **stats, **counts}
        else:
            store.mark_running(expr.sha256())

        # Evaluate
        start = time.perf_counter()
        result = evaluator.evaluate(expr)
        elapsed = time.perf_counter() - start
        stats["formula_evaluation_seconds"] += elapsed
        if is_cache_hit:
            stats["cache_hit_count"] += 1
        else:
            stats["actual_full_backtest_execution_count"] += 1

        rew_result = reward_from_metrics(result.metrics, min_trade_count=1)
        payload = {
            "formula_hash": expr.sha256(),
            "formula_text": expr.to_string(),
            "tokens": list(expr.tokens),
            "metrics": result.metrics,
            "failure_reason": result.failure_reason,
            "elapsed_seconds": elapsed,
            "reward": rew_result.reward,
            "cache_hit": is_cache_hit,
            "sortino_available": result.metrics.get("sortino") is not None if result.metrics else False,
        }

        if result.failure_reason:
            store.mark_failed(expr.sha256(), result.failure_reason)
            _append_jsonl(group_dir / "failed_results.jsonl", payload)
            stats["failed_sequence"].append(expr.sha256())
        else:
            store.mark_completed(expr.sha256(), payload)
            stats["completed_sequence"].append(expr.sha256())
            # PositionLogit: accumulate reward for later batch update
            if pl_s and rew_result.validity_status == "valid":
                sk = pl_s.accept(generated, rew_result.reward)
                if sk:
                    stats["update_skipped_reason_distribution"][sk] = (
                        stats["update_skipped_reason_distribution"].get(sk, 0) + 1
                    )


def resume_one_group(
    gen_type: str,
    formulas: list[Expression],
    evaluator: BatchBacktestEvaluator,
    store: FormulaProgressStore,
    group_dir: Path,
) -> dict:
    """Resume interrupted formulas for one group."""
    completed_before = set(store.completed_hashes())
    resumed_hashes: list[str] = []
    formula_seconds = 0.0

    for expr in formulas:
        record = store.load().get(expr.sha256())
        if record is None or record.status in {"completed", "failed"}:
            continue
        store.mark_running(expr.sha256())
        start = time.perf_counter()
        result = evaluator.evaluate(expr)
        elapsed = time.perf_counter() - start
        formula_seconds += elapsed
        rew_result = reward_from_metrics(result.metrics, min_trade_count=1)
        payload = {
            "formula_hash": expr.sha256(),
            "formula_text": expr.to_string(),
            "tokens": list(expr.tokens),
            "metrics": result.metrics,
            "failure_reason": result.failure_reason,
            "elapsed_seconds": elapsed,
            "reward": rew_result.reward,
            "cache_hit": False,
        }
        if result.failure_reason:
            store.mark_failed(expr.sha256(), result.failure_reason)
            _append_jsonl(group_dir / "failed_results.jsonl", payload)
        else:
            store.mark_completed(expr.sha256(), payload)
        resumed_hashes.append(expr.sha256())

    return {
        "completed_before_resume": len(completed_before),
        "resumed_hashes": resumed_hashes,
        "completed_not_reexecuted": not completed_before.intersection(resumed_hashes),
        "formula_evaluation_seconds": formula_seconds,
    }


def _append_jsonl(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str) + "\n")


# ---------------------------------------------------------------------------
# Per-group statistics
# ---------------------------------------------------------------------------


def _group_stats_from_store(store: FormulaProgressStore) -> dict:
    records = store.load()
    counts = _budget_counts(records)

    completed = []
    for rec in records.values():
        if rec.status == "completed" and rec.summary_path:
            try:
                completed.append(json.loads(Path(rec.summary_path).read_text(encoding="utf-8")))
            except Exception:
                pass

    sortinos = [row["metrics"].get("sortino") for row in completed if row["metrics"].get("sortino") is not None]
    rewards_flat = [r for r in sortinos if r is not None]

    # Length / feature / operator distributions
    length_dist: dict[str, int] = {}
    feature_usage: dict[str, int] = {}
    operator_usage: dict[str, int] = {}
    trade_counts: list[int] = []
    for row in completed:
        toks = row.get("tokens", [])
        length_dist[str(len(toks))] = length_dist.get(str(len(toks)), 0) + 1
        for t in toks:
            if t in {"RET1", "RET5", "VOL_RATIO20", "VOLUME_WEIGHTED_RET", "TREND60"}:
                feature_usage[t] = feature_usage.get(t, 0) + 1
            else:
                operator_usage[t] = operator_usage.get(t, 0) + 1
        tc = row["metrics"].get("trade_count")
        if tc is not None:
            trade_counts.append(int(tc))

    # Reward distribution
    arr = np.array(rewards_flat, dtype=float)
    finite = arr[np.isfinite(arr)]

    top5 = sorted(arr, reverse=True)[:5]
    top10 = sorted(arr, reverse=True)[: max(1, len(arr) // 10)]

    first_pos = None
    best_idx = None
    best_val = -1e9
    for i, r in enumerate(arr):
        if r > 0 and first_pos is None:
            first_pos = i + 1
        if r > best_val:
            best_val = r
            best_idx = i + 1

    failed = [r for r in records.values() if r.status == "failed"]
    fail_reasons: dict[str, int] = {}
    for rec in failed:
        r = rec.failure_reason or "unknown"
        fail_reasons[r] = fail_reasons.get(r, 0) + 1

    return {
        **counts,
        "sortino_available_count": len(sortinos),
        "sortino_available_ratio": round(len(sortinos) / len(completed), 4) if completed else 0.0,
        "positive_sortino_count": int((arr > 0).sum()),
        "negative_sortino_count": int((arr < 0).sum()),
        "zero_sortino_count": int((arr == 0).sum()),
        "reward_distribution": {
            "count": int(len(arr)),
            "finite_count": int(len(finite)),
            "mean": round(float(finite.mean()), 6) if len(finite) else None,
            "std": round(float(finite.std(ddof=0)), 6) if len(finite) else None,
            "min": round(float(finite.min()), 6) if len(finite) else None,
            "max": round(float(finite.max()), 6) if len(finite) else None,
            "p50": round(float(np.median(finite)), 6) if len(finite) else None,
            "p10": round(float(np.percentile(finite, 10)), 6) if len(finite) else None,
            "p90": round(float(np.percentile(finite, 90)), 6) if len(finite) else None,
        },
        "best_reward": round(float(best_val), 6) if best_val > -1e8 else None,
        "median_reward": round(float(np.median(finite)), 6) if len(finite) else None,
        "top_5_mean_reward": round(float(np.mean(top5)), 6) if top5 else None,
        "top_10_mean_reward": round(float(np.mean(top10)), 6) if top10 else None,
        "evaluations_to_first_positive": first_pos,
        "evaluations_to_best": best_idx,
        "generation_attempts_per_completed": round(counts["completed_full_backtest_count"] / max(counts.get("generation_attempt_count", 0), 1), 4),
        "unique_attempts_per_completed": round(counts["unique_formula_attempt_count"] / max(counts["completed_full_backtest_count"], 1), 4),
        "duplicate_rate": 0.0,  # filled from parent stats in merge
        "failure_rate": round(counts.get("failed_count", 0) / max(counts["unique_formula_attempt_count"], 1), 4),
        "trade_count_distribution": {
            "mean": round(float(np.mean(trade_counts)), 4) if trade_counts else None,
            "median": round(float(np.median(trade_counts)), 4) if trade_counts else None,
            "min": int(min(trade_counts)) if trade_counts else None,
            "max": int(max(trade_counts)) if trade_counts else None,
        },
        "failure_reason_distribution": fail_reasons,
        "formula_length_distribution": length_dist,
        "feature_usage_frequency": feature_usage,
        "operator_usage_frequency": operator_usage,
    }


# ---------------------------------------------------------------------------
# Overlap analysis
# ---------------------------------------------------------------------------


def _compute_overlap(group_results: list[dict]) -> dict:
    by_group: dict[str, set[str]] = {}
    for gr in group_results:
        key = f"{gr['gen_type']}_seed{gr['seed']}"
        by_group[key] = set(gr.get("completed_sequence", []))

    uni_keys = sorted(k for k in by_group if k.startswith("uniform_random"))
    pl_keys = sorted(k for k in by_group if k.startswith("position_logit"))

    # Within-searcher overlap
    uni_shared: set[str] = set()
    for i, u1 in enumerate(uni_keys):
        for u2 in uni_keys[i + 1 :]:
            uni_shared |= by_group[u1] & by_group[u2]

    pl_shared: set[str] = set()
    for i, p1 in enumerate(pl_keys):
        for p2 in pl_keys[i + 1 :]:
            pl_shared |= by_group[p1] & by_group[p2]

    # Between-searcher overlap
    all_uni: set[str] = set()
    for k in uni_keys:
        all_uni |= by_group[k]
    all_pl: set[str] = set()
    for k in pl_keys:
        all_pl |= by_group[k]

    total_union = all_uni | all_pl

    return {
        "uniform_groups": uni_keys,
        "position_logit_groups": pl_keys,
        "uniform_within_overlap_count": len(uni_shared),
        "position_logit_within_overlap_count": len(pl_shared),
        "between_overlap_count": len(all_uni & all_pl),
        "unique_to_uniform": len(all_uni - all_pl),
        "unique_to_position_logit": len(all_pl - all_uni),
        "uniform_total_unique": len(all_uni),
        "position_logit_total_unique": len(all_pl),
        "overlap_ratio": round(len(all_uni & all_pl) / max(len(total_union), 1), 4),
    }


# ---------------------------------------------------------------------------
# Searcher comparison
# ---------------------------------------------------------------------------


def _compare_searchers(group_statistics: list[dict]) -> dict:
    uni = [gs for gs in group_statistics if gs.get("gen_type") == "uniform_random"]
    pl = [gs for gs in group_statistics if gs.get("gen_type") == "position_logit"]

    def _extract(rows: list[dict], key: str) -> list[float | None]:
        return [r.get(key) for r in rows]

    per_seed: dict[str, dict] = {}
    for s in set(str(r.get("seed")) for r in group_statistics):
        u = [r for r in uni if str(r.get("seed")) == s]
        p = [r for r in pl if str(r.get("seed")) == s]
        u_row = u[0] if u else {}
        p_row = p[0] if p else {}
        per_seed[s] = {
            "uniform_median_reward": u_row.get("median_reward"),
            "position_logit_median_reward": p_row.get("median_reward"),
            "uniform_top_10_mean_reward": u_row.get("top_10_mean_reward"),
            "position_logit_top_10_mean_reward": p_row.get("top_10_mean_reward"),
            "uniform_positive_sortino_count": u_row.get("positive_sortino_count"),
            "position_logit_positive_sortino_count": p_row.get("positive_sortino_count"),
            "uniform_best_reward": u_row.get("best_reward"),
            "position_logit_best_reward": p_row.get("best_reward"),
            "uniform_duplicate_rate": u_row.get("duplicate_rate"),
            "position_logit_duplicate_rate": p_row.get("duplicate_rate"),
            "uniform_update_count": u_row.get("update_count", 0),
            "position_logit_update_count": p_row.get("update_count", 0),
            "uniform_update_skipped_count": u_row.get("update_skipped_count", 0),
            "position_logit_update_skipped_count": p_row.get("update_skipped_count", 0),
        }

    def _safe_mean(vals: list) -> float | None:
        f = [v for v in vals if v is not None]
        return round(float(np.mean(f)), 6) if f else None

    uni_top10 = _extract(uni, "top_10_mean_reward")
    pl_top10 = _extract(pl, "top_10_mean_reward")
    uni_med = _extract(uni, "median_reward")
    pl_med = _extract(pl, "median_reward")
    uni_pos = _extract(uni, "positive_sortino_count")
    pl_pos = _extract(pl, "positive_sortino_count")

    n_seeds = len(uni)
    majority_top10 = (
        sum(
            1 for s, d in per_seed.items()
            if (d.get("position_logit_top_10_mean_reward") or -1e9) > (d.get("uniform_top_10_mean_reward") or -1e9)
        ) > n_seeds / 2
    ) if n_seeds else False
    majority_med = (
        sum(
            1 for s, d in per_seed.items()
            if (d.get("position_logit_median_reward") or -1e9) > (d.get("uniform_median_reward") or -1e9)
        ) > n_seeds / 2
    ) if n_seeds else False
    majority_pos = (
        sum(
            1 for s, d in per_seed.items()
            if (d.get("position_logit_positive_sortino_count") or -999) > (d.get("uniform_positive_sortino_count") or -999)
        ) > n_seeds / 2
    ) if n_seeds else False

    return {
        "per_seed": per_seed,
        "aggregated": {
            "uniform_mean_top_10_mean_reward": _safe_mean(uni_top10),
            "position_logit_mean_top_10_mean_reward": _safe_mean(pl_top10),
            "uniform_mean_median_reward": _safe_mean(uni_med),
            "position_logit_mean_median_reward": _safe_mean(pl_med),
            "uniform_mean_positive_count": _safe_mean(uni_pos),
            "position_logit_mean_positive_count": _safe_mean(pl_pos),
            "n_seeds": n_seeds,
            "majority_top_10_advantage": majority_top10,
            "majority_median_advantage": majority_med,
            "majority_positive_ratio_advantage": majority_pos,
            "advantage_top_10_mean_reward": _safe_mean(pl_top10) > _safe_mean(uni_top10) if _safe_mean(pl_top10) is not None and _safe_mean(uni_top10) is not None else None,
            "advantage_median_reward": _safe_mean(pl_med) > _safe_mean(uni_med) if _safe_mean(pl_med) is not None and _safe_mean(uni_med) is not None else None,
            "advantage_positive_ratio": _safe_mean(pl_pos) > _safe_mean(uni_pos) if _safe_mean(pl_pos) is not None and _safe_mean(uni_pos) is not None else None,
        },
    }


# ---------------------------------------------------------------------------
# Context/profile helpers
# ---------------------------------------------------------------------------


def _context_profile_details(context: ResearchContext) -> dict:
    frames = {
        "bars": context.bars,
        "calendar": context.calendar,
        "constituents": context.constituents,
        "limits": context.limits,
        "tradability": context.tradability,
        "lifecycle": context.lifecycle,
        "st_status": context.st_status,
        "features": context.features,
        "standardized_features": context.standardized_features,
    }
    return {
        "daily_bar_query_seconds": context.profile.get("sqlite_daily_bars_seconds", 0.0),
        "calendar_query_seconds": context.profile.get("sqlite_trade_calendar_seconds", 0.0),
        "constituent_query_seconds": context.profile.get("sqlite_constituents_seconds", 0.0),
        "lifecycle_query_seconds": context.profile.get("sqlite_lifecycle_seconds", 0.0),
        "st_status_query_seconds": context.profile.get("sqlite_st_status_seconds", 0.0),
        "tradability_query_seconds": context.profile.get("sqlite_tradability_seconds", 0.0),
        "limit_price_query_seconds": context.profile.get("sqlite_limit_prices_seconds", 0.0),
        "base_feature_compute_seconds": context.profile.get("base_features_seconds", 0.0),
        "cross_section_normalize_seconds": context.profile.get("standardized_features_seconds", 0.0),
        "row_counts": {name: int(len(df)) for name, df in frames.items()},
        "dataframe_memory_bytes": {name: int(df.memory_usage(deep=True).sum()) for name, df in frames.items()},
        "peak_memory_mb": peak_memory_mb(),
    }


# ---------------------------------------------------------------------------
# Markdown report generator
# ---------------------------------------------------------------------------


def _fmt(val) -> str:
    if val is None:
        return "None"
    if isinstance(val, float):
        return f"{val:.4f}"
    if isinstance(val, bool):
        return str(val)
    return str(val)


def _build_markdown(output: dict) -> str:
    lines = ["# Stage 3.6D-1 Training Searcher Benchmark\n"]
    for w in WARNING_LINES:
        lines.append(f"{w}\n")
    lines.append(f"\nRun dir: `{output.get('run_dir', 'unknown')}`\n")

    # Status flags
    lines.append("\n## Overall Status\n\n")
    for k in [
        "all_groups_completed_equal_budget", "context_shared_safely",
        "position_logit_updates_valid", "uniform_not_updated",
        "provisional_training_advantage", "train_candidates_frozen",
        "ready_for_frozen_candidate_validation",
        "validation_accessed", "blind_test_accessed", "resume_validated",
    ]:
        lines.append(f"- {k}: `{_fmt(output.get(k))}`\n")

    # Per-group table
    gs_list = output.get("group_statistics", [])
    lines.append("\n## Per-Group Results\n\n")
    hdrs = ["Group", "Gen", "Seed", "Completed", "Failed", "Dup", "Cache",
             "BestR", "MedR", "Top10R", "Sort%", "Upd", "Skip", "ContextHash"]
    lines.append("| " + " | ".join(hdrs) + " |\n")
    lines.append("|" + "|".join(["---"] * len(hdrs)) + "|\n")
    for gs in gs_list:
        ch = gs.get("context_hash", output.get("context_hash", ""))[:12]
        lines.append(
            f"| {gs.get('group_id', '?')} | {gs.get('gen_type', '?')} "
            f"| {gs.get('seed', '?')} | {gs.get('completed_full_backtest_count', 0)} "
            f"| {gs.get('failed_count', 0)} | {gs.get('duplicate_count', 0)} "
            f"| {gs.get('cache_hit_count', 0)} | {_fmt(gs.get('best_reward'))} "
            f"| {_fmt(gs.get('median_reward'))} | {_fmt(gs.get('top_10_mean_reward'))} "
            f"| {_fmt(gs.get('sortino_available_ratio'))} | {gs.get('update_count', 0)} "
            f"| {gs.get('update_skipped_count', 0)} | {ch} |\n"
        )

    # Searcher comparison
    comp = output.get("searcher_comparison", {})
    agg = comp.get("aggregated", {})
    lines.append("\n## Searcher Comparison\n\n")
    for k, v in agg.items():
        lines.append(f"- {k}: `{_fmt(v)}`\n")

    ps = comp.get("per_seed", {})
    if ps:
        lines.append("\n### Per-Seed\n\n")
        for s in sorted(ps.keys()):
            d = ps[s]
            lines.append(f"#### Seed {s}\n")
            for k, v in d.items():
                lines.append(f"- {k}: `{_fmt(v)}`\n")

    # Overlap
    ol = output.get("overlap", {})
    lines.append("\n## Formula Overlap\n\n")
    for k, v in ol.items():
        if isinstance(v, list):
            continue
        lines.append(f"- {k}: `{_fmt(v)}`\n")

    # Resume
    rr = output.get("resume_results", {})
    if rr:
        lines.append("\n## Interrupt/Resume\n\n")
        for gid, rd in rr.items():
            lines.append(f"- {gid}: completed_not_reexecuted=`{rd.get('completed_not_reexecuted')}`, "
                         f"resumed_count=`{len(rd.get('resumed_hashes', []))}`\n")

    # Performance
    perf = output.get("performance", {})
    lines.append("\n## Performance\n\n")
    for k, v in perf.items():
        lines.append(f"- {k}: `{_fmt(v)}`\n")

    # Limitations
    lines.append("\n## Limitations\n\n")
    for lim in output.get("limitations", []):
        lines.append(f"- {lim}\n")

    lines.append("\n")
    return "".join(lines)


# ---------------------------------------------------------------------------
# Main entry-point
# ---------------------------------------------------------------------------


def run_searcher_training_benchmark(config_path: str | Path, repo_root: Path) -> dict:
    """Stage 3.6D-1: compare UniformRandom vs PositionLogit on training-set search."""
    repo_root = Path(repo_root)
    cfg = load_simple_yaml(config_path)
    bench_cfg = parse_benchmark_config(cfg)
    run_id = "searcher_training_benchmark_" + time.strftime("%Y%m%d_%H%M%S")
    run_dir = repo_root / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    (run_dir / "config_snapshot.yaml").write_text(Path(config_path).read_text(encoding="utf-8"), encoding="utf-8")

    # Build shared context
    split = cfg["research_split"]["train"]
    data_cfg = cfg["data"]
    from ashare_research.backtest.engine import BacktestConfig

    bt = BacktestConfig(
        start_date=split[0],
        end_date=split[1],
        rebalance_frequency=int(cfg["backtest"]["rebalance_frequency"]),
        top_n=int(cfg["backtest"]["top_n"]),
        initial_cash=float(cfg["backtest"]["initial_cash"]),
        cost_bps=float(cfg["backtest"]["one_way_cost_bps"]),
        unknown_tradability_policy=str(cfg["backtest"]["unknown_tradability_policy"]),
        runs_dir=str(run_dir / "independent_backtests"),
        temp_dir=str(run_dir / "tmp"),
        min_free_space_gb=0.0,
        max_run_output_gb=1.0,
    )
    provider = LocalSQLiteProvider(
        Path(".") / data_cfg["sqlite_path"],
        Path(".") / data_cfg.get("raw_sqlite_path", "stock-data/a_stock_selector.sqlite3"),
    )

    c_start = time.perf_counter()
    context = ResearchContext.build(
        provider, bt,
        data_snapshot_hash="stage3_6d1",
        progress_path=run_dir / "context_progress.json",
    )
    c_seconds = time.perf_counter() - c_start

    evaluator = BatchBacktestEvaluator(context, save_detail_policy=bench_cfg.save_detail_policy, run_dir=run_dir / "details")
    evaluator._get_market_indices()
    bt_hash = stable_hash(bt.__dict__)

    # Manifest
    manifest = {
        "run_id": run_id,
        "context_hash": context.context_hash,
        "config_hash": bt_hash,
        "data_snapshot_hash": "stage3_6d1",
        "feature_version": "phase1_base_features_v1",
        "operator_version": "phase1_operator_vocab_v1",
        "universe_version": "csi800_asof_from_b_ready",
        "tradability_rule_version": "b_ready_derived_tradability_and_limit_price",
        "price_policy_version": "signal_close_execution_next_raw_open",
        "code_commit": current_git_commit(repo_root),
        "warnings": list(WARNING_LINES),
        "searcher_benchmark_config": {
            "completed_full_backtest_target": bench_cfg.completed_full_backtest_target,
            "max_unique_formula_attempts": bench_cfg.max_unique_formula_attempts,
            "max_generation_attempts": bench_cfg.max_generation_attempts,
            "random_seeds": list(bench_cfg.random_seeds),
            "generators": list(bench_cfg.generators),
            "n_groups": bench_cfg.n_groups,
        },
    }
    atomic_write_json(run_dir / "manifest.json", manifest)

    # Context manifest
    ctx_mf = {
        "context_hash": context.context_hash,
        "config": bt.__dict__,
        "profile": context.profile,
        "details": _context_profile_details(context),
        "validation_loaded": False,
        "blind_test_loaded": False,
    }
    atomic_write_json(run_dir / "context_manifest.json", ctx_mf)

    # Run all groups
    group_results: list[dict] = []
    all_ctx_hashes: list[str] = []

    for gd in bench_cfg.groups:
        gen_type = gd["generator"]
        seed = gd["seed"]
        grp_dir = run_dir / "group_manifests" / f"{gen_type}_seed{seed}"
        grp_dir.mkdir(parents=True, exist_ok=True)

        grp_manifest = {
            **manifest,
            "generator": gen_type,
            "seed": seed,
        }
        store = FormulaProgressStore(grp_dir, grp_manifest)

        # Interrupt: first Uniform group and first PositionLogit group
        is_interrupt = (
            (gen_type == "uniform_random" and seed == bench_cfg.random_seeds[0])
            or (gen_type == "position_logit" and seed == bench_cfg.random_seeds[0])
        )
        ia = 30 if is_interrupt else None
        sa = bool(is_interrupt)

        first = run_one_group(gen_type, seed, evaluator, store, bench_cfg, grp_dir,
                              interrupt_after_completed=ia, stop_after_interrupt=sa)

        resumed: dict = {"completed_not_reexecuted": True, "formula_evaluation_seconds": 0.0, "resumed_hashes": []}

        if first.get("stop_reason") == "simulated_interrupt":
            # Resume interrupted formulas
            formulas = [
                parse_formula_text(row["formula_text"])
                for row in first.get("generated_sequence", [])
                if row["formula_hash"] in store.load()
            ]
            resumed = resume_one_group(gen_type, formulas, evaluator, store, grp_dir)

            # Second pass to complete budget
            second = run_one_group(gen_type, seed, evaluator, store, bench_cfg, grp_dir)

            # Merge
            for key in ["generation_attempt_count", "duplicate_count", "syntax_invalid_count",
                        "cache_hit_count", "actual_full_backtest_execution_count",
                        "update_count", "update_skipped_count"]:
                first[key] = first.get(key, 0) + second.get(key, 0)
            first["formula_evaluation_seconds"] = (
                first.get("formula_evaluation_seconds", 0.0)
                + resumed.get("formula_evaluation_seconds", 0.0)
                + second.get("formula_evaluation_seconds", 0.0)
            )
            first["completed_sequence"] = first.get("completed_sequence", []) + second.get("completed_sequence", [])
            first["failed_sequence"] = first.get("failed_sequence", []) + second.get("failed_sequence", [])
            # Budget counts from store after second pass
            final_counts = _budget_counts(store.load())
            first.update(final_counts)
            first["stop_reason"] = second.get("stop_reason", first.get("stop_reason"))
            # Reload finished generator state
            if (grp_dir / "generator_state.json").exists():
                try:
                    restored = json.loads((grp_dir / "generator_state.json").read_text(encoding="utf-8"))
                    first["final_generator_state_hash"] = stable_hash(restored)
                except Exception:
                    pass

        first["group_id"] = f"{gen_type}_seed{seed}"
        first["gen_type"] = gen_type
        first["seed"] = seed
        first["context_hash"] = context.context_hash
        group_results.append(first)
        all_ctx_hashes.append(context.context_hash)

        atomic_write_json(grp_dir / "group_result.json", first)
        atomic_write_json(grp_dir / "resume_result.json", resumed)

    # Per-group detailed statistics
    group_statistics = []
    for gr in group_results:
        grp_dir = run_dir / "group_manifests" / f"{gr['gen_type']}_seed{gr['seed']}"
        store = FormulaProgressStore(grp_dir, manifest)
        gs = _group_stats_from_store(store)
        gs.update({
            "group_id": gr["group_id"],
            "gen_type": gr["gen_type"],
            "seed": gr["seed"],
            "generation_attempt_count": gr.get("generation_attempt_count", 0),
            "duplicate_count": gr.get("duplicate_count", 0),
            "cache_hit_count": gs.get("cache_hit_count", 0),
            "formula_evaluation_seconds": gr.get("formula_evaluation_seconds", 0.0),
            "update_count": gr.get("update_count", 0),
            "update_skipped_count": gr.get("update_skipped_count", 0),
            "update_skipped_reason_distribution": gr.get("update_skipped_reason_distribution", {}),
            "parameter_hash_after": None,
            "context_hash": context.context_hash,
        })
        group_statistics.append(gs)

    context_hash_stable = all(h == context.context_hash for h in all_ctx_hashes) if all_ctx_hashes else True

    overlap = _compute_overlap(group_results)
    searcher_comp = _compare_searchers(group_statistics)

    # Resume results dict
    resume_results: dict = {}
    for gr in group_results:
        gid = gr["group_id"]
        if not gr.get("interrupted_hash"):
            continue
        rp = run_dir / "group_manifests" / f"{gr['gen_type']}_seed{gr['seed']}" / "resume_result.json"
        if rp.exists():
            resume_results[gid] = json.loads(rp.read_text(encoding="utf-8"))

    # Performance
    total_wall = time.perf_counter() - (c_start if not c_seconds else (time.perf_counter() - c_seconds)) + c_seconds
    # Rough recalc
    total_eval_secs = sum(gr.get("formula_evaluation_seconds", 0.0) for gr in group_results)
    total_completed = sum(gs.get("completed_full_backtest_count", 0) for gs in group_statistics)
    avg_f = round(total_eval_secs / max(total_completed, 1), 4) if total_completed else None

    perf = {
        "context_build_seconds": round(c_seconds, 4),
        "context_rebuild_seconds": 0.0,
        "generator_seconds": 0.0,
        "formula_evaluation_seconds": round(total_eval_secs, 4),
        "actual_backtest_seconds": round(total_eval_secs, 4),
        "cache_lookup_seconds": 0.0,
        "checkpoint_seconds": 0.0,
        "total_wall_seconds": round(total_wall, 4),
        "average_completed_formula_seconds": avg_f,
        "median_formula_seconds": round(float(np.median([gr.get("formula_evaluation_seconds", 0) for gr in group_results])), 4) if group_results else None,
        "peak_memory_mb": round(peak_memory_mb(), 2),
        "run_output_mb": round(disk_mb(run_dir), 4),
        "tmp_residual_count": len(list((run_dir / "tmp").glob("*"))) if (run_dir / "tmp").exists() else 0,
        "detail_directory_count": len(list((run_dir / "details").glob("*"))) if (run_dir / "details").exists() else 0,
    }

    # Conclusions
    all_eq = all(
        gs.get("completed_full_backtest_count", 0) == bench_cfg.completed_full_backtest_target
        for gs in group_statistics
    )
    all_zero_pend = all(gs.get("pending_count", 999) == 0 for gs in group_statistics)
    all_zero_run = all(gs.get("running_count", 999) == 0 for gs in group_statistics)
    all_zero_int = all(gs.get("interrupted_count", 999) == 0 for gs in group_statistics)
    all_groups_equal = all_eq and all_zero_pend and all_zero_run and all_zero_int

    pl_groups = [gs for gs in group_statistics if gs["gen_type"] == "position_logit"]
    pl_valid_updates = all(gs.get("update_count", 0) > 0 for gs in pl_groups)
    uni_groups = [gs for gs in group_statistics if gs["gen_type"] == "uniform_random"]
    uni_no_updates = all(gs.get("update_count", 0) == 0 for gs in uni_groups)

    agg = searcher_comp.get("aggregated", {})
    prov_adv = (
        all_groups_equal and pl_valid_updates and uni_no_updates
        and agg.get("advantage_top_10_mean_reward") is True
        and (
            agg.get("advantage_median_reward") is True
            or agg.get("advantage_positive_ratio") is True
        )
    )

    resume_ok = all(
        r.get("completed_not_reexecuted", True) for r in resume_results.values()
    ) if resume_results else True

    output = {
        "run_id": run_id,
        "run_dir": str(run_dir),
        "warnings": list(WARNING_LINES),
        "train_interval": split,
        "validation_accessed": False,
        "blind_test_accessed": False,
        "validation_split_configured": False,
        "context_shared_safely": context_hash_stable,
        "context_hash_stable": context_hash_stable,
        "context_hash": context.context_hash,
        "all_groups_completed_equal_budget": all_groups_equal,
        "position_logit_updates_valid": pl_valid_updates,
        "uniform_not_updated": uni_no_updates,
        "provisional_training_advantage": prov_adv,
        "train_candidates_frozen": False,
        "ready_for_frozen_candidate_validation": False,
        "resume_validated": resume_ok,
        "seeds_used": list(bench_cfg.random_seeds),
        "seed_selection_basis": "reused from Stage 3.6 search benchmark (seeds 11, 23, 47)",
        "group_statistics": group_statistics,
        "searcher_comparison": searcher_comp,
        "overlap": overlap,
        "resume_results": resume_results,
        "performance": perf,
        "limitations": [
            "Training-set only comparison; no validation or blind test accessed.",
            "Candidates are not frozen because frozen_candidate_top_n is not configured.",
            "B-ready data with approximate tradability.",
            "PositionLogitGenerator is a position-dependent logit model, not a Transformer.",
            "Stage 3.6D-1 does not produce final searcher A/B/C rating.",
        ],
        "group_results": group_results,
    }

    # Write all output files
    atomic_write_json(run_dir / "group_statistics.json", group_statistics)
    atomic_write_json(run_dir / "aggregate_statistics.json", output)
    atomic_write_json(run_dir / "formula_overlap.json", overlap)
    atomic_write_json(run_dir / "performance.json", perf)
    atomic_write_json(run_dir / "searcher_comparison.json", searcher_comp)

    report_md = _build_markdown(output)
    (run_dir / "report.md").write_text(report_md, encoding="utf-8")

    docs_dir = repo_root / "docs"
    docs_dir.mkdir(exist_ok=True)
    atomic_write_json(docs_dir / "stage3_6d1_training_searcher_benchmark.json", output)
    (docs_dir / "stage3_6d1_training_searcher_benchmark.md").write_text(report_md, encoding="utf-8")

    return output
