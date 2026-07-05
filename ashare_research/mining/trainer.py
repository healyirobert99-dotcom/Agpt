from __future__ import annotations

from .model import AlphaGPTLite, GeneratedFormula


class ReinforceTrainer:
    def __init__(self, model: AlphaGPTLite):
        self.model = model
        self.update_count = 0
        self.skipped_count = 0
        self.last_skip_reason: str | None = None

    def update(self, generated: GeneratedFormula, reward: float) -> None:
        self.model.update(generated, reward)
        self.update_count += 1

    def update_batch(self, items: list[tuple[GeneratedFormula, float]]) -> str | None:
        rewards = [float(reward) for _, reward in items]
        if not rewards:
            self.skipped_count += 1
            self.last_skip_reason = "empty_batch"
            return self.last_skip_reason
        if len(set(round(r, 12) for r in rewards)) <= 1:
            self.skipped_count += 1
            self.last_skip_reason = "constant_or_invalid_rewards"
            return self.last_skip_reason
        baseline = sum(rewards) / len(rewards)
        for generated, reward in items:
            self.model.update(generated, reward - baseline)
        self.update_count += len(items)
        self.last_skip_reason = None
        return None
