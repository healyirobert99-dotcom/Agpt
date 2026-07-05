# AlphaGPT full pytest 失败归因与最小阻塞项修复报告

## 1. 本次任务边界

本次只做 full pytest 失败归因与第二轮搜索前最小阻塞项修复。

本次未搜索、未回测、未生成新公式、未启动第二轮搜索、未启动第二轮实验配置、未访问 forward data、未接入券商、未自动交易、未输出交易建议。新增特征仍仅为第二批最小实验候选种子因子的可计算基础特征。

## 2. 当前测试状态

已执行命令：

- `python -m pytest tests -ra`
- `python -m pytest tests/test_secret_safety.py`
- `python -m pytest tests/test_new_unseen_runner_checkpoint.py --basetemp D:\alphaGPT\tmp\pytest_new_unseen_runner`
- `python -m pytest tests/test_features_phase1.py`
- `python -m pytest tests/test_expression_executor_phase1.py`
- `python -m pytest tests`

日志保存状态：

- `D:\alphaGPT_runtime\research_intel\reports\full_pytest_failure_log.txt` 已保存本轮修复前的 `python -m pytest tests -ra` 完整失败日志。
- 修复后尝试覆盖保存该日志时，平台拒绝了写入 `D:\alphaGPT_runtime` 的提权请求；因此修复后 full pytest 最终结果以本次会话命令输出为准。

测试结果：

- `tests/test_features_phase1.py`：6 passed。
- `tests/test_expression_executor_phase1.py`：6 passed。
- `tests/test_secret_safety.py`：2 passed。
- `tests/test_new_unseen_runner_checkpoint.py --basetemp D:\alphaGPT\tmp\pytest_new_unseen_runner`：19 passed。
- 修复后 `python -m pytest tests`：238 collected；8 failed, 140 passed, 4 skipped, 86 errors in 22.71s。

## 3. 失败分类汇总

| 分类 | 数量 | 是否与新增特征/executor相关 | 是否阻塞第二轮搜索 | 处理方式 |
| -- | -: | ------------------ | --------- | ---- |
| recent_feature_or_executor_regression | 0 | 否 | 否 | 未发现。新增特征 targeted tests 与 executor targeted tests 均通过。 |
| missing_test_dependency | 0 | 否 | 否 | Windows `resource` 模块缺失已通过 heartbeat fallback 修复。 |
| missing_local_config_or_db | 7 | 否 | 条件阻塞 | 需要用户提供本地 config/DB 或恢复安全同步遗漏；本次不凭空补造配置或数据库。 |
| windows_temp_permission | 87 | 否 | 条件阻塞 | 默认 pytest temp 根目录权限异常及 `/tmp` Windows 权限问题；可用显式 `--basetemp` 验证相关代码路径。 |
| security_scan_false_positive | 0 | 否 | 否 | Firecrawl README 赋值示例已改为非赋值说明，安全测试已通过。 |
| missing_repo_file | 0 | 否 | 否 | 未发现可安全补回的公开轻量仓库文件；缺失 config/DB 按本地依赖处理。 |
| legacy_test_issue | 0 | 否 | 否 | 当前未单列。 |
| unknown | 0 | 否 | 否 | 当前无未知类。 |

## 4. 逐项失败明细

| 测试文件 | 测试名称 | 错误摘要 | 分类 | 是否已修复 | 是否仍阻塞 |
| ---- | ---- | ---- | -- | ----- | ----- |
| tests/test_provider_phase1.py | test_provider_filters_dates_symbols_and_batches | `stock-data/ashare_research.sqlite3` 无法打开 | missing_local_config_or_db | 否 | 条件阻塞 |
| tests/test_provider_phase1.py | test_trade_calendar_and_derived_boundaries | `stock-data/ashare_research.sqlite3` 无法打开 | missing_local_config_or_db | 否 | 条件阻塞 |
| tests/test_provider_phase1.py | test_csi800_asof_no_future_backfill | `stock-data/ashare_research.sqlite3` 无法打开 | missing_local_config_or_db | 否 | 条件阻塞 |
| tests/test_stage3_6d1_training_searcher_benchmark.py | test_validation_split_not_in_config | 缺少 `config/searcher_training_benchmark.yaml`；PyYAML 未安装后 fallback 仍需该文件 | missing_local_config_or_db | 否 | 条件阻塞 |
| tests/test_stage3_6d1_training_searcher_benchmark.py | test_blind_test_split_not_in_config | 缺少 `config/searcher_training_benchmark.yaml`；PyYAML 未安装后 fallback 仍需该文件 | missing_local_config_or_db | 否 | 条件阻塞 |
| tests/test_trade_recommendation_protocol_b_v1.py | test_build_weekly_schedule_116_days_not_116_signals | `stock-data/ashare_research.sqlite3` 无法打开 | missing_local_config_or_db | 否 | 条件阻塞 |
| tests/test_trade_recommendation_protocol_b_v1.py | test_config_equivalence | 缺少 `config/trade_recommendation_protocol_b_v1.yaml`；PyYAML 未安装后 fallback 仍需该文件 | missing_local_config_or_db | 否 | 条件阻塞 |
| tests/test_stage3_6d1_training_searcher_benchmark.py | test_interrupted_correctly_recovers | Windows `/tmp/_test_interrupt_recovery` 清理权限失败 | windows_temp_permission | 否 | 条件阻塞 |
| tests/test_backtest_end_to_end.py | test_manual_market_case_is_auditable_line_by_line | pytest 默认 temp 根 `C:\Users\Admin\AppData\Local\Temp\pytest-of-Admin` 权限失败 | windows_temp_permission | 否 | 条件阻塞 |
| tests/test_checkpoint_resume.py | test_checkpoint_round_trip_validates_hashes | pytest 默认 temp 根权限失败 | windows_temp_permission | 否 | 条件阻塞 |
| tests/test_factor_research_v2.py | test_checkpoint_hash_mismatch_rejects_resume | pytest 默认 temp 根权限失败 | windows_temp_permission | 否 | 条件阻塞 |
| tests/test_factor_research_v2.py | test_chinese_report_written | pytest 默认 temp 根权限失败 | windows_temp_permission | 否 | 条件阻塞 |
| tests/test_factor_research_v2.py | test_completed_run_resume_does_not_create_new_dir_or_registry_event | pytest 默认 temp 根权限失败 | windows_temp_permission | 否 | 条件阻塞 |
| tests/test_factor_research_v2.py | test_completed_run_resume_is_idempotent_twice | pytest 默认 temp 根权限失败 | windows_temp_permission | 否 | 条件阻塞 |
| tests/test_factor_research_v2.py | test_resume_rejects_config_hash_mismatch | pytest 默认 temp 根权限失败 | windows_temp_permission | 否 | 条件阻塞 |
| tests/test_factor_research_v2.py | test_resume_reuses_existing_fast_screen_results_without_rescreening | pytest 默认 temp 根权限失败 | windows_temp_permission | 否 | 条件阻塞 |
| tests/test_factor_research_v2.py | test_registry_event_idempotency_and_quarantine | pytest 默认 temp 根权限失败 | windows_temp_permission | 否 | 条件阻塞 |
| tests/test_factor_research_v2.py | test_run_creates_empty_errors_jsonl_and_uses_absolute_runs_root | pytest 默认 temp 根权限失败 | windows_temp_permission | 否 | 条件阻塞 |
| tests/test_factor_research_v2.py | test_run_uses_candidate_source_without_regeneration | pytest 默认 temp 根权限失败 | windows_temp_permission | 否 | 条件阻塞 |
| tests/test_factor_research_v2.py | test_pipeline_writes_candidate_status_and_respects_full_backtest_limit | pytest 默认 temp 根权限失败 | windows_temp_permission | 否 | 条件阻塞 |
| tests/test_factor_research_v2.py | test_diagnostic_report_uses_specific_reasons_and_recomputes_grade | pytest 默认 temp 根权限失败 | windows_temp_permission | 否 | 条件阻塞 |
| tests/test_factor_research_v2.py | test_revalidation_extracts_fixed_94_without_generator | pytest 默认 temp 根权限失败 | windows_temp_permission | 否 | 条件阻塞 |
| tests/test_formula_registry.py | test_registry_separates_runs_formulas_and_evaluations | pytest 默认 temp 根权限失败 | windows_temp_permission | 否 | 条件阻塞 |
| tests/test_forward_paper_runner.py | all tmp_path-dependent failing tests | pytest 默认 temp 根权限失败 | windows_temp_permission | 否 | 条件阻塞 |
| tests/test_immutable_freeze.py | all tmp_path-dependent failing tests | pytest 默认 temp 根权限失败 | windows_temp_permission | 否 | 条件阻塞 |
| tests/test_lifecycle_phase2.py | test_not_yet_listed_member_is_excluded_from_portfolio | pytest 默认 temp 根权限失败 | windows_temp_permission | 否 | 条件阻塞 |
| tests/test_mining_config.py | test_formal_mining_config_with_nulls_stops | pytest 默认 temp 根权限失败 | windows_temp_permission | 否 | 条件阻塞 |
| tests/test_mining_end_to_end.py | test_smoke_orchestrator_freezes_candidates_and_blind_results | pytest 默认 temp 根权限失败 | windows_temp_permission | 否 | 条件阻塞 |
| tests/test_new_unseen_runner_checkpoint.py | tmp_path-dependent setup failures in exact full run | pytest 默认 temp 根权限失败； with explicit basetemp: 19 passed | windows_temp_permission | 条件验证通过 | 条件阻塞 |
| tests/test_no_future_leakage_backtest.py | all failing tests | pytest 默认 temp 根权限失败 | windows_temp_permission | 否 | 条件阻塞 |
| tests/test_phase2_external_target_schedule.py | all failing tests | pytest 默认 temp 根权限失败 | windows_temp_permission | 否 | 条件阻塞 |
| tests/test_rebalance.py | test_rebalance_creates_multiple_signal_dates | pytest 默认 temp 根权限失败 | windows_temp_permission | 否 | 条件阻塞 |
| tests/test_resume_training_guards.py | test_completed_run_cannot_resume_training | pytest 默认 temp 根权限失败 | windows_temp_permission | 否 | 条件阻塞 |
| tests/test_signal_execution_alignment.py | test_signal_date_is_before_actual_trade_date | pytest 默认 temp 根权限失败 | windows_temp_permission | 否 | 条件阻塞 |
| tests/test_stage3_5_validation.py | tmp_path-dependent failing tests | pytest 默认 temp 根权限失败 | windows_temp_permission | 否 | 条件阻塞 |
| tests/test_stage3_6_search_benchmark.py | tmp_path-dependent failing test | pytest 默认 temp 根权限失败 | windows_temp_permission | 否 | 条件阻塞 |
| tests/test_stage3_6a_reward_observability.py | tmp_path-dependent failing test | pytest 默认 temp 根权限失败 | windows_temp_permission | 否 | 条件阻塞 |
| tests/test_stage3_6b_batch_context.py | all failing tests | pytest 默认 temp 根权限失败 | windows_temp_permission | 否 | 条件阻塞 |
| tests/test_stage3_6b_final_progress.py | tmp_path-dependent failing tests | pytest 默认 temp 根权限失败 | windows_temp_permission | 否 | 条件阻塞 |
| tests/test_stage3_6b_golden_baseline.py | all failing tests | pytest 默认 temp 根权限失败 | windows_temp_permission | 否 | 条件阻塞 |
| tests/test_stage3_6c2_completed_budget.py | tmp_path-dependent failing tests | pytest 默认 temp 根权限失败 | windows_temp_permission | 否 | 条件阻塞 |
| tests/test_stage3_6c2r_daily_bar_diagnosis.py | all failing tests | pytest 默认 temp 根权限失败 | windows_temp_permission | 否 | 条件阻塞 |
| tests/test_stage3_6d1_training_searcher_benchmark.py | tmp_path-dependent errors | pytest 默认 temp 根权限失败 | windows_temp_permission | 否 | 条件阻塞 |
| tests/test_stage3_6d2_candidate_freeze.py | tmp_path-dependent errors | pytest 默认 temp 根权限失败 | windows_temp_permission | 否 | 条件阻塞 |
| tests/test_stage3_6d3_frozen_candidate_validation.py | tmp_path-dependent errors | pytest 默认 temp 根权限失败 | windows_temp_permission | 否 | 条件阻塞 |
| tests/test_storage_safety_phase2.py | test_output_size_failure_cleans_temp_run_dir | pytest 默认 temp 根权限失败 | windows_temp_permission | 否 | 条件阻塞 |

## 5. 已修复内容

实际修复文件：

- `tools/firecrawl/README.md`
- `ashare_research/mining/new_unseen_runner.py`

修复内容：

- 将 Firecrawl README 中的 shell 环境变量赋值示例改为非赋值说明，避免安全扫描将文档示例误判为硬编码密钥。未降低安全检查，未修改测试。
- 将 `atomic_write_json` 从“写完后以只读 fd 执行 `os.fsync`”改为“写入文件句柄后 flush + fsync + replace”。这是 Windows 兼容修复，不改变输出 JSON 内容、不改变研究逻辑。
- 将 heartbeat 中的 `resource` 模块导入移入 try 块；Windows 无该模块时仅跳过内存占用字段，不影响 heartbeat 持久化。

验证：

- `tests/test_secret_safety.py`：2 passed。
- `tests/test_new_unseen_runner_checkpoint.py --basetemp D:\alphaGPT\tmp\pytest_new_unseen_runner`：19 passed。

## 6. 剩余问题

剩余问题不属于新增 11 个基础特征或 executor.py 兼容性改动引入的真实回归。

环境问题：

- 默认 pytest temp 根目录 `C:\Users\Admin\AppData\Local\Temp\pytest-of-Admin` 权限异常导致 86 个 setup error。
- Windows `/tmp` 路径权限导致 `test_interrupted_correctly_recovers` 失败。

缺 DB/config：

- 缺少 `stock-data/ashare_research.sqlite3`，影响 provider 与部分 protocol-b 测试。
- 缺少 `config/searcher_training_benchmark.yaml`。
- 缺少 `config/trade_recommendation_protocol_b_v1.yaml`。
- PyYAML 未安装，但当前报错最终落在缺配置文件；本次未安装依赖、未新增外部数据。

是否需要用户提供本地依赖：

- 是。若用户要求 full pytest 全绿，需要提供或恢复对应本地 DB/config，并修复默认 temp 目录权限或允许使用显式 `--basetemp` 运行。

是否阻塞第二轮搜索：

- 对“完整 full pytest 全绿”构成条件阻塞。
- 对“第二轮配置草案”不构成特征/executor 层阻塞，因为新增特征 targeted tests、executor targeted tests、安全扫描、checkpoint 局部验证均通过。

是否与本轮新增特征有关：

- 否。

## 7. 第二轮前测试就绪判断

second_round_test_ready: conditional

判断依据：核心相关测试通过；剩余失败均归因于本地 temp 权限、私有 DB/config 或外部依赖问题，未发现新增 11 个基础特征或 executor.py 兼容性改动引入真实回归。该状态不代表 full pytest 通过。

## 8. 禁止事项核查

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
- new_operator_added: false
- external_data_added: false
- forward_data_accessed: false
- trading_advice_generated: false
- next_stage_started: false
