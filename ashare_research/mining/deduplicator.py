from __future__ import annotations


class FormulaDeduplicator:
    def __init__(self, historical_hashes: set[str] | None = None):
        self.seen: set[str] = set(historical_hashes or set())

    def accept(self, formula_hash: str) -> bool:
        if formula_hash in self.seen:
            return False
        self.seen.add(formula_hash)
        return True
