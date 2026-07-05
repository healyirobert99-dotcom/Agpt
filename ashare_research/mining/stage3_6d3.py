from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from ashare_research.backtest.batch import BatchBacktestEvaluator
from ashare_research.backtest.context import ResearchContext
from ashare_research.backtest.engine import BacktestConfig
from ashare_research.backtest.golden import current_git_commit
from ashare_research.backtest.progress import FormulaProgressStore, atomic_write_json
from ashare_research.config import load_simple_yaml
from ashare_research.data.local_sqlite_provider import LocalSQLiteProvider
from ashare_research.factors.base_features import compute_base_features, robust_cross_sectional_standardize
from ashare_research.factors.expression import Expression, parse_formula_text
from ashare_research.mining.stage3_6 import disk_mb, peak_memory_mb
from ashare_research.registry.artifacts import stable_hash


GENERATOR_UNIFORM = "UniformRandomGenerator"
GENERATOR_POSITION = "PositionLogitGenerator"


@dataclass(frozen=True)
class FreezeBundle:
    freeze_dir: Path
    manifest: dict
    uniform: list[dict]
    position: list[dict]
    global_unique: list[dict]
    overlap: dict
    provenance: dict


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def verify_freeze_manifest_hash(manifest: dict) -> str:
    return stable_hash({k: v for k, v in manifest.items() if k not in {"created_at_unix", "freeze_manifest_hash"}})


def load_and_verify_freeze(freeze_manifest_path: str | Path) -> FreezeBundle:
    manifest_path = Path(freeze_manifest_path)
    freeze_dir = manifest_path.parent
    manifest = read_json(manifest_path)
    uniform = read_json(freeze_dir / "uniform_candidates.json")
    position = read_json(freeze_dir / "position_logit_candidates.json")
    global_unique = read_json(freeze_dir / "global_unique_candidates.json")
    overlap = read_json(freeze_dir / "candidate_overlap.json")
    provenance = read_json(freeze_dir / "candidate_provenance.json")
    checks = {
        "uniform_candidates_hash": stable_hash(uniform),
        "position_logit_candidates_hash": stable_hash(position),
        "global_unique_candidates_hash": stable_hash(global_unique),
        "freeze_manifest_hash": verify_freeze_manifest_hash(manifest),
    }
    for key, value in checks.items():
        if manifest.get(key) != value:
            raise ValueError(f"freeze_hash_mismatch:{key}")
    if len(uniform) != 20 or len(position) != 20 or len(global_unique) != 31:
        raise ValueError("unexpected_frozen_candidate_count")
    if len({row["formula_hash"] for row in global_unique}) != 31:
        raise ValueError("global_unique_candidate_hash_count_mismatch")
    if overlap.get("cross_searcher_overlap_count") != 9:
        raise ValueError("unexpected_cross_searcher_overlap_count")
    return FreezeBundle(freeze_dir, manifest, uniform, position, global_unique, overlap, provenance)


def build_backtest_config(cfg: dict, run_dir: Path) -> BacktestConfig:
    validation = cfg["validation"]
    return BacktestConfig(
        start_date=str(validation["start_date"]),
        end_date=str(validation["end_date"]),
        rebalance_frequency=int(cfg["backtest"]["rebalance_frequency"]),
        top_n=int(cfg["backtest"]["top_n"]),
        initial_cash=float(cfg["backtest"]["initial_cash"]),
        cost_bps=float(cfg["backtest"]["one_way_cost_bps"]),
        unknown_tradability_policy=str(cfg["backtest"]["unknown_tradability_policy"]),
        runs_dir=str(run_dir / "independent_backtests"),
        temp_dir=str(run_dir / "tmp"),
        min_free_space_gb=0.0,
        max_run_output_gb=float(cfg.get("storage", {}).get("max_run_output_gb", 1)),
    )


def validation_provider(cfg: dict, repo_root: Path) -> LocalSQLiteProvider:
    data = cfg["data"]
    if data.get("allow_network", False):
        raise ValueError("validation_requires_allow_network_false")
    return LocalSQLiteProvider(repo_root / data["sqlite_path"], repo_root / data.get("raw_sqlite_path", "stock-data/a_stock_selector.sqlite3"))


def warmup_start_date(provider: LocalSQLiteProvider, validation_start: str, validation_end: str, warmup_trading_days: int) -> str:
    calendar = provider.get_trade_calendar("20240101", validation_end)
    dates = list(calendar["trade_date"].astype(str))
    if validation_start not in dates:
        raise ValueError("validation_start_not_open_day")
    idx = dates.index(validation_start)
    start_idx = max(0, idx - int(warmup_trading_days))
    return dates[start_idx]


def build_validation_context(provider: LocalSQLiteProvider, config: BacktestConfig, *, warmup_start: str, data_snapshot_hash: str, progress_path: str | Path | None = None) -> ResearchContext:
    profile: dict[str, float] = {}
    progress = Path(progress_path) if progress_path else None

    def write_progress(stage: str, **payload) -> None:
        if progress is None:
            return
        progress.parent.mkdir(parents=True, exist_ok=True)
        progress.write_text(json.dumps({"stage": stage, **payload}, ensure_ascii=False, indent=2, sort_keys=True, default=str), encoding="utf-8")

    def timed(name: str, fn):
        write_progress(name + "_started")
        start = time.perf_counter()
        value = fn()
        elapsed = time.perf_counter() - start
        profile[name + "_seconds"] = elapsed
        rows = len(value) if hasattr(value, "__len__") else None
        write_progress(name + "_completed", rows=rows, elapsed_seconds=elapsed)
        return value

    bars = timed("daily_bars_query", lambda: provider.get_daily_bars(warmup_start, config.end_date))
    calendar = timed("calendar_query", lambda: provider.get_trade_calendar(config.start_date, config.end_date))
    constituents = timed("constituents_query", lambda: provider.get_index_constituents("CSI800", config.start_date, config.end_date))
    limits = timed("limit_prices", lambda: provider.get_limit_prices(config.start_date, config.end_date))
    tradability = timed("tradability_query", lambda: provider.get_tradability_flags(config.start_date, config.end_date))
    lifecycle = timed("lifecycle_query", provider.get_lifecycle)
    st_status = timed("historical_st_query", lambda: provider.get_historical_st_status(config.start_date, config.end_date))
    features = timed("base_features", lambda: compute_base_features(bars))
    standardized = timed("normalization", lambda: robust_cross_sectional_standardize(features, min_count=2))
    dates = tuple(calendar["trade_date"].astype(str))
    payload = {
        "config": config.__dict__,
        "warmup_start": warmup_start,
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
    write_progress("context_hash_started")
    context_hash = stable_hash(payload)
    write_progress("context_hash_completed", context_hash=context_hash)
    return ResearchContext(
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


def candidate_source_maps(bundle: FreezeBundle) -> dict[str, dict]:
    source: dict[str, dict] = {}
    for label, rows in ((GENERATOR_UNIFORM, bundle.uniform), (GENERATOR_POSITION, bundle.position)):
        for row in rows:
            entry = source.setdefault(
                row["formula_hash"],
                {
                    "formula_hash": row["formula_hash"],
                    "formula_text": row["formula_text"],
                    "token_sequence": row["token_sequence"],
                    "source_generators": [],
                    "source_seeds": [],
                    "uniform_train_rank": None,
                    "position_logit_train_rank": None,
                    "train_sortino_by_generator": {},
                },
            )
            entry["source_generators"].append(label)
            entry["source_seeds"] = sorted(set(entry["source_seeds"]) | set(row["source_seeds"]))
            if label == GENERATOR_UNIFORM:
                entry["uniform_train_rank"] = row["train_rank_within_generator"]
            else:
                entry["position_logit_train_rank"] = row["train_rank_within_generator"]
            entry["train_sortino_by_generator"][label] = row["train_reward"]
    return source


def expressions_from_freeze(bundle: FreezeBundle) -> list[Expression]:
    expressions = []
    for row in bundle.global_unique:
        expr = parse_formula_text(row["formula_text"])
        if expr.sha256() != row["formula_hash"]:
            raise ValueError(f"formula_hash_mismatch:{row['formula_hash']}")
        expressions.append(expr)
    return expressions


def validation_summary(expr: Expression, result, elapsed_seconds: float, source: dict) -> dict:
    sortino = result.metrics.get("sortino") if result.metrics else None
    train_values = [value for value in source["train_sortino_by_generator"].values() if value is not None]
    train_sortino = max(train_values) if train_values else None
    return {
        "formula_hash": expr.sha256(),
        "formula_text": expr.to_string(),
        "token_sequence": list(expr.tokens),
        "training_sources": source,
        "source_generators": source["source_generators"],
        "source_seeds": source["source_seeds"],
        "uniform_train_rank": source["uniform_train_rank"],
        "position_logit_train_rank": source["position_logit_train_rank"],
        "train_sortino": train_sortino,
        "validation_sortino": sortino,
        "validation_metrics": result.metrics,
        "validation_status": "failed" if result.failure_reason else "completed",
        "failure_reason": result.failure_reason,
        "train_validation_decay": (train_sortino - sortino) if train_sortino is not None and sortino is not None else None,
        "positive_sign_preserved": bool(train_sortino is not None and sortino is not None and train_sortino > 0 and sortino > 0),
        "elapsed_seconds": elapsed_seconds,
    }


def evaluate_frozen_candidates(
    expressions: list[Expression],
    evaluator: BatchBacktestEvaluator,
    store: FormulaProgressStore,
    source_map: dict[str, dict],
    *,
    run_dir: Path,
    interrupt_after_completed: int | None = 10,
) -> dict:
    completed_sequence: list[str] = []
    failed_sequence: list[str] = []
    interrupted_hash: str | None = None
    formula_seconds = 0.0
    store.initialize_queue((expr.sha256(), expr.to_string()) for expr in expressions)
    for expr in expressions:
        record = store.load()[expr.sha256()]
        if record.status in {"completed", "failed"}:
            continue
        if interrupt_after_completed is not None and len(store.completed_hashes()) >= interrupt_after_completed and interrupted_hash is None:
            store.mark_running(expr.sha256())
            store.mark_interrupted_running()
            interrupted_hash = expr.sha256()
            break
        _evaluate_one(expr, evaluator, store, source_map, run_dir, completed_sequence, failed_sequence, formula_seconds_ref := {"seconds": 0.0})
        formula_seconds += formula_seconds_ref["seconds"]
    resumed_execution = []
    for expr in expressions:
        record = store.load()[expr.sha256()]
        if record.status not in {"pending", "interrupted"}:
            continue
        resumed_execution.append(expr.sha256())
        _evaluate_one(expr, evaluator, store, source_map, run_dir, completed_sequence, failed_sequence, formula_seconds_ref := {"seconds": 0.0})
        formula_seconds += formula_seconds_ref["seconds"]
    return {
        "completed_sequence": completed_sequence,
        "failed_sequence": failed_sequence,
        "interrupted_hash": interrupted_hash,
        "resumed_execution": resumed_execution,
        "completed_not_reexecuted": bool(interrupted_hash is None or interrupted_hash in resumed_execution),
        "formula_evaluation_seconds": formula_seconds,
    }


def _evaluate_one(expr: Expression, evaluator: BatchBacktestEvaluator, store: FormulaProgressStore, source_map: dict[str, dict], run_dir: Path, completed_sequence: list[str], failed_sequence: list[str], formula_seconds_ref: dict) -> None:
    store.mark_running(expr.sha256())
    start = time.perf_counter()
    result = evaluator.evaluate(expr)
    elapsed = time.perf_counter() - start
    formula_seconds_ref["seconds"] = elapsed
    payload = validation_summary(expr, result, elapsed, source_map[expr.sha256()])
    if result.failure_reason:
        payload["failure_stage"] = "formula_execution" if str(result.failure_reason).startswith("invalid_formula:") else "backtest"
        store.mark_failed(expr.sha256(), result.failure_reason)
        _append_jsonl(run_dir / "failed_results.jsonl", payload)
        failed_sequence.append(expr.sha256())
    else:
        store.mark_completed(expr.sha256(), payload)
        completed_sequence.append(expr.sha256())


def _append_jsonl(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str) + "\n")


def load_completed_summaries(store: FormulaProgressStore) -> list[dict]:
    rows = []
    for record in store.load().values():
        if record.status == "completed" and record.summary_path:
            rows.append(read_json(Path(record.summary_path)))
    return sorted(rows, key=lambda row: row["formula_hash"])


def distribution(values: list[float]) -> dict:
    if not values:
        return {"count": 0}
    arr = np.array(values, dtype=float)
    return {
        "count": int(len(arr)),
        "mean": float(arr.mean()),
        "median": float(np.median(arr)),
        "std": float(arr.std()),
        "min": float(arr.min()),
        "max": float(arr.max()),
        "p10": float(np.percentile(arr, 10)),
        "p90": float(np.percentile(arr, 90)),
    }


def view_statistics(rows: list[dict]) -> dict:
    sortinos = [row["validation_sortino"] for row in rows if row["validation_sortino"] is not None]
    train = [row["train_sortino"] for row in rows if row["train_sortino"] is not None and row["validation_sortino"] is not None]
    val = [row["validation_sortino"] for row in rows if row["train_sortino"] is not None and row["validation_sortino"] is not None]
    top10 = sorted(sortinos, reverse=True)[: max(1, len(sortinos) // 10)] if sortinos else []
    return {
        "candidate_count": len(rows),
        "completed_count": sum(row["validation_status"] == "completed" for row in rows),
        "failed_formula_count": sum(row["validation_status"] != "completed" for row in rows),
        "validation_sortino_available_ratio": len(sortinos) / len(rows) if rows else 0.0,
        "validation_sortino_median": float(np.median(sortinos)) if sortinos else None,
        "validation_sortino_mean": float(np.mean(sortinos)) if sortinos else None,
        "validation_top_10_mean": float(np.mean(top10)) if top10 else None,
        "validation_positive_ratio": sum(value > 0 for value in sortinos) / len(sortinos) if sortinos else 0.0,
        "validation_negative_ratio": sum(value < 0 for value in sortinos) / len(sortinos) if sortinos else 0.0,
        "validation_best": max(sortinos) if sortinos else None,
        "validation_worst": min(sortinos) if sortinos else None,
        "validation_reward_std": float(np.std(sortinos)) if sortinos else None,
        "train_validation_sortino_decay": float(np.mean([t - v for t, v in zip(train, val)])) if train else None,
        "positive_sign_preservation_ratio": sum(t > 0 and v > 0 for t, v in zip(train, val)) / sum(t > 0 for t in train) if any(t > 0 for t in train) else None,
        "train_validation_spearman": spearman_rank_correlation(train, val),
        "train_validation_rank_retention": rank_retention(train, val),
        "trade_count_distribution": distribution([float(row["validation_metrics"].get("trade_count", 0)) for row in rows if row["validation_metrics"]]),
        "annualized_return_distribution": distribution([float(row["validation_metrics"]["annualized_return"]) for row in rows if row["validation_metrics"].get("annualized_return") is not None]),
        "max_drawdown_distribution": distribution([float(row["validation_metrics"]["max_drawdown"]) for row in rows if row["validation_metrics"].get("max_drawdown") is not None]),
        "turnover_or_cost_distribution": distribution([float(row["validation_metrics"].get("cumulative_cost", 0.0)) for row in rows if row["validation_metrics"]]),
        "failure_reason_distribution": failure_distribution(rows),
    }


def rank_retention(train: list[float], val: list[float]) -> float | None:
    if len(train) < 2:
        return None
    n = max(1, int(np.ceil(len(train) * 0.2)))
    train_top = set(np.argsort(train)[-n:])
    val_top = set(np.argsort(val)[-n:])
    return len(train_top & val_top) / n


def spearman_rank_correlation(train: list[float], val: list[float]) -> float | None:
    if len(train) < 2 or len(val) < 2 or len(train) != len(val):
        return None
    paired = pd.DataFrame({"train": train, "validation": val}, dtype="float64").dropna()
    if len(paired) < 2:
        return None
    train_rank = paired["train"].rank(method="average")
    val_rank = paired["validation"].rank(method="average")
    corr = train_rank.corr(val_rank)
    if pd.isna(corr):
        return None
    return float(corr)


def failure_distribution(rows: list[dict]) -> dict[str, int]:
    out: dict[str, int] = {}
    for row in rows:
        reason = row.get("failure_reason")
        if reason:
            out[reason] = out.get(reason, 0) + 1
    return out


def build_views(bundle: FreezeBundle, formula_results: list[dict]) -> dict:
    by_hash = {row["formula_hash"]: row for row in formula_results}
    uniform_hashes = [row["formula_hash"] for row in bundle.uniform]
    position_hashes = [row["formula_hash"] for row in bundle.position]
    uniform_set = set(uniform_hashes)
    position_set = set(position_hashes)
    views = {
        "uniform": [by_hash[h] for h in uniform_hashes],
        "position_logit": [by_hash[h] for h in position_hashes],
        "uniform_exclusive": [by_hash[h] for h in uniform_hashes if h not in position_set],
        "position_logit_exclusive": [by_hash[h] for h in position_hashes if h not in uniform_set],
        "overlap": [by_hash[h] for h in sorted(uniform_set & position_set)],
    }
    return views


def compare_pair(left: dict, right: dict) -> dict:
    metrics = ["validation_sortino_median", "validation_top_10_mean", "validation_positive_ratio"]
    left_wins = sum((left.get(m) is not None and right.get(m) is not None and left[m] > right[m]) for m in metrics)
    right_wins = sum((left.get(m) is not None and right.get(m) is not None and right[m] > left[m]) for m in metrics)
    return {"metrics": metrics, "left_wins": left_wins, "right_wins": right_wins}


def validation_conclusion(stats: dict) -> str:
    full = compare_pair(stats["position_logit_full"], stats["uniform_full"])
    exclusive = compare_pair(stats["position_logit_exclusive"], stats["uniform_exclusive"])
    pos_ok = (
        full["left_wins"] >= 2
        and exclusive["left_wins"] >= 2
        and stats["position_logit_full"]["validation_sortino_available_ratio"] >= stats["uniform_full"]["validation_sortino_available_ratio"] * 0.8
    )
    uni_ok = (
        full["right_wins"] >= 2
        and exclusive["right_wins"] >= 2
        and stats["uniform_full"]["validation_sortino_available_ratio"] >= stats["position_logit_full"]["validation_sortino_available_ratio"] * 0.8
    )
    if pos_ok and not uni_ok:
        return "position_logit_advantage"
    if uni_ok and not pos_ok:
        return "uniform_random_advantage"
    return "inconclusive"


def freeze_blind_shortlist(run_dir: Path, formula_results: list[dict], config: dict, validation_results_hash: str) -> dict:
    top_n = int(config["blind_shortlist"]["top_n"])
    eligible = [
        row for row in formula_results
        if row["validation_status"] == "completed"
        and row["validation_sortino"] is not None
        and float(row["validation_sortino"]) > 0.0
    ]
    ranked = sorted(eligible, key=lambda r: (-float(r["validation_sortino"]), -(float(r["train_sortino"]) if r["train_sortino"] is not None else -1e99), r["formula_hash"]))
    shortlist = ranked[:top_n]
    payload = {
        "top_n": top_n,
        "validation_results_hash": validation_results_hash,
        "shortlist_hash_input": [{"formula_hash": row["formula_hash"], "validation_sortino": row["validation_sortino"], "train_sortino": row["train_sortino"]} for row in shortlist],
    }
    shortlist_id = stable_hash(payload)[:16]
    out_dir = run_dir / "frozen_blind_shortlist" / shortlist_id
    if out_dir.exists():
        raise FileExistsError(out_dir)
    out_dir.mkdir(parents=True)
    global_hash = stable_hash(shortlist)
    provenance = {
        "selection_rule": "validation_sortino_desc_then_training_sortino_desc_then_formula_hash_asc",
        "eligible_count": len(eligible),
        "source": "global_unique_validation_results",
        "blind_test_data_accessed": False,
    }
    manifest = {
        "shortlist_id": shortlist_id,
        "created_at_unix": time.time(),
        "top_n": top_n,
        "eligible_blind_candidates": len(eligible),
        "frozen_blind_shortlist_count": len(shortlist),
        "validation_results_hash": validation_results_hash,
        "global_shortlist_hash": global_hash,
        "blind_shortlist_frozen": True,
        "blind_test_data_accessed": False,
    }
    manifest["shortlist_manifest_hash"] = stable_hash({k: v for k, v in manifest.items() if k != "created_at_unix"})
    atomic_write_json(out_dir / "global_shortlist.json", shortlist)
    atomic_write_json(out_dir / "shortlist_provenance.json", provenance)
    atomic_write_json(out_dir / "validation_results_hash.json", {"validation_results_hash": validation_results_hash, "global_shortlist_hash": global_hash})
    atomic_write_json(out_dir / "shortlist_manifest.json", manifest)
    return {"shortlist_dir": str(out_dir), "shortlist_manifest": manifest, "global_shortlist": shortlist, "shortlist_provenance": provenance}


def run_frozen_candidate_validation(config_path: str | Path, repo_root: Path) -> dict:
    cfg = load_simple_yaml(config_path)
    if cfg.get("test_only") is not True:
        raise ValueError("stage3_6d3_requires_test_only_true")
    bundle = load_and_verify_freeze(repo_root / cfg["candidate_source"]["freeze_manifest"])
    run_id = "frozen_candidate_validation_" + time.strftime("%Y%m%d_%H%M%S")
    run_dir = repo_root / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    (run_dir / "config_snapshot.yaml").write_text(Path(config_path).read_text(encoding="utf-8"), encoding="utf-8")
    atomic_write_json(run_dir / "source_freeze_manifest.json", bundle.manifest)

    provider = validation_provider(cfg, repo_root)
    bt = build_backtest_config(cfg, run_dir)
    warmup_start = warmup_start_date(provider, bt.start_date, bt.end_date, int(cfg["validation"].get("warmup_trading_days", 80)))
    context_start = time.perf_counter()
    context = build_validation_context(provider, bt, warmup_start=warmup_start, data_snapshot_hash="stage3_6d3_validation", progress_path=run_dir / "context_progress.json")
    context_seconds = time.perf_counter() - context_start
    source_map = candidate_source_maps(bundle)
    expressions = expressions_from_freeze(bundle)
    evaluator = BatchBacktestEvaluator(context, save_detail_policy="summary_only", run_dir=run_dir / "details")
    manifest = {
        "run_id": run_id,
        "context_hash": context.context_hash,
        "config_hash": stable_hash(bt.__dict__),
        "data_snapshot_hash": "stage3_6d3_validation",
        "feature_version": "phase1_base_features_v1",
        "operator_version": "phase1_operator_vocab_v1",
        "universe_version": "csi800_asof_from_b_ready",
        "tradability_rule_version": "b_ready_derived_tradability_and_limit_price",
        "price_policy_version": "signal_close_execution_next_raw_open",
        "code_commit": current_git_commit(repo_root),
        "freeze_manifest_hash": bundle.manifest["freeze_manifest_hash"],
        "validation_start": bt.start_date,
        "validation_end": bt.end_date,
        "warmup_start": warmup_start,
        "blind_test_data_accessed": False,
    }
    store = FormulaProgressStore(run_dir, manifest)
    eval_result = evaluate_frozen_candidates(expressions, evaluator, store, source_map, run_dir=run_dir, interrupt_after_completed=10)
    formula_results = load_completed_summaries(store)
    views = build_views(bundle, formula_results)
    stats = {
        "uniform_full": view_statistics(views["uniform"]),
        "position_logit_full": view_statistics(views["position_logit"]),
        "uniform_exclusive": view_statistics(views["uniform_exclusive"]),
        "position_logit_exclusive": view_statistics(views["position_logit_exclusive"]),
        "overlap": view_statistics(views["overlap"]),
    }
    conclusion = validation_conclusion(stats)
    validation_results_hash = stable_hash(formula_results)
    shortlist = freeze_blind_shortlist(run_dir, formula_results, cfg, validation_results_hash)
    performance = {
        "context_build_seconds": context_seconds,
        "formula_evaluation_seconds": eval_result["formula_evaluation_seconds"],
        "total_wall_seconds": context_seconds + eval_result["formula_evaluation_seconds"],
        "average_formula_seconds_excluding_context": eval_result["formula_evaluation_seconds"] / len(formula_results) if formula_results else None,
        "peak_memory_mb": peak_memory_mb(),
        "run_output_mb": disk_mb(run_dir),
        "tmp_residual_count": len(list((run_dir / "tmp").glob("*"))) if (run_dir / "tmp").exists() else 0,
        "detail_directory_count": len(list((run_dir / "details").glob("*"))) if (run_dir / "details").exists() else 0,
    }
    output = {
        "run_id": run_id,
        "run_dir": str(run_dir),
        "source_candidate_freeze_verified": True,
        "freeze_audit": {
            "uniform_candidates": len(bundle.uniform),
            "position_logit_candidates": len(bundle.position),
            "global_unique_candidates": len(bundle.global_unique),
            "cross_searcher_overlap": bundle.overlap["cross_searcher_overlap_count"],
            "freeze_manifest_hash": bundle.manifest["freeze_manifest_hash"],
        },
        "validation_interval": [bt.start_date, bt.end_date],
        "warmup_interval": [warmup_start, bt.start_date],
        "validation_actual_read_range": {
            "bars_min_date": str(context.bars["trade_date"].min()),
            "bars_max_date": str(context.bars["trade_date"].max()),
            "calendar_min_date": str(context.calendar["trade_date"].min()),
            "calendar_max_date": str(context.calendar["trade_date"].max()),
        },
        "formula_generation_count": 0,
        "position_logit_update_count": 0,
        "uniform_update_count": 0,
        "global_unique_candidates_evaluated": len(formula_results),
        "validation_data_accessed": True,
        "blind_test_data_accessed": False,
        "formula_results": formula_results,
        "uniform_view_count": len(views["uniform"]),
        "position_logit_view_count": len(views["position_logit"]),
        "uniform_exclusive_count": len(views["uniform_exclusive"]),
        "position_logit_exclusive_count": len(views["position_logit_exclusive"]),
        "overlap_count": len(views["overlap"]),
        "aggregate_statistics": stats,
        "validation_searcher_conclusion": conclusion,
        "resume": eval_result,
        "performance": performance,
        "shortlist": shortlist,
        "eligible_blind_candidates": shortlist["shortlist_manifest"]["eligible_blind_candidates"],
        "frozen_blind_shortlist_count": shortlist["shortlist_manifest"]["frozen_blind_shortlist_count"],
        "blind_shortlist_frozen": shortlist["shortlist_manifest"]["blind_shortlist_frozen"],
        "ready_for_blind_test": shortlist["shortlist_manifest"]["frozen_blind_shortlist_count"] > 0 and len(formula_results) == 31,
    }
    atomic_write_json(run_dir / "context_manifest.json", {"context_hash": context.context_hash, "config": bt.__dict__, "profile": context.profile, "validation_loaded": True, "blind_test_loaded": False})
    atomic_write_json(run_dir / "formula_results.json", formula_results)
    atomic_write_json(run_dir / "uniform_view.json", views["uniform"])
    atomic_write_json(run_dir / "position_logit_view.json", views["position_logit"])
    atomic_write_json(run_dir / "exclusive_comparison.json", {"uniform_exclusive": views["uniform_exclusive"], "position_logit_exclusive": views["position_logit_exclusive"]})
    atomic_write_json(run_dir / "overlap_results.json", views["overlap"])
    atomic_write_json(run_dir / "aggregate_statistics.json", stats)
    atomic_write_json(run_dir / "performance.json", performance)
    atomic_write_json(run_dir / "validation_results_hash.json", {"validation_results_hash": validation_results_hash})
    (run_dir / "report.md").write_text(stage3_6d3_markdown(output), encoding="utf-8")
    docs_dir = repo_root / "docs"
    atomic_write_json(docs_dir / "stage3_6d3_frozen_candidate_validation.json", output)
    (docs_dir / "stage3_6d3_frozen_candidate_validation.md").write_text(stage3_6d3_markdown(output), encoding="utf-8")
    return output


def stage3_6d3_markdown(output: dict) -> str:
    lines = ["# Stage 3.6D-3 Frozen Candidate Validation\n"]
    lines.append("Validation was run only for the frozen global unique candidates. Blind test was not accessed.\n")
    lines.append(f"\nrun_id: `{output['run_id']}`\n")
    lines.append(f"run_dir: `{output['run_dir']}`\n")
    lines.append(f"source_candidate_freeze_verified: `{output['source_candidate_freeze_verified']}`\n")
    lines.append(f"global_unique_candidates_evaluated: `{output['global_unique_candidates_evaluated']}`\n")
    lines.append(f"validation_interval: `{output['validation_interval']}`\n")
    lines.append(f"warmup_interval: `{output['warmup_interval']}`\n")
    lines.append(f"validation_searcher_conclusion: `{output['validation_searcher_conclusion']}`\n")
    lines.append(f"eligible_blind_candidates: `{output['eligible_blind_candidates']}`\n")
    lines.append(f"frozen_blind_shortlist_count: `{output['frozen_blind_shortlist_count']}`\n")
    lines.append(f"ready_for_blind_test: `{output['ready_for_blind_test']}`\n")
    lines.append(f"validation_data_accessed: `{output['validation_data_accessed']}`\n")
    lines.append(f"blind_test_data_accessed: `{output['blind_test_data_accessed']}`\n")
    lines.append("\n## Full Candidate Views\n")
    for key in ["uniform_full", "position_logit_full", "uniform_exclusive", "position_logit_exclusive", "overlap"]:
        stats = output["aggregate_statistics"][key]
        lines.append(f"- {key}: median={stats['validation_sortino_median']} top10={stats['validation_top_10_mean']} positive_ratio={stats['validation_positive_ratio']} available_ratio={stats['validation_sortino_available_ratio']}\n")
    return "".join(lines)
