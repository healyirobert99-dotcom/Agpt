from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ashare_research.config import load_simple_yaml


@dataclass(frozen=True)
class FactorResearchV2Config:
    raw: dict[str, Any]
    path: str

    @property
    def research_end(self) -> str:
        return str(self.raw["data"]["research_end"])

    @property
    def run_name(self) -> str:
        return str(self.raw.get("run", {}).get("name", "factor_research_v2"))

    @property
    def seed(self) -> int:
        return int(self.raw["generation"]["seed"])

    @property
    def candidate_count(self) -> int:
        return int(self.raw["generation"]["candidate_count"])

    @property
    def full_backtest_limit(self) -> int:
        return int(self.raw["full_backtest"]["limit"])


def load_v2_config(path: str | Path) -> FactorResearchV2Config:
    raw = load_simple_yaml(path)
    if str(raw["data"]["research_end"]) > "20260626":
        raise ValueError("research_data_end_after_forward_activation_cutoff")
    return FactorResearchV2Config(raw=raw, path=str(path))

