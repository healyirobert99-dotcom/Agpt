from ashare_research.factors.expression import Expression
from ashare_research.factors.vocabulary import MAX_FORMULA_LENGTH, TOKENS
from ashare_research.mining.action_mask import MaskState, is_complete, next_state, valid_next_tokens


def test_action_mask_only_allows_closable_formulas() -> None:
    state = MaskState()
    tokens = []
    for step in range(MAX_FORMULA_LENGTH):
        allowed = valid_next_tokens(state, step)
        assert set(allowed) <= set(TOKENS)
        token = allowed[0]
        tokens.append(token)
        state = next_state(state, token)
        if state.closed:
            break

    expr = Expression(tuple(tokens))
    assert expr.validate() == (True, None)
    assert is_complete(expr.tokens)
    assert len(expr.tokens) <= MAX_FORMULA_LENGTH
