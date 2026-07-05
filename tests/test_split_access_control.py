from ashare_research.backtest.engine import BacktestConfig
from ashare_research.validation.blind_test_evaluator import BlindTestEvaluator
from ashare_research.validation.train_evaluator import TrainEvaluator
from ashare_research.validation.validation_evaluator import ValidationEvaluator


def _base_config() -> BacktestConfig:
    return BacktestConfig(
        start_date="19000101",
        end_date="19000102",
        rebalance_frequency=20,
        top_n=3,
        initial_cash=1000000,
        cost_bps=20,
        unknown_tradability_policy="reject_trade",
        min_free_space_gb=0,
    )


def test_evaluators_only_receive_their_split_dates() -> None:
    train = TrainEvaluator(None, _base_config(), ("20240101", "20240131"), 1)
    validation = ValidationEvaluator(None, _base_config(), ("20240201", "20240229"), 1)
    blind = BlindTestEvaluator(None, _base_config(), ("20240301", "20240329"), 1)

    assert (train.config.start_date, train.config.end_date) == ("20240101", "20240131")
    assert (validation.config.start_date, validation.config.end_date) == ("20240201", "20240229")
    assert (blind.config.start_date, blind.config.end_date) == ("20240301", "20240329")
