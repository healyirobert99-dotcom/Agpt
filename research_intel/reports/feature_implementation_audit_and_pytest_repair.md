# AlphaGPT 新增基础特征实现审计与 pytest 修复报告

## 1. 本次任务边界

本次只执行新增基础特征实现审计、executor.py 兼容性审计，以及 full pytest 收集失败修复。

本次未搜索、未回测、未生成新公式、未启动第二批搜索、未启动第二批实验配置、未访问 forward data、未接入券商、未自动交易、未输出交易建议。新增特征仅作为第二批最小实验候选种子因子的可计算基础特征，不代表已经通过 AlphaGPT 本地回测验证。

## 2. 读取和修改文件

实际读取文件：

- ashare_research/factors/base_features.py
- ashare_research/factors/executor.py
- tests/test_features_phase1.py
- tests/test_expression_executor_phase1.py
- tests/test_factor_research_v2.py
- tools 目录现状

实际修改文件：

- tools/__init__.py
- tools/generate_factor_research_v2_diagnostics.py
- tools/revalidate_factor_research_v2_94.py
- research_intel/reports/feature_implementation_audit_and_pytest_repair.md
- D:\alphaGPT_runtime\research_intel\reports\feature_implementation_audit_and_pytest_repair.md

未修改文件：

- ashare_research/factors/base_features.py
- ashare_research/factors/executor.py
- ashare_research/factors/operators.py
- ashare_research/factors/vocabulary.py
- ashare_research/factor_research_v2/config.py
- ashare_research/factor_research_v2/pipeline.py
- fast_screen、robustness、full_backtest 相关实现

## 3. 新增 11 个基础特征审计

审计结论：11 个新增基础特征实现符合上一阶段方案边界；原有 5 个基础特征仍保留，未发现未来函数风险。

| 特征 | 审计结论 | 说明 |
| --- | --- | --- |
| RET20 | 通过 | 基于按 ts_code 分组并按 trade_date 排序后的 close.pct_change(20)，只使用历史收盘价。 |
| RET60 | 通过 | 基于 close.pct_change(60)，只使用历史收盘价。 |
| RET120 | 通过 | 基于 close.pct_change(120)，只使用历史收盘价。 |
| RET_STD20 | 通过 | 基于 RET1 的 rolling(20).std(ddof=0)，只使用当前日及之前收益率，warm-up 不足为缺失。 |
| RET_STD60 | 通过 | 基于 RET1 的 rolling(60).std(ddof=0)，只使用当前日及之前收益率，warm-up 不足为缺失。 |
| DOWNSIDE_RET_STD20 | 通过 | 基于 RET1；负收益保留，非负收益置 0，RET1 缺失保持缺失；rolling(20).std(ddof=0)。无负收益窗口在 warm-up 后结果为 0。 |
| DOWNSIDE_RET_STD60 | 通过 | 与 DOWNSIDE_RET_STD20 逻辑一致，窗口为 60。无负收益窗口在 warm-up 后结果为 0。 |
| AMOUNT_MA20 | 通过 | required 列包含真实 amount 字段，使用 amount.rolling(20).mean()；未用 volume 或价格合成替代。 |
| AMOUNT_MA60 | 通过 | required 列包含真实 amount 字段，使用 amount.rolling(60).mean()；未用 volume 或价格合成替代。 |
| TREND20 | 通过 | 与 TREND60 相同逻辑，只改变 rolling mean 窗口为 20。 |
| TREND120 | 通过 | 与 TREND60 相同逻辑，只改变 rolling mean 窗口为 120。 |

原有 5 个基础特征检查：

- RET1：保留。
- RET5：保留。
- VOL_RATIO20：保留。
- VOLUME_WEIGHTED_RET：保留。
- TREND60：保留，逻辑未被本次审计修复改动。

warm-up 和缺失值处理：沿用项目既有 rolling/pct_change 行为，窗口不足时产生缺失；基础特征统一在末尾将 inf/-inf 替换为 NaN。按 ts_code 分组、trade_date 排序后计算，未发现使用未来行的实现。

## 4. executor.py 兼容性审计

改动原因：BASE_FEATURES 扩展到 16 个后，如果 executor 继续要求输入数据包含全部 BASE_FEATURES，会导致只引用旧特征的旧公式也必须提供 11 个新列，破坏旧公式执行夹具和兼容性。因此上一阶段将输入列检查收窄为当前公式实际依赖的基础特征。

改动范围：只影响公式执行前的依赖特征集合识别、required columns 检查，以及 env 中注入的基础特征列。公式合法性校验、表达式解析、算子实现、算子执行语义、action mask、vocabulary 均未改变。

缺失依赖识别：如果公式引用了某个基础特征而输入 features 缺少该列，executor 仍返回 invalid，并报告 missing_columns；未用 NaN、0 或其他默认值替代缺失特征。

旧公式结果影响：对只依赖旧基础特征的旧公式，env 中对应 Series 的值来源不变，计算路径不变；本次审计未发现旧公式计算结果会因该兼容性改动而改变。

执行语义：未发现绕过公式合法性校验、改变算子语义、改变公式解析逻辑或改变 vocabulary/action mask 的情况。

## 5. full pytest 收集失败原因与修复

失败原因：full pytest 收集阶段导入 tests/test_factor_research_v2.py 时，项目缺少 tools.generate_factor_research_v2_diagnostics 模块。进一步检查发现同一测试文件还依赖 tools.revalidate_factor_research_v2_94。tools 目录中仅存在 firecrawl 子目录，缺少 tools 包初始化文件和上述两个测试依赖模块。

修复方式：补回最小 tools 包与测试所需模块：

- 新增 tools/__init__.py，使 tools 可作为包导入。
- 新增 tools/generate_factor_research_v2_diagnostics.py，提供 generate_diagnostics 测试入口，读取测试构造的 run 目录并输出诊断 csv/markdown。
- 新增 tools/revalidate_factor_research_v2_94.py，提供 tests/test_factor_research_v2.py 所需的 _window_results、_final_grade、extract_deduplicated_inputs。

修复边界：未跳过测试，未删除测试，未修改业务 pipeline/config/筛选/评级/回测逻辑。新增模块仅用于恢复测试依赖入口和诊断工具入口。

安全同步遗漏判断：从现状看，full pytest 收集失败属于 tools 下必要测试支持模块缺失；该问题与新增基础特征本身无直接关系，但会阻断完整测试进入执行阶段。

修复后状态：tests/test_factor_research_v2.py 能完成收集并进入执行；python -m pytest tests 能完成全量收集并进入真实测试执行阶段。

## 6. 测试结果

已运行 targeted pytest：

- python -m pytest tests/test_features_phase1.py：6 passed in 1.78s
- python -m pytest tests/test_expression_executor_phase1.py：6 passed in 0.52s

已运行 full pytest：

- python -m pytest tests
- 结果：9 failed, 139 passed, 4 skipped, 86 errors in 23.39s
- 阶段：已通过收集阶段，进入测试 setup/执行阶段后失败。

full pytest 主要失败原因：

- Windows 临时目录权限错误：C:\Users\Admin\AppData\Local\Temp\pytest-of-Admin 多处 PermissionError，影响使用 tmp_path 的测试。
- 环境/夹具缺失：config/searcher_training_benchmark.yaml、config/trade_recommendation_protocol_b_v1.yaml、stock-data/ashare_research.sqlite3 等测试依赖文件不存在。
- 依赖缺失或环境差异：部分测试提示 PyYAML 不可用后走 fallback，但对应 config 文件仍缺失。
- 既有敏感词扫描测试失败：tools\\firecrawl\\README.md 中存在 Firecrawl 环境变量赋值示例字样。
- Windows /tmp 路径权限导致 test_interrupted_correctly_recovers 失败。

关联性判断：上述 full pytest 执行阶段失败与本次新增基础特征实现、executor.py 兼容性改动无直接关系；原始的 missing tools.generate_factor_research_v2_diagnostics 收集失败已修复。

## 7. 禁止事项核查

- new_formula_generated: false
- new_factor_search_started: false
- new_backtest_run: false
- fast_screen_modified: false
- robustness_modified: false
- full_backtest_modified: false
- pipeline_modified: false
- config_modified: false
- threshold_changed: false
- rating_rule_changed: false
- new_operator_added: false
- external_data_added: false
- forward_data_accessed: false
- trading_advice_generated: false
- next_stage_started: false


