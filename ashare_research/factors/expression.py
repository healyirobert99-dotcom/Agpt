from __future__ import annotations

import hashlib
from dataclasses import dataclass

from .vocabulary import MAX_FORMULA_LENGTH, TOKENS, token_arity


@dataclass(frozen=True)
class Expression:
    tokens: tuple[str, ...]

    def validate(self) -> tuple[bool, str | None]:
        if not self.tokens:
            return False, "empty_formula"
        if len(self.tokens) > MAX_FORMULA_LENGTH:
            return False, "formula_too_long"
        pos, reason = self._parse_at(0)
        if reason:
            return False, reason
        if pos != len(self.tokens):
            return False, "trailing_tokens"
        return True, None

    def _parse_at(self, pos: int) -> tuple[int, str | None]:
        if pos >= len(self.tokens):
            return pos, "unexpected_end"
        token = self.tokens[pos]
        if token not in TOKENS:
            return pos, f"unknown_token:{token}"
        pos += 1
        for _ in range(token_arity(token)):
            pos, reason = self._parse_at(pos)
            if reason:
                return pos, reason
        return pos, None

    def to_string(self) -> str:
        pos, text = self._string_at(0)
        if pos != len(self.tokens):
            return "Invalid"
        return text

    def _string_at(self, pos: int) -> tuple[int, str]:
        token = self.tokens[pos]
        arity = token_arity(token)
        pos += 1
        if arity == 0:
            return pos, token
        args = []
        for _ in range(arity):
            pos, arg = self._string_at(pos)
            args.append(arg)
        return pos, f"{token}({','.join(args)})"

    def normalized(self) -> str:
        valid, reason = self.validate()
        if not valid:
            return f"INVALID:{reason}:{' '.join(self.tokens)}"
        return self.to_string()

    def sha256(self) -> str:
        return hashlib.sha256(self.normalized().encode("utf-8")).hexdigest()


def parse_formula_text(text: str) -> Expression:
    """Parse a compact prefix formula such as ADD(RET1,VOL_RATIO20)."""
    parser = _FormulaTextParser(text)
    tokens = parser.parse()
    return Expression(tuple(tokens))


class _FormulaTextParser:
    def __init__(self, text: str):
        self.text = text
        self.pos = 0

    def parse(self) -> list[str]:
        tokens = self._parse_expr()
        self._skip_ws()
        if self.pos != len(self.text):
            raise ValueError(f"trailing_formula_text_at:{self.pos}")
        return tokens

    def _parse_expr(self) -> list[str]:
        self._skip_ws()
        name = self._parse_name()
        if name not in TOKENS:
            raise ValueError(f"unknown_token:{name}")
        tokens = [name]
        arity = token_arity(name)
        if arity == 0:
            return tokens
        self._skip_ws()
        self._expect("(")
        for i in range(arity):
            if i:
                self._expect(",")
            tokens.extend(self._parse_expr())
        self._expect(")")
        return tokens

    def _parse_name(self) -> str:
        start = self.pos
        while self.pos < len(self.text) and (self.text[self.pos].isalnum() or self.text[self.pos] == "_"):
            self.pos += 1
        if start == self.pos:
            raise ValueError(f"expected_token_at:{self.pos}")
        return self.text[start:self.pos]

    def _expect(self, char: str) -> None:
        self._skip_ws()
        if self.pos >= len(self.text) or self.text[self.pos] != char:
            raise ValueError(f"expected_{char}_at:{self.pos}")
        self.pos += 1

    def _skip_ws(self) -> None:
        while self.pos < len(self.text) and self.text[self.pos].isspace():
            self.pos += 1
