from ashare_research.mining.model import AlphaGPTLite
from ashare_research.registry.artifacts import stable_hash


def test_blind_test_result_does_not_update_model_state() -> None:
    model = AlphaGPTLite(seed=1)
    before = model.state_hash()
    _blind_metrics = {"formula_hash": "a", "dataset_split": "blind_test", "reward": -10.0}

    assert model.state_hash() == before


def test_blind_shortlist_is_frozen_before_results() -> None:
    shortlist = [{"formula_hash": "a", "formula_text": "RET1"}]
    shortlist_hash = stable_hash(shortlist)
    blind_results = [{"formula_hash": "a", "reward": -1.0}]

    assert stable_hash(shortlist) == shortlist_hash
    assert stable_hash(blind_results) != shortlist_hash
