import numpy as np
import pandas as pd

from ashare_research.factors.base_features import BASE_FEATURES, compute_base_features
from ashare_research.factors.executor import FormulaExecutor
from ashare_research.factors.expression import Expression, parse_formula_text
from ashare_research.factors.operators import OPERATORS
from ashare_research.factors.vocabulary import TOKENS


def feature_frame() -> pd.DataFrame:
    rows = []
    for code, base in [("A", 20.0), ("B", 40.0)]:
        for i in range(130):
            close = base + i + (4.0 if i % 6 < 3 else -4.0)
            rows.append({"trade_date": f"2024{i+1:04d}", "ts_code": code, "close": close, "volume": 100 + i, "amount": (100 + i) * close})
    return compute_base_features(pd.DataFrame(rows))


def test_operator_registry_exact_set() -> None:
    assert set(OPERATORS) == {"ADD", "SUB", "MUL", "DIV", "NEG", "ABS", "SIGN", "DELTA5", "DECAY_LINEAR20", "ZSCORE20"}
    assert OPERATORS["DIV"].arity == 2
    assert OPERATORS["DELTA5"].required_history == 5


def test_expression_validation_hash_and_dedup() -> None:
    expr = Expression(("ADD", "RET1", "VOL_RATIO20"))
    assert expr.validate() == (True, None)
    assert expr.to_string() == "ADD(RET1,VOL_RATIO20)"
    assert expr.sha256() == Expression(("ADD", "RET1", "VOL_RATIO20")).sha256()
    assert Expression(("ADD", "RET1")).validate()[0] is False
    assert Expression(("NEG", "ABS", "SIGN", "RET1", "RET5", "VOL_RATIO20", "TREND60", "RET1", "RET5")).validate()[1] == "formula_too_long"


def test_parse_formula_text_for_cli() -> None:
    expr = parse_formula_text("ADD(RET1,VOL_RATIO20)")

    assert expr.tokens == ("ADD", "RET1", "VOL_RATIO20")
    assert expr.to_string() == "ADD(RET1,VOL_RATIO20)"


def test_executor_valid_and_invalid_formulas() -> None:
    feats = feature_frame()
    ok = FormulaExecutor(min_valid_rows=10).execute(Expression(("ADD", "RET1", "VOL_RATIO20")), feats)
    assert ok.valid, ok.summary()
    const = FormulaExecutor(min_valid_rows=10).execute(Expression(("SUB", "RET1", "RET1")), feats)
    assert not const.valid
    assert const.failure_reason == "constant_or_all_missing"


def test_second_batch_features_are_tokens_and_executable() -> None:
    second_batch = {
        "RET20",
        "RET60",
        "RET120",
        "RET_STD20",
        "RET_STD60",
        "DOWNSIDE_RET_STD20",
        "DOWNSIDE_RET_STD60",
        "AMOUNT_MA20",
        "AMOUNT_MA60",
        "TREND20",
        "TREND120",
    }
    assert second_batch <= set(BASE_FEATURES)
    assert second_batch <= set(TOKENS)
    feats = feature_frame()
    for name in second_batch:
        result = FormulaExecutor(min_valid_rows=10).execute(Expression((name,)), feats)
        assert result.valid, result.summary()


def test_executor_requires_only_formula_feature_dependencies() -> None:
    feats = feature_frame()[["trade_date", "ts_code", "RET1"]]
    result = FormulaExecutor(min_valid_rows=10).execute(Expression(("RET1",)), feats)
    assert result.valid, result.summary()
    missing = FormulaExecutor(min_valid_rows=10).execute(Expression(("RET20",)), feats)
    assert not missing.valid
    assert "RET20" in str(missing.failure_reason)
