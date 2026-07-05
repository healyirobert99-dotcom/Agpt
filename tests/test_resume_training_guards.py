import pytest

from ashare_research import cli
from ashare_research.registry.database import ResearchRegistry


def test_completed_run_cannot_resume_training(tmp_path, monkeypatch) -> None:
    registry = ResearchRegistry(tmp_path / "runs" / "research_registry.sqlite3")
    registry.upsert_run(
        run_id="done",
        status="complete",
        created_at="now",
        completed_at="later",
        git_commit="abc",
        config_hash="cfg",
        data_snapshot_hash="data",
        seed=1,
        current_iteration=1,
        model_checkpoint="checkpoint.json",
        error_message=None,
    )
    monkeypatch.setattr(cli, "REPO_ROOT", tmp_path)

    with pytest.raises(ValueError, match="run_not_resumable:complete"):
        cli.resume_training("done")
