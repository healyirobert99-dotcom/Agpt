from __future__ import annotations

import argparse
import json
from pathlib import Path

from .config import load_simple_yaml
from .backtest.engine import BacktestConfig, DeterministicBacktestEngine
from .data.local_sqlite_provider import LocalSQLiteProvider
from .factors.base_features import compute_base_features, robust_cross_sectional_standardize
from .factors.executor import FormulaExecutor
from .factors.expression import Expression, parse_formula_text
from .orchestrator import ResearchOrchestrator
from .registry.database import ResearchRegistry
from .mining.stage3_6 import run_search_benchmark
from .mining.stage3_6c2 import WARNING_LINES, run_completed_budget_gate
from .mining.stage3_6c2r import WARNING_LINES as DAILY_BAR_DIAG_WARNINGS
from .mining.stage3_6c2r import run_daily_bar_diagnosis
from .mining.stage3_6d3 import run_frozen_candidate_validation
from .mining.forward_paper_runner import run_forward_paper_once
from .factor_research_v2.pipeline import resume_pipeline as resume_factor_research_v2
from .factor_research_v2.pipeline import run_pipeline as run_factor_research_v2


REPO_ROOT = Path(__file__).resolve().parents[1]


def smoke_test(config_path: str) -> int:
    cfg = load_simple_yaml(config_path)
    data_cfg = cfg["data"]
    feat_cfg = cfg.get("features", {})
    smoke_cfg = cfg.get("smoke", {})
    provider = LocalSQLiteProvider(
        REPO_ROOT / data_cfg["sqlite_path"],
        REPO_ROOT / data_cfg.get("raw_sqlite_path", "stock-data/a_stock_selector.sqlite3"),
    )
    if data_cfg.get("allow_network", False):
        raise ValueError("Smoke test requires allow_network=false")

    symbols = smoke_cfg.get("symbols")
    bars = provider.get_daily_bars(smoke_cfg["start_date"], smoke_cfg["end_date"], symbols=symbols)
    constituents = provider.get_index_constituents("CSI800", smoke_cfg["start_date"], smoke_cfg["end_date"])
    member_keys = set(zip(constituents["effective_trade_date"], constituents["ts_code"]))
    bars = bars[[((d, s) in member_keys) for d, s in zip(bars["trade_date"], bars["ts_code"])]].copy()
    features = compute_base_features(bars, price_col=feat_cfg.get("calculation_price_column", "close"))
    standardized = robust_cross_sectional_standardize(features, min_count=int(smoke_cfg.get("min_cross_section", 2)))
    merged = features.merge(standardized, on=["trade_date", "ts_code"], how="left")
    expr = Expression(tuple(smoke_cfg.get("formula_tokens", ["ADD", "RET1", "VOL_RATIO20"])))
    result = FormulaExecutor(min_valid_rows=int(smoke_cfg.get("min_valid_rows", 5))).execute(expr, features)
    print("ENGINEERING SMOKE TEST ONLY")
    print("NOT A VALIDATED INVESTMENT FACTOR")
    print(json.dumps(result.summary(), ensure_ascii=False, indent=2))
    print(f"rows={len(bars)} feature_rows={len(features)} standardized_rows={len(merged)}")
    return 0 if result.valid else 1


def run_backtest(config_path: str, formula_text: str) -> int:
    cfg = load_simple_yaml(config_path)
    data_cfg = cfg["data"]
    if data_cfg.get("allow_network", False):
        raise ValueError("Backtest requires allow_network=false")
    if cfg.get("test_only") is not True:
        raise ValueError("Backtest config must explicitly set test_only: true")

    provider = LocalSQLiteProvider(
        REPO_ROOT / data_cfg["sqlite_path"],
        REPO_ROOT / data_cfg.get("raw_sqlite_path", "stock-data/a_stock_selector.sqlite3"),
    )
    bt_config = BacktestConfig.from_dict(cfg)
    expr = parse_formula_text(formula_text)
    valid, reason = expr.validate()
    if not valid:
        raise ValueError(f"invalid_formula:{reason}")

    result = DeterministicBacktestEngine(provider, bt_config).run(expr)
    print("ENGINEERING BACKTEST ONLY")
    print("NOT A VALIDATED INVESTMENT STRATEGY")
    print("B-READY DATA WITH APPROXIMATE TRADABILITY")
    print(json.dumps({"run_id": result["run_id"], "run_dir": result["run_dir"], "metrics": result["metrics"], "benchmark": result["benchmark"]}, ensure_ascii=False, indent=2))
    return 0


def run_mining(config_path: str) -> int:
    result = ResearchOrchestrator(config_path, REPO_ROOT).run()
    print("ENGINEERING MINING TEST ONLY")
    print("NOT A VALIDATED INVESTMENT STRATEGY")
    print("B-READY DATA WITH APPROXIMATE TRADABILITY")
    print("BLIND TEST RESULTS MUST NOT BE USED FOR RETRAINING")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def mining_status(run_id: str) -> int:
    registry = ResearchRegistry(REPO_ROOT / "runs/research_registry.sqlite3")
    status = registry.status(run_id)
    print(json.dumps(status or {"run_id": run_id, "status": "not_found"}, ensure_ascii=False, indent=2))
    return 0 if status else 1


def resume_training(run_id: str) -> int:
    registry = ResearchRegistry(REPO_ROOT / "runs/research_registry.sqlite3")
    status = registry.status(run_id)
    if not status:
        raise ValueError(f"unknown_run_id:{run_id}")
    if status["status"] in {"complete", "validation", "blind_test", "blind_test_complete"}:
        raise ValueError(f"run_not_resumable:{status['status']}")
    if status["status"] != "training_interrupted":
        raise ValueError(f"run_not_training_interrupted:{status['status']}")
    print(json.dumps({"run_id": run_id, "status": "training_interrupted", "model_checkpoint": status["model_checkpoint"], "resume_allowed": True}, ensure_ascii=False, indent=2))
    return 0


def mining_report(run_id: str) -> int:
    path = REPO_ROOT / "runs" / run_id / "report.md"
    if not path.exists():
        raise FileNotFoundError(path)
    print(path.read_text(encoding="utf-8"))
    return 0


def search_benchmark(config_path: str) -> int:
    result = run_search_benchmark(config_path, REPO_ROOT)
    print("ENGINEERING SEARCH BENCHMARK ONLY")
    print("NOT A VALIDATED INVESTMENT STRATEGY")
    print("B-READY DATA WITH APPROXIMATE TRADABILITY")
    print(json.dumps({"run_id": result["run_id"], "run_dir": result["run_dir"], "conclusion": result["conclusion"], "pytorch_route_decision": result["pytorch_route_decision"]}, ensure_ascii=False, indent=2))
    return 0


def completed_budget_gate(config_path: str) -> int:
    result = run_completed_budget_gate(config_path, REPO_ROOT)
    for line in WARNING_LINES:
        print(line)
    print(
        json.dumps(
            {
                "run_id": result["run_id"],
                "run_dir": result["run_dir"],
                "completed_full_backtest_count": result["budget_summary"]["completed_full_backtest_count"],
                "completed_budget_gate_passed": result["completed_budget_gate_passed"],
                "shared_context_safe_for_generator_comparison": result["shared_context_safe_for_generator_comparison"],
                "ready_for_searcher_comparison": result["ready_for_searcher_comparison"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def diagnose_daily_bars(config_path: str, batch_size: int) -> int:
    result = run_daily_bar_diagnosis(config_path, REPO_ROOT, batch_size=batch_size)
    for line in DAILY_BAR_DIAG_WARNINGS:
        print(line)
    print(
        json.dumps(
            {
                "run_id": result["run_id"],
                "run_dir": result["run_dir"],
                "rows": result["fetchmany_probe"]["rows"],
                "first_batch_seconds": result["fetchmany_probe"]["first_batch_seconds"],
                "elapsed_seconds": result["fetchmany_probe"]["elapsed_seconds"],
                "uses_index": result["diagnosis"]["uses_index"],
                "uses_temp_btree_sort": result["diagnosis"]["uses_temp_btree_sort"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def frozen_candidate_validation(config_path: str) -> int:
    result = run_frozen_candidate_validation(config_path, REPO_ROOT)
    print("ENGINEERING FROZEN-CANDIDATE VALIDATION ONLY")
    print("NOT A BLIND TEST")
    print("NOT A VALIDATED INVESTMENT STRATEGY")
    print(
        json.dumps(
            {
                "run_id": result["run_id"],
                "run_dir": result["run_dir"],
                "source_candidate_freeze_verified": result["source_candidate_freeze_verified"],
                "global_unique_candidates_evaluated": result["global_unique_candidates_evaluated"],
                "validation_searcher_conclusion": result["validation_searcher_conclusion"],
                "frozen_blind_shortlist_count": result["frozen_blind_shortlist_count"],
                "ready_for_blind_test": result["ready_for_blind_test"],
                "blind_test_data_accessed": result["blind_test_data_accessed"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def forward_paper(config_path: str) -> int:
    result = run_forward_paper_once(config_path, REPO_ROOT)
    print("B-v1.0 FORWARD PAPER TRACKING")
    print("NO BACKFILL")
    print("NO BLIND TEST")
    print("NO REAL TRADING")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def factor_research_v2(action: str, config_path: str, run_dir: str | None = None) -> int:
    if action == "run":
        result = run_factor_research_v2(config_path, REPO_ROOT)
        print("FACTOR RESEARCH V2 MVP")
        print("HISTORICAL_RESEARCH_RESULT ONLY")
        print(json.dumps({"run_id": result["run_id"], "run_dir": result["run_dir"], "counts": result["counts"]}, ensure_ascii=False, indent=2))
        return 0
    if action == "status":
        roots = [REPO_ROOT / "runs"]
        import os
        if os.environ.get("ALPHAGPT_RUNS_ROOT"):
            roots.append(Path(os.environ["ALPHAGPT_RUNS_ROOT"]))
        runs = sorted(p for root in roots if root.exists() for p in root.glob("factor_research_v2_*"))
        latest = str(runs[-1]) if runs else None
        print(json.dumps({"latest_run_dir": latest}, ensure_ascii=False, indent=2))
        return 0
    if action == "resume":
        if not run_dir:
            raise ValueError("factor_research_v2_resume_requires_run_dir")
        result = resume_factor_research_v2(run_dir, REPO_ROOT)
        print(json.dumps({
            "resume_status": result.get("resume_status", "resumed"),
            "run_id": result["run_id"],
            "run_dir": result["run_dir"],
            "new_run_created": result.get("new_run_created", False),
            "recomputed_item_count": result.get("recomputed_item_count", 0),
            "new_registry_event_count": result.get("new_registry_event_count", result.get("registry_append_result", {}).get("appended", 0)),
            "registry_duplicate_count": result.get("registry_duplicate_count", 0),
        }, ensure_ascii=False, indent=2))
        return 0
    if action in {"prepare", "generate", "screen", "backtest", "robustness", "report"}:
        print(json.dumps({"action": action, "status": "use_run_for_mvp_pipeline"}, ensure_ascii=False, indent=2))
        return 0
    raise ValueError(f"unknown_factor_research_v2_action:{action}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ashare_research")
    sub = parser.add_subparsers(dest="cmd", required=True)
    smoke = sub.add_parser("smoke-test")
    smoke.add_argument("--config", required=True)
    backtest = sub.add_parser("backtest")
    backtest.add_argument("--config", required=True)
    backtest.add_argument("--formula", required=True)
    mine = sub.add_parser("mine")
    mine.add_argument("--config", required=True)
    resume = sub.add_parser("resume")
    resume.add_argument("--run-id", required=True)
    resume_training_parser = sub.add_parser("resume-training")
    resume_training_parser.add_argument("--run-id", required=True)
    status = sub.add_parser("status")
    status.add_argument("--run-id", required=True)
    report = sub.add_parser("report")
    report.add_argument("--run-id", required=True)
    bench = sub.add_parser("search-benchmark")
    bench.add_argument("--config", required=True)
    gate = sub.add_parser("completed-budget-gate")
    gate.add_argument("--config", required=True)
    daily_diag = sub.add_parser("diagnose-daily-bars")
    daily_diag.add_argument("--config", required=True)
    daily_diag.add_argument("--batch-size", type=int, default=10000)
    frozen_val = sub.add_parser("frozen-candidate-validation")
    frozen_val.add_argument("--config", required=True)
    forward = sub.add_parser("forward-paper")
    forward.add_argument("--config", required=True)
    fr2 = sub.add_parser("factor-research-v2")
    fr2.add_argument("action", choices=["prepare", "generate", "screen", "backtest", "robustness", "report", "run", "resume", "status"])
    fr2.add_argument("--config", default="config/factor_research_v2.yaml")
    fr2.add_argument("--run-dir")
    args = parser.parse_args(argv)
    if args.cmd == "smoke-test":
        return smoke_test(args.config)
    if args.cmd == "backtest":
        return run_backtest(args.config, args.formula)
    if args.cmd == "mine":
        return run_mining(args.config)
    if args.cmd == "resume":
        return mining_status(args.run_id)
    if args.cmd == "resume-training":
        return resume_training(args.run_id)
    if args.cmd == "status":
        return mining_status(args.run_id)
    if args.cmd == "report":
        return mining_report(args.run_id)
    if args.cmd == "search-benchmark":
        return search_benchmark(args.config)
    if args.cmd == "completed-budget-gate":
        return completed_budget_gate(args.config)
    if args.cmd == "diagnose-daily-bars":
        return diagnose_daily_bars(args.config, args.batch_size)
    if args.cmd == "frozen-candidate-validation":
        return frozen_candidate_validation(args.config)
    if args.cmd == "forward-paper":
        return forward_paper(args.config)
    if args.cmd == "factor-research-v2":
        return factor_research_v2(args.action, args.config, args.run_dir)
    raise ValueError(args.cmd)


if __name__ == "__main__":
    raise SystemExit(main())
