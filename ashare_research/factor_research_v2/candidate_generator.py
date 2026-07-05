from __future__ import annotations

import random
from collections import Counter

from ashare_research.factors.expression import Expression, parse_formula_text
from ashare_research.factors.vocabulary import TOKENS, token_arity
from ashare_research.mining.action_mask import FEATURE_TOKENS, OPERATOR_TOKENS, MaskState, next_state, valid_next_tokens

from .models import CandidateFormula


COMMUTATIVE = {"ADD", "MUL"}


def canonicalize(expr: Expression) -> Expression:
    valid, _ = expr.validate()
    if not valid:
        return expr
    tokens, _ = _canonical_at(expr.tokens, 0)
    return Expression(tuple(tokens))


def _canonical_at(tokens: tuple[str, ...], pos: int) -> tuple[list[str], int]:
    token = tokens[pos]
    pos += 1
    arity = token_arity(token)
    if arity == 0:
        return [token], pos
    children = []
    for _ in range(arity):
        child, pos = _canonical_at(tokens, pos)
        children.append(child)
    if token in COMMUTATIVE:
        children = sorted(children, key=lambda c: Expression(tuple(c)).to_string())
    out = [token]
    for child in children:
        out.extend(child)
    return out, pos


class CandidateGeneratorV2:
    def __init__(self, *, seed: int, max_prefix_tokens: int = 8, max_tree_depth: int = 4):
        self.seed = int(seed)
        self.rng = random.Random(self.seed)
        self.max_prefix_tokens = int(max_prefix_tokens)
        self.max_tree_depth = int(max_tree_depth)

    def generate(self, count: int, *, parents: list[str] | None = None) -> tuple[list[CandidateFormula], dict]:
        parents = parents or []
        candidates: list[CandidateFormula] = []
        seen: set[str] = set()
        attempts = 0
        modes = ["random", "enumeration", "mutation"]
        shallow = self.enumerate_shallow()
        while len(candidates) < count and attempts < count * 30:
            attempts += 1
            mode = modes[attempts % len(modes)]
            try:
                if mode == "enumeration" and shallow:
                    expr = shallow[(attempts // len(modes)) % len(shallow)]
                elif mode == "mutation" and parents:
                    expr = self.mutate(parse_formula_text(self.rng.choice(parents)))
                else:
                    expr = self.random_expression()
                expr = canonicalize(expr)
                valid, reason = expr.validate()
                if not valid or len(expr.tokens) > self.max_prefix_tokens:
                    continue
                if _obvious_identity(expr):
                    continue
                formula_hash = expr.sha256()
                if formula_hash in seen:
                    continue
                seen.add(formula_hash)
                candidates.append(_candidate(expr, mode, self.seed))
            except Exception:
                continue
        return candidates, {"generated_count": len(candidates), "attempt_count": attempts, "mode_counts": Counter(c.generator_type for c in candidates)}

    def random_expression(self) -> Expression:
        state = MaskState()
        tokens: list[str] = []
        for step in range(self.max_prefix_tokens):
            allowed = list(valid_next_tokens(state, step, self.max_prefix_tokens))
            if not allowed:
                break
            if step >= self.max_tree_depth:
                allowed = [t for t in allowed if token_arity(t) == 0] or allowed
            token = self.rng.choice(allowed)
            tokens.append(token)
            state = next_state(state, token)
            if state.closed:
                break
        return Expression(tuple(tokens))

    def mutate(self, expr: Expression) -> Expression:
        tokens = list(expr.tokens)
        if not tokens:
            return self.random_expression()
        idx = self.rng.randrange(len(tokens))
        old = tokens[idx]
        same_arity = [t for t in TOKENS if token_arity(t) == token_arity(old)]
        tokens[idx] = self.rng.choice(same_arity)
        return Expression(tuple(tokens))

    def enumerate_shallow(self) -> list[Expression]:
        out = [Expression((f,)) for f in FEATURE_TOKENS]
        for op in OPERATOR_TOKENS:
            arity = token_arity(op)
            if arity == 1:
                out.extend(Expression((op, f)) for f in FEATURE_TOKENS)
            elif arity == 2:
                for a in FEATURE_TOKENS:
                    for b in FEATURE_TOKENS:
                        out.append(Expression((op, a, b)))
        return out


def _candidate(expr: Expression, mode: str, seed: int) -> CandidateFormula:
    features = tuple(t for t in expr.tokens if token_arity(t) == 0)
    operators = tuple(t for t in expr.tokens if token_arity(t) > 0)
    return CandidateFormula(
        formula_hash=expr.sha256(),
        canonical_formula=expr.to_string(),
        tokens=expr.tokens,
        generator_type=mode,
        parent_factor_id=None,
        generation_seed=seed,
        complexity=len(expr.tokens),
        feature_dependencies=tuple(sorted(set(features))),
        operator_dependencies=tuple(sorted(set(operators))),
    )


def _obvious_identity(expr: Expression) -> bool:
    text = expr.to_string()
    return text.startswith("SUB(") and text.count(",") == 1 and text[4:-1].split(",")[0] == text[4:-1].split(",")[1]
