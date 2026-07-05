from ashare_research.registry.database import ResearchRegistry


def test_registry_separates_runs_formulas_and_evaluations(tmp_path) -> None:
    db = ResearchRegistry(tmp_path / "registry.sqlite3")
    db.upsert_run(
        run_id="run1",
        status="running",
        created_at="now",
        completed_at=None,
        git_commit="abc",
        config_hash="cfg",
        data_snapshot_hash="data",
        seed=1,
        current_iteration=0,
        model_checkpoint=None,
        error_message=None,
    )
    db.insert_formula(
        formula_hash="hash1",
        formula_text="RET1",
        token_sequence=["RET1"],
        formula_length=1,
        syntax_valid=True,
        execution_valid=True,
        failure_reason=None,
        first_seen_run_id="run1",
    )
    db.insert_evaluation(run_id="run1", formula_hash="hash1", dataset_split="train", cost_bps=20, reward=1.0, metrics={"sortino": 1.0}, evaluated_at="now")
    db.insert_evaluation(run_id="run1", formula_hash="hash1", dataset_split="blind_test", cost_bps=20, reward=0.5, metrics={"sortino": 0.5}, evaluated_at="now")

    assert db.status("run1")["status"] == "running"
