from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .base_features import BASE_FEATURES
from .expression import Expression
from .operators import OPERATORS


@dataclass
class ExecutionResult:
    formula_hash: str
    formula_text: str
    valid: bool
    failure_reason: str | None
    values: pd.Series | None
    total_rows: int
    valid_rows: int
    nan_rows: int
    inf_rows: int
    unique_values: int
    standard_deviation: float

    def summary(self) -> dict[str, object]:
        return {
            "formula_hash": self.formula_hash,
            "formula_text": self.formula_text,
            "valid": self.valid,
            "failure_reason": self.failure_reason,
            "total_rows": self.total_rows,
            "valid_rows": self.valid_rows,
            "nan_rows": self.nan_rows,
            "inf_rows": self.inf_rows,
            "unique_values": self.unique_values,
            "standard_deviation": self.standard_deviation,
        }


class FormulaExecutor:
    def __init__(self, min_valid_rows: int = 20):
        self.min_valid_rows = min_valid_rows

    def execute(self, expression: Expression, features: pd.DataFrame) -> ExecutionResult:
        valid, reason = expression.validate()
        formula_text = expression.to_string() if valid else "Invalid"
        formula_hash = expression.sha256()
        total_rows = len(features)
        if not valid:
            return self._empty(formula_hash, formula_text, total_rows, reason)

        feature_dependencies = {token for token in expression.tokens if token in BASE_FEATURES}
        required = {"trade_date", "ts_code", *feature_dependencies}
        missing = required - set(features.columns)
        if missing:
            return self._empty(formula_hash, formula_text, total_rows, f"missing_columns:{sorted(missing)}")

        frame = features.sort_values(["ts_code", "trade_date"], kind="mergesort").copy()
        index = pd.MultiIndex.from_frame(frame[["ts_code", "trade_date"]])
        env = {name: pd.Series(frame[name].astype(float).to_numpy(), index=index, name=name) for name in feature_dependencies}

        try:
            pos, values = self._eval_at(expression.tokens, 0, env)
            if pos != len(expression.tokens):
                return self._empty(formula_hash, formula_text, total_rows, "trailing_tokens")
        except Exception as exc:  # noqa: BLE001
            return self._empty(formula_hash, formula_text, total_rows, f"execution_error:{exc}")

        return self._summarize(formula_hash, formula_text, values)

    def _eval_at(self, tokens: tuple[str, ...], pos: int, env: dict[str, pd.Series]) -> tuple[int, pd.Series]:
        token = tokens[pos]
        pos += 1
        if token in env:
            return pos, env[token]
        spec = OPERATORS[token]
        args = []
        for _ in range(spec.arity):
            pos, arg = self._eval_at(tokens, pos, env)
            args.append(arg)
        return pos, spec.implementation(*args)

    def _summarize(self, formula_hash: str, formula_text: str, values: pd.Series) -> ExecutionResult:
        total = len(values)
        inf_mask = np.isinf(values.to_numpy(dtype=float, na_value=np.nan))
        inf_rows = int(inf_mask.sum())
        nan_rows = int(values.isna().sum())
        finite = values.replace([np.inf, -np.inf], np.nan).dropna()
        valid_rows = int(len(finite))
        unique_values = int(finite.nunique(dropna=True)) if valid_rows else 0
        std = float(finite.std(ddof=0)) if valid_rows else float("nan")

        failure = None
        is_valid = True
        if inf_rows:
            failure = "inf_values"
            is_valid = False
        elif valid_rows < self.min_valid_rows:
            failure = "insufficient_valid_rows"
            is_valid = False
        elif unique_values <= 1 or not np.isfinite(std) or std < 1e-12:
            failure = "constant_or_all_missing"
            is_valid = False

        return ExecutionResult(formula_hash, formula_text, is_valid, failure, values, total, valid_rows, nan_rows, inf_rows, unique_values, std)

    @staticmethod
    def _empty(formula_hash: str, formula_text: str, total_rows: int, reason: str | None) -> ExecutionResult:
        return ExecutionResult(formula_hash, formula_text, False, reason, None, total_rows, 0, total_rows, 0, 0, float("nan"))
