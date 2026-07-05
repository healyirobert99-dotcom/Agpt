"""Tests for forward observation framework. Observation-only, no trading."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from ashare_research.forward_observation.observe_low_vol_5d import (
    load_config,
    validate_config,
    write_observation,
)


VALID_CONFIG = {
    "sqlite_path": "stock-data/ashare_research.sqlite3",
    "trading_allowed": False,
    "order_generation_allowed": False,
    "broker_connection_allowed": False,
    "candidate": {
        "candidate_id": "primary_low_vol_5d",
        "formula": "NEG(RET_STD20)",
        "rebalance_frequency": 5,
        "top_n": 20,
    },
}


def test_config_loads() -> None:
    """Config can be loaded from the actual file."""
    config = load_config("config/forward_observation_low_vol_5d.yaml")
    assert config is not None
    assert "candidate" in config


def test_trading_allowed_must_be_false() -> None:
    config = {**VALID_CONFIG, "trading_allowed": True}
    errors = validate_config(config)
    assert any("trading_allowed" in e for e in errors)


def test_order_generation_allowed_must_be_false() -> None:
    config = {**VALID_CONFIG, "order_generation_allowed": True}
    errors = validate_config(config)
    assert any("order_generation" in e for e in errors)


def test_broker_connection_allowed_must_be_false() -> None:
    config = {**VALID_CONFIG, "broker_connection_allowed": True}
    errors = validate_config(config)
    assert any("broker_connection" in e for e in errors)


def test_only_formula_neg_ret_std20_allowed() -> None:
    config = {**VALID_CONFIG, "candidate": {**VALID_CONFIG["candidate"], "formula": "RET1"}}
    errors = validate_config(config)
    assert any("formula" in e for e in errors)


def test_only_rebalance_frequency_5_allowed() -> None:
    config = {**VALID_CONFIG, "candidate": {**VALID_CONFIG["candidate"], "rebalance_frequency": 10}}
    errors = validate_config(config)
    assert any("rebalance_frequency" in e for e in errors)


def test_only_candidate_id_primary_low_vol_5d_allowed() -> None:
    config = {**VALID_CONFIG, "candidate": {**VALID_CONFIG["candidate"], "candidate_id": "other"}}
    errors = validate_config(config)
    assert any("candidate_id" in e for e in errors)


def test_valid_config_passes() -> None:
    errors = validate_config(VALID_CONFIG)
    assert len(errors) == 0


def test_output_contains_orders_generated_false() -> None:
    obs = {
        "observation_date": "20260626",
        "database_latest_trade_date": "20260626",
        "candidate_id": "primary_low_vol_5d",
        "formula": "NEG(RET_STD20)",
        "rebalance_frequency": 5,
        "is_rebalance_day": False,
        "top_n": 20,
        "csi800_member_count": 800,
        "st_count": 10,
        "watchlist": [],
        "trading_allowed": False,
        "orders_generated": False,
        "broker_connected": False,
        "next_5d_return_observed": None,
        "portfolio_forward_return": None,
        "benchmark_forward_return": None,
        "excess_return": None,
        "observation_timestamp": "2026-07-05T16:00:00",
    }
    with tempfile.TemporaryDirectory() as tmp:
        json_path, md_path = write_observation(obs, tmp)
        content = json_path.read_text(encoding="utf-8")
        assert "orders_generated" in content
        assert "false" in content.lower()
        assert "trading_allowed" in content


def test_database_missing_stops_safely() -> None:
    """When database doesn't exist, the script exits gracefully."""
    # This is tested via the main() function's early check
    # which verifies Path.exists() before attempting connection
    from ashare_research.forward_observation.observe_low_vol_5d import _connect_db
    with pytest.raises(FileNotFoundError):
        _connect_db("/nonexistent/database.sqlite3")


def test_output_markdown_has_disclaimer() -> None:
    obs = {
        "observation_date": "20260626",
        "database_latest_trade_date": "20260626",
        "candidate_id": "primary_low_vol_5d",
        "formula": "NEG(RET_STD20)",
        "rebalance_frequency": 5,
        "is_rebalance_day": False,
        "top_n": 20,
        "csi800_member_count": 800,
        "st_count": 0,
        "watchlist": [],
        "trading_allowed": False,
        "orders_generated": False,
        "broker_connected": False,
        "observation_timestamp": "now",
    }
    with tempfile.TemporaryDirectory() as tmp:
        _, md_path = write_observation(obs, tmp)
        content = md_path.read_text(encoding="utf-8")
        assert "OBSERVATION ONLY" in content
        assert "不构成任何投资建议" in content
