from __future__ import annotations

from ashare_research.factors.expression import Expression

from .model import AlphaGPTLite, GeneratedFormula


class FormulaGenerator:
    def __init__(self, model: AlphaGPTLite):
        self.model = model

    def generate_batch(self, batch_size: int) -> list[GeneratedFormula]:
        return [self.model.generate() for _ in range(int(batch_size))]


def validate_generated(expression: Expression) -> tuple[bool, str | None]:
    return expression.validate()
