"""Tests for second_round_gate.py — 第二轮最小搜索配置门禁检查器测试。"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

from ashare_research.factor_research_v2.second_round_gate import (
    EXPECTED_OPERATORS,
    GateResult,
    check_second_round_gate,
)


# ---------- 合法草案配置 ----------

VALID_DRAFT = {
    "status": "draft_not_approved",
    "run_enabled": False,
    "formula_generation_enabled": False,
    "backtest_enabled": False,
    "search_enabled": False,
    "forward_data_access_allowed": False,
    "external_data_allowed": False,
    "operator_extension_allowed": False,
    "threshold_change_allowed": False,
    "rating_rule_change_allowed": False,
    "allowed_seed_manifest": "dummy.jsonl",
    "allowed_scope": [
        "seed_single_factor",
        "seed_pairwise_economic_combination",
        "same_family_narrow_derivation",
    ],
    "allowed_features": {
        "original": ["RET1", "RET5", "VOL_RATIO20", "VOLUME_WEIGHTED_RET", "TREND60"],
        "second_batch_approved": [
            "RET20", "RET60", "RET120",
            "RET_STD20", "RET_STD60",
            "DOWNSIDE_RET_STD20", "DOWNSIDE_RET_STD60",
            "AMOUNT_MA20", "AMOUNT_MA60",
            "TREND20", "TREND120",
        ],
    },
    "allowed_operators": sorted(EXPECTED_OPERATORS),
    "locked_thresholds": {
        "screening": {
            "min_valid_rows": 20,
            "min_coverage": 0.30,
            "min_abs_rank_ic_mean": 0.001,
            "min_cross_sectional_dispersion": 0.000001,
        },
        "correlation": {
            "output_correlation_threshold": 0.95,
            "max_correlation_rows": 2000,
        },
        "rating": {
            "min_positive_period_ratio": 0.45,
            "grade_a_min_abs_ic": 0.03,
            "grade_a_max_drawdown": 0.35,
            "grade_b_min_abs_ic": 0.015,
        },
    },
}

VALID_SEED = {
    "seed_factor_id": "fp_reversal_short_010",
    "factor_name_cn": "短期反转因子",
    "source_title": "Smart Beta public reference; Qlib reference",
    "source_url_or_path": "test",
    "source_verified_by_firecrawl": True,
    "computability_class": "computable_with_current_data",
    "factor_category": "反转",
    "economic_intuition": "短期流动性冲击和过度交易可能带来反转。",
    "required_data": ["日线价量"],
    "uses_existing_base_feature": True,
    "requires_new_base_feature": False,
    "requires_new_operator": False,
    "requires_new_external_data": False,
    "suggested_for_second_batch_minimal_experiment": True,
    "approval_required": True,
}

VALID_SEED_REQUIRES_FEATURE = {
    **VALID_SEED,
    "seed_factor_id": "fp_momentum_mid_009",
    "computability_class": "computable_with_minor_feature_derivation",
    "requires_new_base_feature": True,
}


def _to_yaml(data: object, indent: int = 0) -> str:
    """Minimal YAML serializer compatible with load_simple_yaml."""
    prefix = "  " * indent
    if isinstance(data, dict):
        lines = []
        for k, v in data.items():
            if isinstance(v, dict):
                lines.append(f"{prefix}{k}:")
                lines.append(_to_yaml(v, indent + 1))
            elif isinstance(v, list):
                items = ", ".join(_yaml_value(x) for x in v)
                lines.append(f"{prefix}{k}: [{items}]")
            else:
                lines.append(f"{prefix}{k}: {_yaml_value(v)}")
        return "\n".join(lines)
    return f"{prefix}{_yaml_value(data)}"


def _yaml_value(v: object) -> str:
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        return repr(v)
    return json.dumps(str(v))


def _write_yaml(path: Path, data: dict) -> None:
    path.write_text(_to_yaml(data), encoding="utf-8")


def _write_jsonl(path: Path, records: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")


def _tmp_config(data: dict) -> str:
    fd, p = tempfile.mkstemp(suffix=".yaml")
    os.close(fd)
    _write_yaml(Path(p), data)
    return p


def _tmp_seed(records: list[dict]) -> str:
    fd, p = tempfile.mkstemp(suffix=".jsonl")
    os.close(fd)
    _write_jsonl(Path(p), records)
    return p


# ---------- 测试 1: 合法草案配置通过门禁 ----------


def test_valid_draft_passes_gate() -> None:
    config_path = _tmp_config(VALID_DRAFT)
    seed_path = _tmp_seed([VALID_SEED])

    result = check_second_round_gate(config_path, seed_path)

    assert result.passed, f"Expected pass but got failures: {result.failures}"
    assert len(result.failures) == 0


# ---------- 测试 2: 状态不是 draft_not_approved ----------


def test_approved_status_fails() -> None:
    bad = {**VALID_DRAFT, "status": "approved"}
    config_path = _tmp_config(bad)
    seed_path = _tmp_seed([VALID_SEED])

    result = check_second_round_gate(config_path, seed_path)

    assert not result.passed
    assert any("status" in f.lower() for f in result.failures)


def test_executable_status_fails() -> None:
    bad = {**VALID_DRAFT, "status": "executable"}
    config_path = _tmp_config(bad)
    seed_path = _tmp_seed([VALID_SEED])

    result = check_second_round_gate(config_path, seed_path)

    assert not result.passed
    assert any("status" in f.lower() for f in result.failures)


def test_missing_status_fails() -> None:
    bad = {**VALID_DRAFT}
    del bad["status"]
    config_path = _tmp_config(bad)
    seed_path = _tmp_seed([VALID_SEED])

    result = check_second_round_gate(config_path, seed_path)

    assert not result.passed


# ---------- 测试 3: 执行控制被开启时失败 ----------


@pytest.mark.parametrize("bad_key", [
    "run_enabled",
    "formula_generation_enabled",
    "backtest_enabled",
    "search_enabled",
])
def test_execution_control_enabled_fails(bad_key: str) -> None:
    bad = {**VALID_DRAFT, bad_key: True}
    config_path = _tmp_config(bad)
    seed_path = _tmp_seed([VALID_SEED])

    result = check_second_round_gate(config_path, seed_path)

    assert not result.passed
    assert any(bad_key in f for f in result.failures)


def test_missing_execution_control_fails() -> None:
    bad = {**VALID_DRAFT}
    del bad["run_enabled"]
    config_path = _tmp_config(bad)
    seed_path = _tmp_seed([VALID_SEED])

    result = check_second_round_gate(config_path, seed_path)

    assert not result.passed
    assert any("missing_execution_control" in f for f in result.failures)


# ---------- 测试 4: 边界控制被开启时失败 ----------


@pytest.mark.parametrize("bad_key", [
    "forward_data_access_allowed",
    "external_data_allowed",
    "operator_extension_allowed",
])
def test_boundary_allowed_fails(bad_key: str) -> None:
    bad = {**VALID_DRAFT, bad_key: True}
    config_path = _tmp_config(bad)
    seed_path = _tmp_seed([VALID_SEED])

    result = check_second_round_gate(config_path, seed_path)

    assert not result.passed
    assert any(bad_key in f for f in result.failures)


def test_missing_boundary_control_fails() -> None:
    bad = {**VALID_DRAFT}
    del bad["forward_data_access_allowed"]
    config_path = _tmp_config(bad)
    seed_path = _tmp_seed([VALID_SEED])

    result = check_second_round_gate(config_path, seed_path)

    assert not result.passed
    assert any("missing_boundary_control" in f for f in result.failures)


# ---------- 测试 5: 阈值变更失败 ----------


def test_threshold_change_allowed_fails() -> None:
    bad = {**VALID_DRAFT, "threshold_change_allowed": True}
    config_path = _tmp_config(bad)
    seed_path = _tmp_seed([VALID_SEED])

    result = check_second_round_gate(config_path, seed_path)

    assert not result.passed
    assert any("threshold_change" in f for f in result.failures)


def test_threshold_deviation_fails() -> None:
    bad = {**VALID_DRAFT}
    bad["locked_thresholds"] = {
        **bad["locked_thresholds"],
        "screening": {"min_coverage": 0.10},  # 从 0.30 改到 0.10
    }
    config_path = _tmp_config(bad)
    seed_path = _tmp_seed([VALID_SEED])

    result = check_second_round_gate(config_path, seed_path)

    assert not result.passed
    assert any("threshold_deviation" in f for f in result.failures)


# ---------- 测试 6: 评级规则变更失败 ----------


def test_rating_rule_change_allowed_fails() -> None:
    bad = {**VALID_DRAFT, "rating_rule_change_allowed": True}
    config_path = _tmp_config(bad)
    seed_path = _tmp_seed([VALID_SEED])

    result = check_second_round_gate(config_path, seed_path)

    assert not result.passed
    assert any("rating_rule_change" in f for f in result.failures)


def test_rating_rule_deviation_fails() -> None:
    bad = {**VALID_DRAFT}
    bad["locked_thresholds"] = {
        **bad["locked_thresholds"],
        "rating": {"grade_a_min_abs_ic": 0.01},  # 从 0.03 改到 0.01
    }
    config_path = _tmp_config(bad)
    seed_path = _tmp_seed([VALID_SEED])

    result = check_second_round_gate(config_path, seed_path)

    assert not result.passed
    assert any("rating_rule_deviation" in f for f in result.failures)


# ---------- 测试 7: 种子因子范围 ----------


def test_seed_manifest_not_found_fails() -> None:
    config_path = _tmp_config(VALID_DRAFT)
    seed_path = "/nonexistent/seed_factor_manifest.jsonl"

    result = check_second_round_gate(config_path, seed_path)

    assert not result.passed
    assert any("seed_manifest_not_found" in f for f in result.failures)


def test_requires_new_external_data_seed_fails() -> None:
    config_path = _tmp_config(VALID_DRAFT)
    bad_seed = {
        **VALID_SEED,
        "seed_factor_id": "fp_bad_001",
        "requires_new_external_data": True,
    }
    seed_path = _tmp_seed([bad_seed])

    result = check_second_round_gate(config_path, seed_path)

    assert not result.passed
    assert any("fp_bad_001" in f for f in result.failures)
    assert any("external_data" in f.lower() for f in result.failures)


def test_source_not_verified_seed_fails() -> None:
    config_path = _tmp_config(VALID_DRAFT)
    bad_seed = {
        **VALID_SEED,
        "seed_factor_id": "fp_bad_002",
        "source_verified_by_firecrawl": False,
    }
    seed_path = _tmp_seed([bad_seed])

    result = check_second_round_gate(config_path, seed_path)

    assert not result.passed
    assert any("fp_bad_002" in f for f in result.failures)
    assert any("source_not_verified" in f for f in result.failures)


def test_not_suggested_for_second_batch_fails() -> None:
    config_path = _tmp_config(VALID_DRAFT)
    bad_seed = {
        **VALID_SEED,
        "seed_factor_id": "fp_bad_003",
        "suggested_for_second_batch_minimal_experiment": False,
    }
    seed_path = _tmp_seed([bad_seed])

    result = check_second_round_gate(config_path, seed_path)

    assert not result.passed
    assert any("fp_bad_003" in f for f in result.failures)
    assert any("not_suggested" in f for f in result.failures)


def test_unverified_computability_fails() -> None:
    config_path = _tmp_config(VALID_DRAFT)
    bad_seed = {
        **VALID_SEED,
        "seed_factor_id": "fp_bad_004",
        "computability_class": "partial_source_candidate",
    }
    seed_path = _tmp_seed([bad_seed])

    result = check_second_round_gate(config_path, seed_path)

    assert not result.passed
    assert any("fp_bad_004" in f for f in result.failures)
    assert any("unverified_computability" in f for f in result.failures)


def test_no_source_seed_fails() -> None:
    config_path = _tmp_config(VALID_DRAFT)
    bad_seed = {
        **VALID_SEED,
        "seed_factor_id": "fp_bad_005",
        "source_title": "",
        "source_url_or_path": "",
    }
    seed_path = _tmp_seed([bad_seed])

    result = check_second_round_gate(config_path, seed_path)

    assert not result.passed
    assert any("fp_bad_005" in f for f in result.failures)
    assert any("no_source" in f for f in result.failures)


def test_requires_new_data_seed_in_manifest_fails() -> None:
    config_path = _tmp_config(VALID_DRAFT)
    bad_seed = {
        **VALID_SEED,
        "seed_factor_id": "fp_bad_006",
        "computability_class": "requires_new_data",
    }
    seed_path = _tmp_seed([bad_seed])

    result = check_second_round_gate(config_path, seed_path)

    assert not result.passed
    assert any("fp_bad_006" in f for f in result.failures)


# ---------- 测试 8: 特征范围 ----------


def test_undefined_feature_in_config_fails() -> None:
    config_path = _tmp_config(VALID_DRAFT)
    seed_path = _tmp_seed([VALID_SEED])

    # 使用一个不存在的 BASE_FEATURES
    fake_features = ("RET1", "RET5")
    result = check_second_round_gate(config_path, seed_path, base_features=fake_features)

    assert not result.passed
    assert any("undefined" in f or "unapproved" in f for f in result.failures)


# ---------- 测试 9: 算子范围 ----------


def test_new_operator_in_config_fails() -> None:
    bad = {**VALID_DRAFT, "allowed_operators": sorted(EXPECTED_OPERATORS | {"NEW_OP"})}
    config_path = _tmp_config(bad)
    seed_path = _tmp_seed([VALID_SEED])

    result = check_second_round_gate(config_path, seed_path)

    assert not result.passed
    assert any("NEW_OP" in f for f in result.failures)


def test_new_operator_in_actual_operators_fails() -> None:
    config_path = _tmp_config(VALID_DRAFT)
    seed_path = _tmp_seed([VALID_SEED])

    fake_operators = {**{k: v for k, v in []}, "NEW_OP": object()}
    result = check_second_round_gate(config_path, seed_path, operators={"NEW_OP": "fake"})

    assert not result.passed
    assert any("new_operators_detected" in f for f in result.failures)


# ---------- 测试 10: 搜索规模 ----------


def test_large_candidate_count_fails() -> None:
    bad = {
        **VALID_DRAFT,
        "generation": {"candidate_count": 10000},
    }
    config_path = _tmp_config(bad)
    seed_path = _tmp_seed([VALID_SEED])

    result = check_second_round_gate(config_path, seed_path)

    # 1 seed * 10 = 10 -> 比 10000 小得多, 应该 fail
    # 但实际上 check_search_scale 需要 seed_count > 0 and candidate_count > seed_count * 10
    # 这里 10000 > 1 * 10 = 10, 应该触发
    assert not result.passed
    assert any("large" in f.lower() or "candidate_count" in f.lower() for f in result.failures)


def test_large_backtest_limit_fails() -> None:
    bad = {
        **VALID_DRAFT,
        "full_backtest": {"limit": 100},
    }
    config_path = _tmp_config(bad)
    seed_path = _tmp_seed([VALID_SEED])

    result = check_second_round_gate(config_path, seed_path)

    assert not result.passed
    assert any("large_backtest_limit" in f for f in result.failures)


# ---------- 测试 11: 种子因子 manifest 本身验证 ----------


def test_requires_new_operator_seed_fails() -> None:
    config_path = _tmp_config(VALID_DRAFT)
    bad_seed = {
        **VALID_SEED,
        "seed_factor_id": "fp_bad_007",
        "requires_new_operator": True,
    }
    seed_path = _tmp_seed([bad_seed])

    result = check_second_round_gate(config_path, seed_path)

    assert not result.passed
    assert any("fp_bad_007" in f for f in result.failures)
    assert any("operator" in f.lower() for f in result.failures)


# ---------- 测试 12: 所有七个种子因子都通过检查 ----------


def test_all_seven_valid_seeds_pass() -> None:
    seeds = [
        {
            "seed_factor_id": f"fp_{tag}_{i:03d}",
            "factor_name_cn": f"因子{i}",
            "source_title": "Test source",
            "source_url_or_path": "https://example.com",
            "source_verified_by_firecrawl": True,
            "computability_class": "computable_with_current_data" if i <= 2 else "computable_with_minor_feature_derivation",
            "requires_new_external_data": False,
            "requires_new_operator": False,
            "suggested_for_second_batch_minimal_experiment": True,
        }
        for i, tag in enumerate(
            ["momentum_mid", "reversal_short", "low_vol", "downside_vol", "amount_liquidity", "price_volume_interaction", "multi_frequency_trend"],
            9,
        )
    ]
    config_path = _tmp_config(VALID_DRAFT)
    seed_path = _tmp_seed(seeds)

    result = check_second_round_gate(config_path, seed_path)

    # 即使有7个种子因子，也不应因种子因子本身而失败
    # 注意：如果 seed_count 不等于 7，会触发预警；这里正好是 7 所以没问题
    assert all("seed_factor_count_unexpected" not in f for f in result.failures)


# ---------- 测试 13: 空 manifest ----------


def test_empty_seed_manifest_fails() -> None:
    config_path = _tmp_config(VALID_DRAFT)
    seed_path = _tmp_seed([])

    result = check_second_round_gate(config_path, seed_path)

    assert not result.passed
    assert any("seed_manifest_empty" in f for f in result.failures)


# ---------- 测试 14: 操作策略引用 ----------


def test_operation_strategy_reference_missing_fails() -> None:
    config_path = _tmp_config(VALID_DRAFT)
    seed_path = _tmp_seed([VALID_SEED])

    result = check_second_round_gate(
        config_path, seed_path,
        operation_strategy_reference_path="/nonexistent/op_ref.jsonl",
    )

    assert not result.passed
    assert any("operation_strategy" in f for f in result.failures)
