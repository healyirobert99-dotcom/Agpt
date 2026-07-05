from __future__ import annotations

from dataclasses import dataclass

from .base_features import BASE_FEATURES
from .operators import OPERATORS


MAX_FORMULA_LENGTH = 8


@dataclass(frozen=True)
class Token:
    name: str
    kind: str
    arity: int = 0


TOKENS: dict[str, Token] = {
    **{name: Token(name, "feature", 0) for name in BASE_FEATURES},
    **{name: Token(name, "operator", spec.arity) for name, spec in OPERATORS.items()},
}


def token_arity(name: str) -> int:
    if name not in TOKENS:
        raise ValueError(f"Unknown token: {name}")
    return TOKENS[name].arity

