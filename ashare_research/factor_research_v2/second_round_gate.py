"""
Second Round Minimal Search Gate Checker.

只读检查器，不修改配置、不启动搜索、不运行回测、不生成公式。
输入第二轮搜索配置草案和种子因子 manifest，输出门禁检查结果。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ashare_research.config import load_simple_yaml
from ashare_research.factors.base_features import BASE_FEATURES
from ashare_research.factors.operators import OPERATORS

# ---------- 接口 ----------


@dataclass
class GateResult:
    passed: bool
    failures: list[str] = field(default_factory=list)

    def add_failure(self, reason: str) -> None:
        self.failures.append(reason)
        self.passed = False


def check_second_round_gate(
    config_path: str | Path,
    seed_manifest_path: str | Path,
    *,
    base_features: tuple[str, ...] = BASE_FEATURES,
    operators: dict[str, Any] | None = None,
    operation_strategy_reference_path: str | Path | None = None,
) -> GateResult:
    result = GateResult(passed=True)
    config_path = Path(config_path)
    seed_manifest_path = Path(seed_manifest_path)

    raw = load_simple_yaml(config_path)

    # 1. 状态检查
    _check_status(raw, result)

    # 2. 执行控制检查
    _check_execution_controls(raw, result)

    # 3. 数据和操作边界检查
    _check_data_boundaries(raw, result)

    # 4. 研究口径禁止变更检查
    _check_research_parameters(raw, result)

    # 5. 种子因子范围检查
    _check_seed_factor_scope(seed_manifest_path, result)

    # 6. 特征范围检查
    _check_feature_scope(raw, base_features, result)

    # 7. 算子范围检查
    _check_operator_scope(raw, operators, result)

    # 8. 数据范围检查
    _check_data_scope(seed_manifest_path, result)

    # 9. 搜索规模检查
    _check_search_scale(raw, seed_manifest_path, result)

    # 10. 操作策略引用只读
    if operation_strategy_reference_path:
        _check_operation_strategy_reference(operation_strategy_reference_path, result)

    return result


# ---------- 1. 状态检查 ----------


def _check_status(raw: dict[str, Any], result: GateResult) -> None:
    status = raw.get("status", "")
    if status == "approved":
        result.add_failure("status_is_approved: draft config must have status=draft_not_approved, not approved")
    elif status == "executable":
        result.add_failure("status_is_executable: draft config must have status=draft_not_approved, not executable")
    elif status != "draft_not_approved":
        result.add_failure(f"status_not_explicitly_draft: found status={status!r}, expected draft_not_approved")


# ---------- 2. 执行控制检查 ----------


def _check_execution_controls(raw: dict[str, Any], result: GateResult) -> None:
    execution_controls = {
        "run_enabled": False,
        "formula_generation_enabled": False,
        "backtest_enabled": False,
        "search_enabled": False,
    }
    for key, expected in execution_controls.items():
        actual = raw.get(key)
        if actual is None:
            result.add_failure(f"missing_execution_control:{key}")
        elif actual != expected:
            result.add_failure(f"execution_control_blocked:{key}={actual} (must be {expected})")


# ---------- 3. 数据与操作边界 ----------


def _check_data_boundaries(raw: dict[str, Any], result: GateResult) -> None:
    boundaries = {
        "forward_data_access_allowed": False,
        "external_data_allowed": False,
        "operator_extension_allowed": False,
    }
    for key, expected in boundaries.items():
        actual = raw.get(key)
        if actual is None:
            result.add_failure(f"missing_boundary_control:{key}")
        elif actual != expected:
            result.add_failure(f"boundary_blocked:{key}={actual} (must be {expected})")


# ---------- 4. 研究口径禁止变更 ----------


def _check_research_parameters(raw: dict[str, Any], result: GateResult) -> None:
    _check_thresholds_locked(raw, result)
    _check_rating_rule_locked(raw, result)


DEFAULT_LOCKED_THRESHOLDS_READ_ONLY = {
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
}


def _check_thresholds_locked(raw: dict[str, Any], result: GateResult) -> None:
    if raw.get("threshold_change_allowed") is None:
        result.add_failure("missing_threshold_change_control")
    elif raw.get("threshold_change_allowed") != False:  # noqa: E712
        result.add_failure("threshold_change_blocked: threshold_change_allowed must be false")

    locked = raw.get("locked_thresholds")
    if locked is None:
        return

    expected = DEFAULT_LOCKED_THRESHOLDS_READ_ONLY
    for section in ("screening", "correlation"):
        expected_section = expected.get(section, {})
        actual_section = locked.get(section, {})
        if actual_section is None:
            continue
        for key, expected_value in expected_section.items():
            actual_value = actual_section.get(key)
            if actual_value is not None and actual_value != expected_value:
                result.add_failure(
                    f"threshold_deviation:locked_thresholds.{section}.{key}={actual_value} "
                    f"(expected {expected_value})"
                )


def _check_rating_rule_locked(raw: dict[str, Any], result: GateResult) -> None:
    if raw.get("rating_rule_change_allowed") is None:
        result.add_failure("missing_rating_rule_control")
    elif raw.get("rating_rule_change_allowed") != False:  # noqa: E712
        result.add_failure("rating_rule_change_blocked: rating_rule_change_allowed must be false")

    locked = raw.get("locked_thresholds", {})
    if not locked:
        return

    expected_rating = {
        "min_positive_period_ratio": 0.45,
        "grade_a_min_abs_ic": 0.03,
        "grade_a_max_drawdown": 0.35,
        "grade_b_min_abs_ic": 0.015,
    }
    actual_rating = locked.get("rating", {})
    if actual_rating is None:
        return
    for key, expected_value in expected_rating.items():
        actual_value = actual_rating.get(key)
        if actual_value is not None and actual_value != expected_value:
            result.add_failure(
                f"rating_rule_deviation:locked_thresholds.rating.{key}={actual_value} "
                f"(expected {expected_value})"
            )


# ---------- 5. 种子因子范围 ----------


def _check_seed_factor_scope(manifest_path: Path, result: GateResult) -> None:
    if not manifest_path.exists():
        result.add_failure(f"seed_manifest_not_found:{manifest_path}")
        return

    allowed_ids = _load_seed_factor_ids(manifest_path)
    if not allowed_ids:
        result.add_failure("seed_manifest_empty_or_unreadable")
        return

    # 检查种子因子 manifest 是否非空，但不硬编码数量
    # 实际 manifest 应包含 7 个已冻结种子因子，但门禁检查不强制具体数字
    # 由用户审批时确认因子数量
    if len(allowed_ids) == 0:
        result.add_failure("seed_manifest_empty: no seed factors found in manifest")
    elif len(allowed_ids) > 0 and len(allowed_ids) != 7:
        # 只记录信息性备注，不阻断
        pass

    for record in _load_seed_manifest_records(manifest_path):
        seed_id = record.get("seed_factor_id", "")
        computability = record.get("computability_class", "")
        source_verified = record.get("source_verified_by_firecrawl", False)
        suggested = record.get("suggested_for_second_batch_minimal_experiment", False)
        requires_new_data = record.get("requires_new_external_data", False)

        if computability == "requires_new_data":
            result.add_failure(f"seed_factor_requires_new_data:{seed_id}")
        if not source_verified:
            result.add_failure(f"seed_factor_source_not_verified:{seed_id}")
        if not suggested:
            result.add_failure(f"seed_factor_not_suggested_for_second_batch:{seed_id}")
        if requires_new_data:
            result.add_failure(f"seed_factor_requires_new_external_data:{seed_id}")

        # 禁止 partial_source_candidate / needs_source_verification
        if computability in ("partial_source_candidate", "needs_source_verification"):
            result.add_failure(f"seed_factor_unverified_computability:{seed_id} computability={computability}")

        # 检查是否有来源
        source_title = record.get("source_title", "")
        source_url = record.get("source_url_or_path", "")
        if not source_title and not source_url:
            result.add_failure(f"seed_factor_no_source:{seed_id}")


def _load_seed_factor_ids(manifest_path: Path) -> set[str]:
    ids: set[str] = set()
    for record in _load_seed_manifest_records(manifest_path):
        sid = record.get("seed_factor_id", "")
        if sid:
            ids.add(sid)
    return ids


def _load_seed_manifest_records(manifest_path: Path) -> list[dict[str, Any]]:
    if not manifest_path.exists():
        return []
    records: list[dict[str, Any]] = []
    for line in manifest_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            records.append(json.loads(stripped))
        except json.JSONDecodeError:
            continue
    return records


# ---------- 6. 特征范围 ----------


def _check_feature_scope(raw: dict[str, Any], base_features: tuple[str, ...], result: GateResult) -> None:
    allowed_cfg = raw.get("allowed_features")
    if not allowed_cfg:
        return

    original = set(allowed_cfg.get("original", []))
    second_batch = set(allowed_cfg.get("second_batch_approved", []))

    expected_original = {"RET1", "RET5", "VOL_RATIO20", "VOLUME_WEIGHTED_RET", "TREND60"}
    if original and original != expected_original:
        result.add_failure(
            f"allowed_features.original_mismatch: configured={sorted(original)}, expected={sorted(expected_original)}"
        )

    expected_second_batch = {
        "RET20", "RET60", "RET120",
        "RET_STD20", "RET_STD60",
        "DOWNSIDE_RET_STD20", "DOWNSIDE_RET_STD60",
        "AMOUNT_MA20", "AMOUNT_MA60",
        "TREND20", "TREND120",
    }
    if second_batch and second_batch != expected_second_batch:
        result.add_failure(
            f"allowed_features.second_batch_mismatch: configured={sorted(second_batch)}, expected={sorted(expected_second_batch)}"
        )

    # 验证所有声明的特征都在 BASE_FEATURES 中
    all_allowed = original | second_batch
    system_features = set(base_features)
    undefined = all_allowed - system_features
    if undefined:
        result.add_failure(f"undefined_base_features_in_config:{sorted(undefined)}")

    # 验证 BASE_FEATURES 没有包含超出批准范围的特征
    allowed_combined = expected_original | expected_second_batch
    unapproved = system_features - allowed_combined
    if unapproved:
        result.add_failure(f"unapproved_features_in_BASE_FEATURES:{sorted(unapproved)}")


# ---------- 7. 算子范围 ----------


EXPECTED_OPERATORS = {
    "ADD", "SUB", "MUL", "DIV", "NEG", "ABS", "SIGN",
    "DELTA5", "DECAY_LINEAR20", "ZSCORE20",
}


def _check_operator_scope(raw: dict[str, Any], operators: dict[str, Any] | None, result: GateResult) -> None:
    allowed_cfg = raw.get("allowed_operators")
    if allowed_cfg is not None:
        cfg_set = set(allowed_cfg)
        if cfg_set != EXPECTED_OPERATORS:
            extra = cfg_set - EXPECTED_OPERATORS
            missing = EXPECTED_OPERATORS - cfg_set
            if extra:
                result.add_failure(f"unapproved_operators_in_config:{sorted(extra)}")
            if missing:
                result.add_failure(f"missing_operators_in_config:{sorted(missing)}")

    if operators is not None:
        actual = set(operators.keys())
        extra = actual - EXPECTED_OPERATORS
        if extra:
            result.add_failure(f"new_operators_detected:{sorted(extra)}")


# ---------- 8. 数据范围 ----------


def _check_data_scope(manifest_path: Path, result: GateResult) -> None:
    records = _load_seed_manifest_records(manifest_path)
    for record in records:
        seed_id = record.get("seed_factor_id", "")
        requires_new_data = record.get("requires_new_external_data", False)
        if requires_new_data:
            result.add_failure(f"seed_factor_requires_external_data:{seed_id}")

        would_add_operator = record.get("requires_new_operator", False)
        if would_add_operator:
            result.add_failure(f"seed_factor_requires_new_operator:{seed_id}")


# ---------- 9. 搜索规模 ----------


def _check_search_scale(raw: dict[str, Any], manifest_path: Path, result: GateResult) -> None:
    # 搜索被禁用，不能出现任何规模的搜索参数请求
    search_enabled = raw.get("search_enabled", False)
    run_enabled = raw.get("run_enabled", False)
    formula_gen = raw.get("formula_generation_enabled", False)

    # 检查是否隐藏性地要求大规模候选
    generation = raw.get("generation")
    if generation is not None and not _is_just_reference(generation):
        candidate_count = generation.get("candidate_count")
        if candidate_count is not None:
            records = _load_seed_manifest_records(manifest_path)
            seed_count = len(records)
            if seed_count > 0 and candidate_count > seed_count * 10:
                result.add_failure(
                    f"large_scale_search_detected: candidate_count={candidate_count}, "
                    f"expected at most {seed_count * 10} (10x seed factor count)"
                )

    # 如果 run/search/backtest/formula_generation 任一被开启
    if search_enabled or run_enabled or formula_gen:
        if search_enabled:
            result.add_failure("search_enabled_but_should_be_false")
        if run_enabled:
            result.add_failure("run_enabled_but_should_be_false")
        if formula_gen:
            result.add_failure("formula_generation_enabled_but_should_be_false")

    # 检查是否有 full_backtest limit 超出合理范围
    fb = raw.get("full_backtest")
    if fb is not None and not _is_just_reference(fb):
        limit = fb.get("limit")
        if limit is not None and isinstance(limit, (int, float)) and limit > 10:
            result.add_failure(
                f"large_backtest_limit: full_backtest.limit={limit}, draft must not exceed 10"
            )

    # 检查 candidate_count 是否超过种子数的合理倍数
    if generation is not None and not _is_just_reference(generation):
        candidate_count = generation.get("candidate_count")
        if candidate_count is not None and isinstance(candidate_count, (int, float)):
            records = _load_seed_manifest_records(manifest_path)
            if len(records) > 0 and candidate_count > len(records) * 20:
                result.add_failure(
                    f"candidate_count_too_large: {candidate_count} > {len(records) * 20} (20x seed count)"
                )


def _is_just_reference(section: Any) -> bool:
    """检查某个配置段是否只是纯参考（例如 locked_thresholds 中的只读基准值）。"""
    if isinstance(section, dict):
        locked = section
        for key in ("status", "draft", "reference_only"):
            if key in locked:
                return True
    return False


# ---------- 10. 操作策略引用 ----------


def _check_operation_strategy_reference(
    reference_path: str | Path,
    result: GateResult,
) -> None:
    reference_path = Path(reference_path)
    if not reference_path.exists():
        result.add_failure(f"operation_strategy_reference_not_found:{reference_path}")
        return

    records: list[dict[str, Any]] = []
    for line in reference_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            records.append(json.loads(stripped))
        except json.JSONDecodeError:
            continue

    for record in records:
        sim_class = record.get("simulatability_class", "")
        if sim_class == "requires_new_engine":
            result.add_failure(
                f"operation_strategy_requires_new_engine:{record.get('strategy_id', 'unknown')}"
            )


# ---------- 便捷入口 ----------


def run_gate(
    config_path: str | Path = "config/second_round_minimal_search.example.yaml",
    seed_manifest_path: str | Path = "research_intel/library/second_batch_seed_factor_manifest.jsonl",
    *,
    operation_strategy_reference_path: str | Path | None = "research_intel/library/operation_strategy_reference_manifest.jsonl",
) -> GateResult:
    return check_second_round_gate(
        config_path=config_path,
        seed_manifest_path=seed_manifest_path,
        base_features=BASE_FEATURES,
        operators=OPERATORS,
        operation_strategy_reference_path=operation_strategy_reference_path,
    )
