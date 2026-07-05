# AlphaGPT 第二轮最小搜索配置草案与门禁检查器

## 1. 本次任务边界

本次只实现第二轮最小搜索的"配置草案与门禁检查器"。目的：在真正批准第二轮搜索前，先让代码层面能检查所有必须遵守的约束条件。

本次未启动搜索，未运行回测，未生成新公式，未修改筛选/评级/回测逻辑，未访问 forward data。

## 2. 交付清单

| 文件 | 说明 | 状态 |
| ---- | ---- | ---- |
| `config/second_round_minimal_search.example.yaml` | 第二轮最小搜索配置草案模板 | 已生成 |
| `ashare_research/factor_research_v2/second_round_gate.py` | 门禁检查器 | 已实现 |
| `tests/test_second_round_gate.py` | 门禁检查器测试（33 项） | 已实现 |
| `docs/reports/second_round_minimal_search_gate.md` | 本文档 | 已生成 |

## 3. 配置草案说明

`config/second_round_minimal_search.example.yaml` 是一个只表达"待审批草案"的配置模板，所有关键字段均设置为禁止执行：

```yaml
status: draft_not_approved      # 状态：草案未批准
run_enabled: false              # 禁止运行
formula_generation_enabled: false   # 禁止公式生成
backtest_enabled: false         # 禁止回测
search_enabled: false           # 禁止搜索
forward_data_access_allowed: false  # 禁止访问 forward data
external_data_allowed: false    # 禁止外部数据
operator_extension_allowed: false   # 禁止新增算子
threshold_change_allowed: false # 禁止修改阈值
rating_rule_change_allowed: false   # 禁止修改评级规则
```

该配置还包含只读基准值：
- `allowed_features`: 5 个原有基础特征 + 11 个已批准第二批基础特征
- `allowed_operators`: 10 个现有算子
- `locked_thresholds`: 当前锁定阈值和评级规则抄本
- `allowed_scope`: 仅允许种子单因子、种子配对经济组合、同族窄派生

## 4. 门禁检查器覆盖的场景

门禁检查器 `second_round_gate.py` 检查以下 10 大类场景：

### 4.1 状态检查
- 配置 status 必须为 `draft_not_approved`
- 禁止 `approved`、`executable` 等已批准状态

### 4.2 执行控制检查
- `run_enabled` 必须为 `false`
- `formula_generation_enabled` 必须为 `false`
- `backtest_enabled` 必须为 `false`
- `search_enabled` 必须为 `false`

### 4.3 数据与操作边界
- `forward_data_access_allowed` 必须为 `false`
- `external_data_allowed` 必须为 `false`
- `operator_extension_allowed` 必须为 `false`

### 4.4 研究口径禁止变更
- `threshold_change_allowed` 必须为 `false`
- `rating_rule_change_allowed` 必须为 `false`
- locked_thresholds 中的 screening/correlation/rating 值不能偏离当前锁定值

### 4.5 种子因子范围
- manifest 文件必须存在
- 禁止 `computability_class` 为 `requires_new_data`
- 禁止 `source_verified_by_firecrawl` 为 `false`
- 禁止 `suggested_for_second_batch_minimal_experiment` 为 `false`
- 禁止 `computability_class` 为 `partial_source_candidate` 或 `needs_source_verification`
- 禁止无来源因子
- 禁止 `requires_new_external_data` 为 `true`
- 禁止 `requires_new_operator` 为 `true`

### 4.6 特征范围
- 配置声明的特征必须全部在 BASE_FEATURES 中
- BASE_FEATURES 不能包含超出已批准范围的特征

### 4.7 算子范围
- 配置声明的算子必须与当前 10 个算子完全匹配
- 实际 OPERATORS 字典中不能有新增算子

### 4.8 数据范围
- 种子因子不能要求新增外部数据
- 种子因子不能要求新增算子

### 4.9 搜索规模
- 禁止大规模 candidate_count（超过种子因子数 20 倍）
- 禁止 large backtest limit（超过 10）
- 如果 search/run/formula_generation 任一被开启则失败

### 4.10 操作策略引用
- 引用文件必须存在
- 策略不能要求 `requires_new_engine`

## 5. 测试结果

### 5.1 test_second_round_gate.py

```
33 passed in 0.62s
```

覆盖场景：

| # | 测试名称 | 场景 |
|---|---------|------|
| 1 | test_valid_draft_passes_gate | 合法草案通过 |
| 2 | test_approved_status_fails | 已批准状态失败 |
| 3 | test_executable_status_fails | 可执行状态失败 |
| 4 | test_missing_status_fails | 缺少状态字段失败 |
| 5-8 | test_execution_control_enabled_fails | 四种执行控制被开启均失败 |
| 9 | test_missing_execution_control_fails | 缺少执行控制字段失败 |
| 10-12 | test_boundary_allowed_fails | 三种边界控制被开启均失败 |
| 13 | test_missing_boundary_control_fails | 缺少边界控制字段失败 |
| 14 | test_threshold_change_allowed_fails | 阈值变更标记开启失败 |
| 15 | test_threshold_deviation_fails | 阈值偏离锁定值失败 |
| 16 | test_rating_rule_change_allowed_fails | 评级变更标记开启失败 |
| 17 | test_rating_rule_deviation_fails | 评级规则偏离锁定值失败 |
| 18 | test_seed_manifest_not_found_fails | manifest 不存在失败 |
| 19 | test_requires_new_external_data_seed_fails | 要求外部数据种子失败 |
| 20 | test_source_not_verified_seed_fails | 来源未验证种子失败 |
| 21 | test_not_suggested_for_second_batch_fails | 不建议第二批种子失败 |
| 22 | test_unverified_computability_fails | 未验证可计算性种子失败 |
| 23 | test_no_source_seed_fails | 无来源种子失败 |
| 24 | test_requires_new_data_seed_in_manifest_fails | 要求新数据可计算性失败 |
| 25 | test_undefined_feature_in_config_fails | 未定义特征失败 |
| 26 | test_new_operator_in_config_fails | 配置新增算子失败 |
| 27 | test_new_operator_in_actual_operators_fails | 实际算子集新增失败 |
| 28 | test_large_candidate_count_fails | 大规模候选计数失败 |
| 29 | test_large_backtest_limit_fails | 大规模回测限制失败 |
| 30 | test_requires_new_operator_seed_fails | 种子要求新算子失败 |
| 31 | test_all_seven_valid_seeds_pass | 7 个合法种子全部通过 |
| 32 | test_empty_seed_manifest_fails | 空 manifest 失败 |
| 33 | test_operation_strategy_reference_missing_fails | 策略引用缺失失败 |

### 5.2 原有 targeted tests

```
test_features_phase1.py:             6 passed
test_expression_executor_phase1.py:  6 passed
```

原有 targeted tests 全部通过，新增门禁检查器代码未破坏任何已有功能。

## 6. full pytest 状态

未运行 full pytest。当前不要求 full pytest 全绿（已知 87 个 windows_temp_permission + 7 个 missing_local_config_or_db 失败不是本轮引入）。如需运行，结果将如实报告。

## 7. 禁止事项核查

- new_formula_generated: false
- new_factor_search_started: false
- new_backtest_run: false
- fast_screen_modified: false
- robustness_modified: false
- full_backtest_modified: false
- pipeline_modified: false
- config_research_semantics_modified: false
- threshold_changed: false
- rating_rule_changed: false
- correlation_threshold_changed: false
- time_split_changed: false
- new_operator_added: false
- external_data_added: false
- forward_data_accessed: false
- trading_advice_generated: false
- next_stage_started: false

## 8. 最终结论

本阶段完成第二轮最小搜索配置草案与门禁检查器。尚未批准搜索，尚未生成公式，尚未回测，所有因子仍不得用于交易。
