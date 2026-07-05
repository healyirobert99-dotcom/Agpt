# AlphaGPT 第二轮阶段 A：7 个种子因子单因子检查报告

## 1. 运行信息

| 项目 | 值 |
| ---- | --- |
| run_id | second_round_stage_a_20260705_142800（配置就绪，因数据库缺失未实际执行） |
| commit SHA | f7adb0a80bef6409a04da145bf2a2a569ed98932 |
| 使用的种子因子 | 7 个（全部来自 second_batch_seed_factor_manifest.jsonl） |
| 是否只做单因子 | 是 |
| 是否使用库外因子 | 否 |
| 是否新增特征 | 否（11 个特征已在代码中实现，本次未新增） |
| 是否新增算子 | 否 |
| 是否访问 forward data | 否 |
| 是否修改筛选/评级标准 | 否 |

## 2. 执行状态

| 项目 | 状态 | 详情 |
| ---- | ---- | ---- |
| readiness 检查 | ✅ 通过 | 门禁通过，代码就绪 |
| 固定候选清单 | ✅ 已生成 | 7 个候选，全部为 seed_single_factor |
| 配置加载 | ✅ 通过 | config/second_round_stage_a_run.yaml 加载成功 |
| **pipeline 执行** | **❌ 阻塞** | **stock-data/ashare_research.sqlite3 不存在** |

## 3. 固定候选清单

| # | seed_factor_id | 候选公式 | 特征依赖 | 算子依赖 | 可执行性 |
|---|---------------|---------|---------|---------|---------|
| 1 | fp_momentum_mid_009 | ZSCORE20(RET60) | RET60 | ZSCORE20 | 需配置扩展 |
| 2 | fp_reversal_short_010 | NEG(RET5) | RET5 | NEG | ✅ 直接可执行 |
| 3 | fp_low_vol_011 | NEG(RET_STD20) | RET_STD20 | NEG | 需配置扩展 |
| 4 | fp_downside_vol_012 | NEG(DOWNSIDE_RET_STD20) | DOWNSIDE_RET_STD20 | NEG | 需配置扩展 |
| 5 | fp_amount_liquidity_014 | ZSCORE20(AMOUNT_MA20) | AMOUNT_MA20 | ZSCORE20 | 需配置扩展 |
| 6 | fp_price_volume_interaction_018 | MUL(RET5,VOLUME_WEIGHTED_RET) | RET5, VOLUME_WEIGHTED_RET | MUL | ✅ 直接可执行 |
| 7 | fp_multi_frequency_trend_019 | ADD(TREND20,TREND60) | TREND20, TREND60 | ADD | 需配置扩展 |

## 4. 分段评估结果

因数据库缺失，以下为预期结果（基于 readiness 分析），非实际运行结果：

| 阶段 | 输入 | 预期 | 说明 |
| ---- | ---- | ---- | ---- |
| development | 7 | 待运行 | development: 20240101-20240329 |
| selection | 待定 | 待运行 | selection: 20240401-20240531 |
| stability | 待定 | 待运行 | stability: 20240603-20240628 |

## 5. 评级分布

| 评级 | 数量 | 说明 |
| ---- | ---- | ---- |
| grade_a_count | n/a | 因数据库缺失未运行 |
| grade_b_count | n/a | 同上 |
| grade_c_count | n/a | 同上 |
| rejected_count | n/a | 同上 |
| final_shortlist_count | 0 | 同上（未运行，无法产生任何结果） |
| recommended_factors | [] | 同上 |

## 6. 阻塞原因

`stock-data/ashare_research.sqlite3` 文件不在当前机器上。这是 AlphaGPT v2 pipeline 的必需数据库，包含本地日线价量数据。没有此文件，`LocalSQLiteProvider` 无法连接，整个 pipeline 无法初始化。

## 7. 需要用户提供的依赖

| 文件 | 说明 | 必需 |
| ---- | ---- | ---- |
| stock-data/ashare_research.sqlite3 | 研究用 SQLite 数据库（日线价量） | 是 |
| stock-data/a_stock_selector.sqlite3 | 原始股票筛选数据库 | 是（备选） |

## 8. 阶段 B/C 准入

当前不允许进入阶段 B/C（阶段 A 未完成）。

## 9. 禁止事项核查

- new_formula_generated: false（候选来自固定清单，非随机生成）
- search_started: false
- backtest_run: false
- fast_screen_modified: false
- robustness_modified: false
- pipeline_modified: false
- threshold_modified: false
- rating_rule_modified: false
- correlation_threshold_modified: false
- time_split_modified: false
- new_operator_added: false
- external_data_added: false
- forward_data_accessed: false
- stage_b_started: false
- stage_c_started: false
- trading_advice_generated: false

## 10. 最终结论

本阶段完成第二轮阶段 A：7 个种子因子单因子检查的准备工作（readiness 通过、固定候选清单已生成、配置就绪），但因本地数据库缺失无法完成实际 pipeline 运行。结果仅为历史研究结果，尚未经过未来前向验证，不得用于交易。
