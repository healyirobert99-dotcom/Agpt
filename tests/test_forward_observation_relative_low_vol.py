"""Tests for relative alpha forward observation runner."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from ashare_research.forward_observation.observe_relative_low_vol import (
    load_config,
    validate_relative_config,
    write_observation,
    _connect_db,
)

VALID_CONFIG = {
    "sqlite_path": "stock-data/ashare_research.sqlite3",
    "trading_allowed": False,
    "order_generation_allowed": False,
    "broker_connection_allowed": False,
    "candidate": {
        "candidate_id": "relative_low_vol_5d",
        "formula": "NEG(RET_STD20)",
        "rebalance_frequency": 5,
        "top_n": 20,
        "status": "relative_factor_watch_only",
        "absolute_return_strategy": False,
        "relative_alpha_factor": True,
    },
    "observation": {
        "primary_metric": "excess_return_vs_CSI800",
    },
}


def test_config_loads():
    config = load_config("config/forward_observation_low_vol_relative_alpha.yaml")
    assert config is not None
    assert "candidate" in config


def test_only_formula_neg_ret_std20():
    c = {**VALID_CONFIG, "candidate": {**VALID_CONFIG["candidate"], "formula": "OTHER"}}
    assert any("formula" in e for e in validate_relative_config(c))


def test_only_rebalance_5():
    c = {**VALID_CONFIG, "candidate": {**VALID_CONFIG["candidate"], "rebalance_frequency": 10}}
    assert any("rebalance_frequency" in e for e in validate_relative_config(c))


def test_only_topn_20():
    c = {**VALID_CONFIG, "candidate": {**VALID_CONFIG["candidate"], "top_n": 10}}
    assert any("top_n" in e for e in validate_relative_config(c))


def test_trading_must_be_false():
    c = {**VALID_CONFIG, "trading_allowed": True}
    assert any("trading_allowed" in e for e in validate_relative_config(c))


def test_order_generation_must_be_false():
    c = {**VALID_CONFIG, "order_generation_allowed": True}
    assert any("order_generation" in e for e in validate_relative_config(c))


def test_broker_must_be_false():
    c = {**VALID_CONFIG, "broker_connection_allowed": True}
    assert any("broker_connection" in e for e in validate_relative_config(c))


def test_valid_config_passes():
    assert len(validate_relative_config(VALID_CONFIG)) == 0


def test_output_contains_orders_generated_false():
    obs = {
        "observation_date": "20260626",
        "database_latest_trade_date": "20260626",
        "candidate_id": "relative_low_vol_5d",
        "formula": "NEG(RET_STD20)",
        "rebalance_frequency": 5,
        "top_n": 20,
        "stock_pool": "CSI800_asof",
        "benchmark": "CSI800 (000906.SH)",
        "candidate_status": "relative_factor_watch_only",
        "absolute_return_strategy": False,
        "relative_alpha_factor": True,
        "is_rebalance_day": False,
        "CSI800_index": {"found": True, "close": 4500, "daily_return": -0.005},
        "CSI800_5d_return": -0.01,
        "CSI800_20d_return": -0.02,
        "csi800_member_count": 800,
        "st_count": 10,
        "portfolio_top20": [],
        "portfolio_equal_weight": True,
        "orders_generated": False,
        "trading_allowed": False,
        "broker_connected": False,
        "portfolio_forward_return": None,
        "CSI800_forward_return": None,
        "excess_return_vs_CSI800": None,
        "rolling_5d_excess": None,
        "rolling_20d_excess": None,
        "relative_hit_rate": None,
        "observation_timestamp": "now",
    }
    with tempfile.TemporaryDirectory() as tmp:
        json_path, _ = write_observation(obs, tmp)
        content = json_path.read_text(encoding="utf-8")
        assert "orders_generated" in content
        assert "false" in content.lower()


def test_database_missing_stops():
    with pytest.raises(FileNotFoundError):
        _connect_db("/nonexistent/db.sqlite3")


def test_output_markdown_mentions_relative_alpha():
    obs = {
        "observation_date": "20260626",
        "candidate_id": "relative_low_vol_5d",
        "formula": "NEG(RET_STD20)",
        "rebalance_frequency": 5,
        "top_n": 20,
        "stock_pool": "CSI800_asof",
        "benchmark": "CSI800 (000906.SH)",
        "candidate_status": "relative_factor_watch_only",
        "absolute_return_strategy": False,
        "relative_alpha_factor": True,
        "is_rebalance_day": False,
        "CSI800_index": {"close": 4500, "daily_return": -0.005},
        "CSI800_5d_return": None,
        "CSI800_20d_return": None,
        "csi800_member_count": 800,
        "st_count": 0,
        "portfolio_top20": [],
        "portfolio_equal_weight": True,
        "orders_generated": False,
        "trading_allowed": False,
        "broker_connected": False,
        "portfolio_forward_return": None,
        "CSI800_forward_return": None,
        "excess_return_vs_CSI800": None,
        "observation_timestamp": "now",
    }
    with tempfile.TemporaryDirectory() as tmp:
        _, md_path = write_observation(obs, tmp)
        content = md_path.read_text(encoding="utf-8")
        assert "RELATIVE ALPHA" in content
        assert "excess_return_vs_CSI800" in content
