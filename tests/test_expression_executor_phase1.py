import numpy as np
import pandas as pd

from ashare_research.factors.base_features import compute_base_features
from ashare_research.factors.executor import FormulaExecutor
from ashare_research.factors.expression import Expression, parse_formula_text
from ashare_research.factors.operators import OPERATORS


def feature_frame() -> pd.DataFrame:
    rows = []
    for code, base in [("A", 10.0), ("B", 20.0)]:
        for i in range(80):
            rows.append({"trade_date": f"202402{i+1:02d}", "ts_code": code, "close": base + i, "volume": 100 + i})
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
