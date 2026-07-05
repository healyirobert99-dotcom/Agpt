from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Candidate:
    formula_hash: str
    formula_text: str
    token_sequence: list[str]
    formula_length: int
    train_metrics: dict
    train_reward: float
    validity_status: str
    failure_reason: str | None
    data_snapshot_hash: str
    backtest_config_hash: str
    model_checkpoint: str | None
    created_iteration: int


@dataclass
class CandidatePool:
    capacity: int
    candidates: dict[str, Candidate] = field(default_factory=dict)

    def add(self, candidate: Candidate) -> None:
        if candidate.formula_hash in self.candidates:
            return
        self.candidates[candidate.formula_hash] = candidate
        self._trim()

    def ranked(self) -> list[Candidate]:
        return sorted(
            self.candidates.values(),
            key=lambda c: (-float(c.train_reward), c.formula_hash),
        )

    def _trim(self) -> None:
        ranked = self.ranked()
        self.candidates = {c.formula_hash: c for c in ranked[: self.capacity]}
