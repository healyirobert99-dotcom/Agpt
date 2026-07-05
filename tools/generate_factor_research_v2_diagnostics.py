from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _read_config_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _load_rows_by_hash(path: Path) -> dict[str, dict[str, Any]]:
    return {str(row.get("formula_hash")): row for row in _read_jsonl(path)}


def _specific_reason(full_row: dict[str, Any], robust_row: dict[str, Any] | None) -> str:
    metrics = full_row.get("metrics") or {}
    if metrics.get("total_return") is not None and float(metrics["total_return"]) < 0:
        return "\u6210\u672c\u540e\u603b\u6536\u76ca\u4e3a\u8d1f"
    if robust_row and robust_row.get("robustness_status") not in {None, "passed"}:
        return "\u7a33\u5065\u6027\u672a\u901a\u8fc7"
    if full_row.get("failure_reason"):
        return str(full_row["failure_reason"])
    return "\u901a\u8fc7"


def generate_diagnostics(run_dir: str | Path, output_root: str | Path | None = None) -> dict[str, Any]:
    run_dir = Path(run_dir)
    diagnostics_dir = run_dir / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)

    config_text = _read_config_text(run_dir / "run_config.yaml")
    fast_rules_loaded = "fast_screen:" in config_text and "thresholds:" in config_text
    time_split_effective = (
        "split:" in config_text
        and "development:" in config_text
        and "selection:" in config_text
        and "stability:" in config_text
    )

    full_rows = _read_jsonl(run_dir / "full_backtest_results.jsonl")
    robust_by_hash = _load_rows_by_hash(run_dir / "robustness_results.jsonl")
    registry_rows = _read_jsonl(run_dir / "factor_registry_updates.jsonl")

    registry_by_hash = {str(row.get("formula_hash")): row for row in registry_rows}
    rating_recompute_equal = True
    csv_rows: list[dict[str, Any]] = []
    for row in full_rows:
        formula_hash = str(row.get("formula_hash"))
        metrics = row.get("metrics") or {}
        reason = _specific_reason(row, robust_by_hash.get(formula_hash))
        registry_grade = registry_by_hash.get(formula_hash, {}).get("grade")
        if registry_grade == "Rejected" and reason == "\u901a\u8fc7":
            rating_recompute_equal = False
        csv_rows.append(
            {
                "formula_hash": formula_hash,
                "canonical_formula": row.get("canonical_formula"),
                "total_return": metrics.get("total_return"),
                "max_drawdown": metrics.get("max_drawdown"),
                "diagnostic_reason": reason,
            }
        )

    csv_path = diagnostics_dir / "full_backtest_50_factors.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=["formula_hash", "canonical_formula", "total_return", "max_drawdown", "diagnostic_reason"],
        )
        writer.writeheader()
        writer.writerows(csv_rows)

    report_path = run_dir / "research_diagnostic_report.md"
    report_path.write_text(
        "\n".join(
            [
                "# Factor Research V2 Diagnostic Report",
                "",
                f"- fast_screen_rules_loaded: {str(fast_rules_loaded).lower()}",
                f"- time_split_effective: {str(time_split_effective).lower()}",
                f"- rating_recompute_equal: {str(rating_recompute_equal).lower()}",
                "",
                "## Specific Reasons",
                *[f"- {row['formula_hash']}: {row['diagnostic_reason']}" for row in csv_rows],
            ]
        ),
        encoding="utf-8",
    )

    return {
        "grades": {"rating_recompute_equal": rating_recompute_equal},
        "time_split": {"effective": False},
        "fast_screen": {"rules_loaded": fast_rules_loaded},
        "diagnostics_dir": str(diagnostics_dir),
    }
