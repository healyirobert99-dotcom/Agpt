from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class CandidateFormula:
    formula_hash: str
    canonical_formula: str
    tokens: tuple[str, ...]
    generator_type: str
    parent_factor_id: str | None
    generation_seed: int
    complexity: int
    feature_dependencies: tuple[str, ...]
    operator_dependencies: tuple[str, ...]


@dataclass
class StageSummary:
    stage: str
    input_count: int
    passed_count: int
    rejected_count: int
    rejection_reasons: dict[str, int] = field(default_factory=dict)
    elapsed_seconds: float = 0.0


@dataclass
class FactorRecord:
    factor_id: str
    formula_hash: str
    canonical_formula: str
    status: str
    grade: str
    fast_screen_metrics: dict[str, Any]
    full_backtest_metrics: dict[str, Any]
    robustness_metrics: dict[str, Any]
    rejection_reason: str | None = None

