from ashare_research.mining.checkpoint import load_checkpoint, save_checkpoint
from ashare_research.mining.model import AlphaGPTLite


def test_checkpoint_round_trip_validates_hashes(tmp_path) -> None:
    model = AlphaGPTLite(seed=7)
    path = tmp_path / "checkpoint.json"

    state_hash = save_checkpoint(
        path,
        run_id="run1",
        iteration=2,
        model=model,
        metadata={"config_hash": "cfg", "data_snapshot_hash": "data"},
    )
    iteration, restored, meta = load_checkpoint(path, run_id="run1", config_hash="cfg", data_snapshot_hash="data")

    assert iteration == 2
    assert restored.state_hash() == state_hash
    assert meta["config_hash"] == "cfg"
