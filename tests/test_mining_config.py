import pytest

from ashare_research.orchestrator import ResearchOrchestrator


def test_formal_mining_config_with_nulls_stops(tmp_path) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "b_ready_data_snapshot.json").write_text("{}", encoding="utf-8")
    cfg = tmp_path / "formal.yaml"
    cfg.write_text(
        """
test_only: false
research_split:
  train_start: null
backtest:
  rebalance_frequency: null
mining:
  batch_size: null
data:
  allow_network: false
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Missing formal research parameters"):
        ResearchOrchestrator(cfg, tmp_path).validate_config()
