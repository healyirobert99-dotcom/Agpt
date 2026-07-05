from pathlib import Path

import pandas as pd

from ashare_research.backtest.golden import hash_backtest_outputs, run_golden_baseline, stable_csv_hash
from ashare_research.mining.stage3_5 import SyntheticMomentumProvider, synthetic_backtest_config


def test_stable_csv_hash_is_order_independent_when_sorting(tmp_path: Path) -> None:
    a = tmp_path / "a.csv"
    b = tmp_path / "b.csv"
    pd.DataFrame([{"trade_date": "20240102", "ts_code": "B"}, {"trade_date": "20240101", "ts_code": "A"}]).to_csv(a, index=False)
    pd.DataFrame([{"trade_date": "20240101", "ts_code": "A"}, {"trade_date": "20240102", "ts_code": "B"}]).to_csv(b, index=False)

    assert stable_csv_hash(a, ["trade_date", "ts_code"]) == stable_csv_hash(b, ["trade_date", "ts_code"])


def test_hash_backtest_outputs_has_expected_keys(tmp_path: Path) -> None:
    for name in ["planned_orders.csv", "executions.csv", "daily_holdings.csv", "daily_account.csv"]:
        (tmp_path / name).write_text("trade_date,ts_code\n20240101,000001.SZ\n", encoding="utf-8")
    (tmp_path / "metrics.json").write_text("{}", encoding="utf-8")
    (tmp_path / "report.md").write_text("report", encoding="utf-8")

    hashes = hash_backtest_outputs(tmp_path)

    assert set(hashes) == {"planned_orders", "executions", "daily_holdings", "daily_account", "metrics", "report"}
    assert all(hashes.values())


def test_golden_baseline_manifest_and_formula_output(tmp_path: Path) -> None:
    provider = SyntheticMomentumProvider()
    config = synthetic_backtest_config(tmp_path / "bt")

    result = run_golden_baseline(
        provider=provider,
        config=config,
        repo_root=tmp_path,
        output_root=tmp_path / "golden",
        config_snapshot_text="test_only: true\n",
        data_snapshot_hash="synthetic",
        formulas=("RET1",),
    )

    assert (tmp_path / "golden" / "manifest.json").exists()
    assert (tmp_path / "golden" / "formula_manifest.json").exists()
    assert result["formulas"][0]["status"] == "completed"
    assert result["formulas"][0]["file_hashes"]["daily_account"]
