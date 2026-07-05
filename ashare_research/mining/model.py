from __future__ import annotations

import json
from dataclasses import dataclass

import numpy as np

from ashare_research.factors.expression import Expression
from ashare_research.factors.vocabulary import MAX_FORMULA_LENGTH, TOKENS

from .action_mask import MaskState, next_state, valid_next_tokens


TOKEN_NAMES = tuple(TOKENS.keys())
TOKEN_INDEX = {name: i for i, name in enumerate(TOKEN_NAMES)}


@dataclass
class GeneratedFormula:
    expression: Expression
    log_probs: list[float]


class PositionLogitGenerator:
    """Position-dependent token logits with strict action masking."""

    def __init__(self, seed: int = 0, learning_rate: float = 0.05):
        self.seed = int(seed)
        self.learning_rate = float(learning_rate)
        self.rng = np.random.default_rng(self.seed)
        self.logits = np.zeros((MAX_FORMULA_LENGTH, len(TOKEN_NAMES)), dtype=float)

    def generate(self) -> GeneratedFormula:
        state = MaskState()
        tokens: list[str] = []
        log_probs: list[float] = []
        for step in range(MAX_FORMULA_LENGTH):
            allowed = valid_next_tokens(state, step)
            if not allowed:
                break
            probs = self._masked_probs(step, allowed)
            idx = int(self.rng.choice(len(TOKEN_NAMES), p=probs))
            token = TOKEN_NAMES[idx]
            tokens.append(token)
            log_probs.append(float(np.log(max(probs[idx], 1e-12))))
            state = next_state(state, token)
            if state.closed:
                break
        return GeneratedFormula(Expression(tuple(tokens)), log_probs)

    def formula_probability(self, tokens: tuple[str, ...]) -> float:
        state = MaskState()
        prob = 1.0
        for step, token in enumerate(tokens):
            allowed = valid_next_tokens(state, step)
            if token not in allowed:
                return 0.0
            probs = self._masked_probs(step, allowed)
            prob *= float(probs[TOKEN_INDEX[token]])
            state = next_state(state, token)
        return prob if state.closed else 0.0

    def update(self, generated: GeneratedFormula, reward: float) -> None:
        advantage = float(np.clip(reward, -5.0, 5.0))
        for step, token in enumerate(generated.expression.tokens):
            allowed = valid_next_tokens(MaskState() if step == 0 else self._state_before(generated.expression.tokens, step), step)
            if not allowed:
                continue
            probs = self._masked_probs(step, allowed)
            grad = -probs
            grad[TOKEN_INDEX[token]] += 1.0
            self.logits[step] += self.learning_rate * advantage * grad

    def _state_before(self, tokens: tuple[str, ...], step: int) -> MaskState:
        state = MaskState()
        for i in range(step):
            state = next_state(state, tokens[i])
        return state

    def _masked_probs(self, step: int, allowed: tuple[str, ...]) -> np.ndarray:
        mask = np.full(len(TOKEN_NAMES), -np.inf)
        for token in allowed:
            mask[TOKEN_INDEX[token]] = self.logits[step, TOKEN_INDEX[token]]
        finite = mask[np.isfinite(mask)]
        shifted = mask - finite.max()
        weights = np.exp(shifted, where=np.isfinite(shifted), out=np.zeros_like(shifted))
        return weights / weights.sum()

    def state_dict(self) -> dict:
        return {
            "seed": self.seed,
            "learning_rate": self.learning_rate,
            "logits": self.logits.tolist(),
            "rng_state": self.rng.bit_generator.state,
        }

    @classmethod
    def from_state_dict(cls, state: dict) -> "PositionLogitGenerator":
        model = cls(seed=int(state["seed"]), learning_rate=float(state["learning_rate"]))
        model.logits = np.array(state["logits"], dtype=float)
        model.rng.bit_generator.state = state["rng_state"]
        return model

    def state_hash(self) -> str:
        import hashlib

        payload = json.dumps(self.state_dict(), sort_keys=True)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class AlphaGPTLite(PositionLogitGenerator):
    """Backward-compatible alias for PositionLogitGenerator."""


class UniformRandomGenerator(PositionLogitGenerator):
    """Uniform random baseline over action-mask-valid tokens; never trains."""

    def update(self, generated: GeneratedFormula, reward: float) -> None:
        return None
