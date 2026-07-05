from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FrozenShortlist:
    formulas: list[dict]
    shortlist_hash: str
