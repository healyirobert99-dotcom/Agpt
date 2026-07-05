import json
from pathlib import Path

from ashare_research.orchestrator import ResearchOrchestrator


def test_smoke_orchestrator_freezes_candidates_and_blind_results(tmp_path, monkeypatch) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "b_ready_data_snapshot.json").write_text(json.dumps({"snapshot_hash": "snapshot"}), encoding="utf-8")
    config = tmp_path / "mining.yaml"
    config.write_text(
        """
test_only: true
data:
  sqlite_path: stock-data/ashare_research.sqlite3
  raw_sqlite_path: stock-data/a_stock_selector.sqlite3
  allow_network: false
research_split:
  train_start: "20240101"
  train_end: "20240131"
  validation_start: "20240201"
  validation_end: "20240229"
  blind_test_start: "20240301"
  blind_test_end: "20240329"
backtest:
  rebalance_frequency: 20
  top_n: 3
  initial_cash: 1000000
  one_way_cost_bps: 20
  unknown_tradability_policy: reject_trade
mining:
  seed: 0
  batch_size: 3
  max_iterations: 1
  candidate_pool_size: 2
  validation_shortlist_size: 1
  min_valid_rows: 10
  min_trade_count: 1
cost:
  sensitivity_one_way_bps: [10, 20, 40]
storage:
  min_free_space_gb: 0
  max_run_output_gb: 1
registry:
  path: runs/research_registry.sqlite3
output:
  runs_dir: runs
""",
        encoding="utf-8",
    )
    calls = []

    def fake_evaluate(self, provider, base_config, split, expr, split_name, cost_bps, cache):
        calls.append((expr.sha256(), split_name, cost_bps, split))
        reward = 1.0 if split_name == "train" else 0.5
        return {"sortino": reward, "trade_count": 2}, reward, ""

    monkeypatch.setattr(ResearchOrchestrator, "_evaluate_cached", fake_evaluate)

    result = ResearchOrchestrator(config, tmp_path).run()
    run_dir = Path(result["run_dir"])

    assert result["summary"]["model_update_count"] >= 0
    assert result["summary"]["update_skipped_count"] >= 0
    assert (run_dir / "train_candidates.parquet").exists()
    assert (run_dir / "validation_results.parquet").exists()
    assert (run_dir / "shortlist.json").exists()
    assert (run_dir / "blind_test_results.parquet").exists()
    assert any(c[1] == "train" for c in calls)
    assert any(c[1] == "validation" for c in calls)
    assert any(c[1] == "blind_test" for c in calls)
