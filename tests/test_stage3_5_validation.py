from pathlib import Path

import pytest

from ashare_research.factors.expression import Expression
from ashare_research.mining.checkpoint import load_checkpoint, save_checkpoint
from ashare_research.mining.model import AlphaGPTLite, GeneratedFormula
from ashare_research.mining.stage3_5 import evaluate_on_synthetic
from ashare_research.mining.trainer import ReinforceTrainer


def test_synthetic_market_target_formula_has_advantage(tmp_path: Path) -> None:
    target = evaluate_on_synthetic(Expression(("RET1",)), tmp_path / "target")
    baseline = evaluate_on_synthetic(Expression(("RET5",)), tmp_path / "baseline")

    assert target["trade_count"] >= 1
    assert baseline["trade_count"] >= 1
    assert target["sortino"] is not None
    assert baseline["sortino"] is not None
    assert target["sortino"] > baseline["sortino"]


def test_constant_or_failed_reward_batch_skips_update() -> None:
    model = AlphaGPTLite(seed=0)
    trainer = ReinforceTrainer(model)
    before = model.state_hash()
    generated = GeneratedFormula(Expression(("RET1",)), [])

    reason = trainer.update_batch([(generated, -1.0), (generated, -1.0)])

    assert reason == "constant_or_invalid_rewards"
    assert trainer.update_count == 0
    assert model.state_hash() == before


def test_model_update_increases_target_probability_for_controlled_reward() -> None:
    model = AlphaGPTLite(seed=0, learning_rate=0.2)
    trainer = ReinforceTrainer(model)
    target = GeneratedFormula(Expression(("RET1",)), [])
    baseline = GeneratedFormula(Expression(("RET5",)), [])
    before = model.formula_probability(target.expression.tokens)

    for _ in range(20):
        trainer.update_batch([(target, 1.0), (baseline, -0.5)])

    assert model.formula_probability(target.expression.tokens) > before


def test_checkpoint_resume_matches_continuous_training(tmp_path: Path) -> None:
    target = GeneratedFormula(Expression(("RET1",)), [])
    baseline = GeneratedFormula(Expression(("RET5",)), [])
    continuous = AlphaGPTLite(seed=4, learning_rate=0.2)
    continuous_trainer = ReinforceTrainer(continuous)
    for _ in range(10):
        continuous_trainer.update_batch([(target, 1.0), (baseline, -0.5)])

    interrupted = AlphaGPTLite(seed=4, learning_rate=0.2)
    interrupted_trainer = ReinforceTrainer(interrupted)
    for _ in range(5):
        interrupted_trainer.update_batch([(target, 1.0), (baseline, -0.5)])
    ckpt = tmp_path / "checkpoint.json"
    save_checkpoint(ckpt, run_id="run", iteration=5, model=interrupted, metadata={"config_hash": "cfg", "data_snapshot_hash": "data"})
    _, resumed, _ = load_checkpoint(ckpt, run_id="run", config_hash="cfg", data_snapshot_hash="data")
    resumed_trainer = ReinforceTrainer(resumed)
    for _ in range(5):
        resumed_trainer.update_batch([(target, 1.0), (baseline, -0.5)])

    assert resumed.state_hash() == continuous.state_hash()


def test_more_than_100_formulas_have_dedup_cache_statistics() -> None:
    model = AlphaGPTLite(seed=11)
    hashes = []
    for _ in range(120):
        hashes.append(model.generate().expression.sha256())

    assert len(hashes) == 120
    assert len(set(hashes)) < len(hashes)
    assert len(set(hashes)) > 50
