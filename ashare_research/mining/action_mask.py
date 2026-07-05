from __future__ import annotations

from dataclasses import dataclass

from ashare_research.factors.vocabulary import MAX_FORMULA_LENGTH, TOKENS, token_arity


TOKEN_NAMES = tuple(TOKENS.keys())
FEATURE_TOKENS = tuple(name for name, spec in TOKENS.items() if spec.arity == 0)
OPERATOR_TOKENS = tuple(name for name, spec in TOKENS.items() if spec.arity > 0)


@dataclass(frozen=True)
class MaskState:
    open_slots: int = 1
    closed: bool = False


def next_state(state: MaskState, token: str) -> MaskState:
    if state.closed:
        raise ValueError("formula_already_closed")
    if token not in TOKENS:
        raise ValueError(f"unknown_token:{token}")
    open_slots = state.open_slots - 1 + token_arity(token)
    if open_slots < 0:
        raise ValueError("negative_open_slots")
    return MaskState(open_slots=open_slots, closed=open_slots == 0)


def valid_next_tokens(state: MaskState, step: int, max_len: int = MAX_FORMULA_LENGTH) -> tuple[str, ...]:
    if state.closed or state.open_slots <= 0:
        return ()
    remaining_after_this = max_len - step - 1
    allowed: list[str] = []
    for token in TOKEN_NAMES:
        new_open = state.open_slots - 1 + token_arity(token)
        if new_open < 0:
            continue
        if new_open > remaining_after_this:
            continue
        allowed.append(token)
    return tuple(allowed)


def is_complete(tokens: tuple[str, ...]) -> bool:
    state = MaskState()
    for i, token in enumerate(tokens):
        if token not in valid_next_tokens(state, i):
            return False
        state = next_state(state, token)
    return state.closed
