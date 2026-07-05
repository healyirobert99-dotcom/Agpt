from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from ashare_research.backtest.engine import BacktestConfig, DeterministicBacktestEngine
from ashare_research.factors.expression import Expression, parse_formula_text
from ashare_research.registry.artifacts import stable_hash


GOLDEN_FORMULAS = (
    "RET1",
    "RET5",
    "VOL_RATIO20",
    "TREND60",
    "ADD(RET1,VOL_RATIO20)",
    "SUB(RET5,TREND60)",
    "DECAY_LINEAR20(RET1)",
    "ZSCORE20(RET5)",
)


@dataclass(frozen=True)
class GoldenRunResult:
    formula_text: str
    formula_hash: str
    status: str
    failure_reason: str | None
    run_dir: str | None
    metrics: dict
    elapsed_seconds: float
    file_hashes: dict[str, str]


def stable_csv_hash(path: Path, sort_columns: list[str] | None = None) -> str:
    if path.exists() and path.stat().st_size > 0 and path.suffix == ".csv":
        df = pd.read_csv(path)
        if sort_columns:
            present = [col for col in sort_columns if col in df.columns]
            if present:
                df = df.sort_values(present, kind="mergesort").reset_index(drop=True)
        payload = df.to_csv(index=False, float_format="%.17g")
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()
    if path.exists():
        return hashlib.sha256(path.read_bytes()).hexdigest()
    return ""


def hash_backtest_outputs(run_dir: Path) -> dict[str, str]:
    return {
        "planned_orders": stable_csv_hash(run_dir / "planned_orders.csv", ["signal_date", "planned_trade_date", "ts_code", "side"]),
        "executions": stable_csv_hash(run_dir / "executions.csv", ["actual_trade_date", "ts_code", "side"]),
        "daily_holdings": stable_csv_hash(run_dir / "daily_holdings.csv", ["trade_date", "ts_code"]),
        "daily_account": stable_csv_hash(run_dir / "daily_account.csv", ["trade_date"]),
        "metrics": stable_csv_hash(run_dir / "metrics.json"),
        "report": stable_csv_hash(run_dir / "report.md"),
    }


def current_git_commit(repo_root: Path) -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo_root, text=True).strip()
    except Exception:
        return "unknown"


def run_golden_baseline(
    *,
    provider,
    config: BacktestConfig,
    repo_root: Path,
    output_root: Path,
    config_snapshot_text: str,
    data_snapshot_hash: str,
    formulas: tuple[str, ...] = GOLDEN_FORMULAS,
) -> dict:
    if output_root.exists():
        raise FileExistsError(output_root)
    output_root.mkdir(parents=True)
    manifest = {
        "created_at_unix": time.time(),
        "git_commit": current_git_commit(repo_root),
        "data_snapshot_hash": data_snapshot_hash,
        "backtest_config_hash": stable_hash(config.__dict__),
        "feature_version": "phase1_base_features_v1",
        "operator_version": "phase1_operator_vocab_v1",
        "universe_version": "csi800_asof_from_b_ready",
        "tradability_rule_version": "b_ready_derived_tradability_and_limit_price",
        "price_policy_version": "signal_close_execution_next_raw_open",
        "floating_tolerance": 1e-9,
        "sorting_rules": {
            "dates": "ascending",
            "ts_code": "ascending",
            "factor_tie_break": "factor desc then ts_code asc using mergesort",
            "nan_factor": "dropped before ranking",
        },
        "rounding_rules": {
            "buy_lot": "floor target quantity to 100 shares",
            "cost": "executed_notional * bps / 10000 without extra rounding",
            "limit_price_epsilon": "tick_size / 2",
        },
    }
    (output_root / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    (output_root / "config_snapshot.yaml").write_text(config_snapshot_text, encoding="utf-8")
    formula_rows = []
    results = []
    for formula_text in formulas:
        start = time.perf_counter()
        try:
            expr = parse_formula_text(formula_text)
            valid, reason = expr.validate()
            if not valid:
                raise ValueError(reason)
            run_config = BacktestConfig(**{**config.__dict__, "runs_dir": str(output_root / "formula_runs"), "temp_dir": str(output_root / "tmp")})
            result = DeterministicBacktestEngine(provider, run_config).run(expr)
            src = Path(result["run_dir"])
            dst = output_root / "formulas" / expr.sha256()
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))
            hashes = hash_backtest_outputs(dst)
            status = "completed"
            failure_reason = None
            metrics = result["metrics"]
            run_dir = str(dst)
        except Exception as exc:  # noqa: BLE001
            expr = Expression((formula_text,))
            status = "failed"
            failure_reason = str(exc)
            metrics = {"status": "failed", "failure_reason": failure_reason}
            hashes = {}
            run_dir = None
        elapsed = time.perf_counter() - start
        formula_hash = parse_formula_text(formula_text).sha256() if status == "completed" else hashlib.sha256(formula_text.encode("utf-8")).hexdigest()
        row = GoldenRunResult(formula_text, formula_hash, status, failure_reason, run_dir, metrics, elapsed, hashes)
        results.append(row)
        formula_rows.append(row.__dict__)
    (output_root / "formula_manifest.json").write_text(json.dumps(formula_rows, ensure_ascii=False, indent=2, sort_keys=True, default=str), encoding="utf-8")
    all_hashes = {row.formula_hash: row.file_hashes for row in results}
    (output_root / "file_hashes.json").write_text(json.dumps(all_hashes, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return {"manifest": manifest, "formulas": formula_rows, "file_hashes": all_hashes}
