from ashare_research.registry.artifacts import stable_hash


def test_shortlist_hash_changes_if_frozen_list_changes() -> None:
    shortlist = [{"formula_hash": "a", "reward": 1.0}]
    frozen_hash = stable_hash(shortlist)

    changed = [{"formula_hash": "a", "reward": 1.0}, {"formula_hash": "b", "reward": 0.5}]

    assert stable_hash(changed) != frozen_hash
