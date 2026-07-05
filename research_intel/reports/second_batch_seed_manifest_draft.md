# AlphaGPT 第二批最小实验种子清单冻结草案

## 1. 本次任务边界

本次只冻结第二批最小实验种子清单草案，不生成公式、不运行回测、不启动搜索、不抓取新资料、不修改 AlphaGPT 主程序、配置、阈值、评级规则、特征或算子。所有条目只作为待审批研究种子，不代表已经批准、有效或可交易。

## 2. 当前资料来源状态

Firecrawl 补证后可计算性映射已完成。当前进入可计算性候选的因子共 7 个，其中 computable_with_current_data 为 2 个，computable_with_minor_feature_derivation 为 5 个，requires_new_data 为 0 个，not_suitable_for_second_batch 为 0 个。

操作层策略候选共 19 条，本草案只整理其中建议进入后续操作层研究的 7 条；这些策略仅作为参考库，不进入本轮因子验证主流程。

当前 AlphaGPT 只读核查结果：基础特征为 RET1, RET5, VOL_RATIO20, VOLUME_WEIGHTED_RET, TREND60；算子为 ADD, SUB, MUL, DIV, NEG, ABS, SIGN, DELTA5, DECAY_LINEAR20, ZSCORE20；词表只暴露上述基础特征与算子；配置层存在 forward data 截止保护，research_end 不得晚于 20260626。

## 3. 7 个种子因子清单

| seed_factor_id | 因子名称 | 来源 | 可计算性分类 | 所需数据 | 是否需要新增派生特征 | 是否需要外部数据 | 是否建议进入第二批最小实验 |
| -------------- | ---- | -- | ------ | ---- | ---------- | -------- | ------------- |
| fp_momentum_mid_009 | 中期价格动量因子 | Smart Beta public reference; Stockformer abstract; Qlib reference | computable_with_minor_feature_derivation | 日线价量 | True | False | True |
| fp_reversal_short_010 | 短期反转因子 | Smart Beta public reference; Qlib reference | computable_with_current_data | 日线价量 | False | False | True |
| fp_low_vol_011 | 低波动因子 | Smart Beta public reference; Stockformer abstract | computable_with_minor_feature_derivation | 日线价量 | True | False | True |
| fp_downside_vol_012 | 下行波动因子 | A multi-factor market-neutral investment strategy for NYSE equities | computable_with_minor_feature_derivation | 日线价量 | True | False | True |
| fp_amount_liquidity_014 | 成交额流动性因子 | Stockformer abstract; Qlib reference | computable_with_minor_feature_derivation | 日线价量 | True | False | True |
| fp_price_volume_interaction_018 | 量价配合因子 | Stockformer abstract; Qlib reference | computable_with_current_data | 日线价量 | False | False | True |
| fp_multi_frequency_trend_019 | 多频趋势因子 | Stockformer abstract | computable_with_minor_feature_derivation | 日线价量 | True | False | True |

## 4. 直接可用因子

- fp_reversal_short_010 短期反转因子: 当前基础特征已包含 RET1、RET5；当前算子支持取反、加减乘除和简单时序处理。
- fp_price_volume_interaction_018 量价配合因子: 当前基础特征已包含 RET1、RET5、VOL_RATIO20、VOLUME_WEIGHTED_RET；当前算子支持乘除和简单时序处理。

上述因子不需要新增外部数据，不需要新增基础特征定义，也不需要新增算子；但仍需要用户审批后，才能转成 AlphaGPT 第二批候选特征。

## 5. 需要少量派生的因子

- fp_momentum_mid_009 中期价格动量因子: 需要新增中期收益窗口类日线价量派生基础特征定义，例如中期累计收益/趋势窗口；本阶段只登记，不实现。
- fp_low_vol_011 低波动因子: 需要新增基于日收益的滚动波动率类基础特征定义；本阶段只登记，不实现。
- fp_downside_vol_012 下行波动因子: 需要新增只统计负收益方向的下行波动类基础特征定义；本阶段只登记，不实现。
- fp_amount_liquidity_014 成交额流动性因子: 需要新增成交额均值或容量/流动性类日线价量派生基础特征定义；本阶段只登记，不实现。
- fp_multi_frequency_trend_019 多频趋势因子: 需要新增多窗口趋势或多窗口收益类日线价量派生基础特征定义；本阶段只登记，不实现。

上述因子只登记需要新增的日线价量派生基础特征定义。本阶段不实现这些派生特征，不写入 AlphaGPT 配置，不新增算子，不生成公式。

## 6. 不需要新增外部数据的确认

按当前映射文件，本轮 7 个因子均只依赖已确认的本地日线价量字段或可由日线价量轻量派生，不需要新增外部数据。requires_new_external_data 全部为 false。

## 7. 7 个操作层策略参考

| strategy_id | 策略名称 | 来源 | 可模拟性分类 | 当前是否可模拟 | 需要的轻微扩展 | 是否进入后续操作层研究 |
| ----------- | ---- | -- | ------ | ------- | ------- | ----------- |
| ts_multifactor_rank_monthly_001 | 多因子月度排序选股 | Smart Beta public reference; Qlib paper | simulatable_with_minor_engine_extension | False | 需要轻量表达多因子预设组合、月度调仓和过滤层；本阶段不实现。 | True |
| ts_momentum_liquidity_filter_004 | 动量选股+流动性过滤 | Smart Beta public reference; Stockformer abstract | simulatable_with_current_engine | True | 不需要本轮引擎扩展；仅作为后续操作层研究参考，不执行。 | True |
| ts_short_reversal_005 | 短期反转均值回归 | Smart Beta public reference; Qlib reference | simulatable_with_current_engine | True | 不需要本轮引擎扩展；仅作为后续操作层研究参考，不执行。 | True |
| ts_low_vol_defensive_006 | 低波动防御组合 | Smart Beta public reference; market-neutral strategy paper | simulatable_with_current_engine | True | 不需要本轮引擎扩展；仅作为后续操作层研究参考，不执行。 | True |
| ts_market_filter_exposure_014 | 市场状态过滤与仓位控制 | Qlib paper; A-share fundamental investing abstract | simulatable_with_minor_engine_extension | False | 需要轻量表达市场状态过滤或仓位暴露控制；本阶段不实现。 | True |
| ts_equal_weight_topn_017 | TopN 等权持仓 | Smart Beta public reference; Qlib paper | simulatable_with_current_engine | True | 不需要本轮引擎扩展；仅作为后续操作层研究参考，不执行。 | True |
| ts_liquidity_capacity_gate_018 | 流动性与容量门槛 | Stockformer abstract; Qlib paper | simulatable_with_minor_engine_extension | False | 需要轻量表达流动性/容量门槛或仓位上限；本阶段不实现。 | True |

这些策略只作为后续操作层研究参考，不是买卖建议，不接入交易，不回测，不进入本轮因子验证主流程。

## 8. 第二批最小实验的审批建议

- 是否批准 7 个种子因子进入第二批最小实验候选池：建议提交用户审批。
- 是否批准为 5 个派生因子新增基础特征定义：建议单独审批，且仅限日线价量轻量派生。
- 是否仍保持现有筛选标准：建议保持。
- 是否仍保持现有评级标准：建议保持。
- 是否仍禁止访问 forward data：建议继续禁止。
- 是否仍禁止自动交易和券商接入：建议继续禁止。
- 是否先只做小规模实验，不启动大规模搜索：建议是。

## 9. 禁止事项核查

- new_crawl_started: false
- new_formula_generated: false
- new_factor_search_started: false
- new_backtest_run: false
- alphaGPT_code_modified: false
- alphaGPT_config_modified: false
- new_feature_added: false
- new_operator_added: false
- threshold_changed: false
- rating_rule_changed: false
- forward_data_accessed: false
- trading_advice_generated: false
- next_stage_started: false

## 10. 汇总

- seed_factor_total: 7
- computable_with_current_data: 2
- computable_with_minor_feature_derivation: 5
- requires_new_external_data: 0
- operation_strategy_reference_total: 7
- simulatable_with_current_engine: 4
- simulatable_with_minor_engine_extension: 3

最终结论：本阶段完成第二批最小实验种子清单冻结草案。所有因子和策略仍只是待审批研究种子，尚未经过 AlphaGPT 本地回测验证，不得用于交易。
