# AlphaGPT 第二批种子因子特征落地方案

## 1. 本次任务边界

本次只做第二批种子因子特征落地方案，不修改代码、不修改配置、不新增基础特征、不新增算子、不生成公式、不启动搜索、不运行回测、不访问 forward data。本文只把 7 个待审批研究种子映射到 AlphaGPT 当前特征系统的可落地设计，供用户下一步审批。

## 2. 7 个种子因子逐项映射

| seed_factor_id | 因子名称 | 可计算性分类 | 当前是否可表达 | 需要新增基础特征 | 需要新增算子 | 需要外部数据 | 说明 |
| -------------- | ---- | ------ | ------- | -------- | ------ | ------ | -- |
| fp_momentum_mid_009 | 中期价格动量因子 | computable_with_minor_feature_derivation | 部分可表达 | RET20, RET60, RET120 | 否 | 否 | 当前已有 RET1、RET5、TREND60，但缺少中期累计收益窗口；建议以日线 close 派生多窗口收益特征，不生成新公式。 |
| fp_reversal_short_010 | 短期反转因子 | computable_with_current_data | 是 | 无 | 否 | 否 | 当前 RET1、RET5 可承载短期收益方向，现有 NEG、SUB、ZSCORE20 等算子可表达反转取向；不需要新数据或新特征。 |
| fp_low_vol_011 | 低波动因子 | computable_with_minor_feature_derivation | 否 | RET_STD20, RET_STD60 | 否 | 否 | 当前有收益特征但没有滚动波动率基础特征；建议基于日收益只用历史窗口派生。 |
| fp_downside_vol_012 | 下行波动因子 | computable_with_minor_feature_derivation | 否 | DOWNSIDE_RET_STD20, DOWNSIDE_RET_STD60 | 否 | 否 | 当前没有只统计负收益的下行风险特征；建议从 RET1 的负收益部分做历史滚动统计。 |
| fp_amount_liquidity_014 | 成交额流动性因子 | computable_with_minor_feature_derivation | 否 | AMOUNT_MA20, AMOUNT_MA60 | 否 | 否 | 当前 compute_base_features 只要求 close 和 volume，未暴露 amount；建议在批准实现时把 amount 作为可选输入列并派生成交额均值。 |
| fp_price_volume_interaction_018 | 量价配合因子 | computable_with_current_data | 是 | 无 | 否 | 否 | 当前 RET1、RET5、VOL_RATIO20、VOLUME_WEIGHTED_RET 已覆盖收益、成交量相对强弱和量价加权收益，可用现有算子组合表达价量配合方向。 |
| fp_multi_frequency_trend_019 | 多频趋势因子 | computable_with_minor_feature_derivation | 部分可表达 | TREND20, TREND120 | 否 | 否 | 当前只有 TREND60；建议补充短/长窗口趋势特征，使多频趋势不依赖复杂模型。 |

## 3. 2 个直接可用因子的表达方式

fp_reversal_short_010 短期反转因子：当前基础特征 RET1 和 RET5 已经提供 1 日与 5 日收益。反转方向可通过现有一元或二元算子对收益方向进行变换或排序取向调整来表达。这里仅说明可表达性，不把任何表达写入搜索、不新增候选公式。

fp_price_volume_interaction_018 量价配合因子：当前基础特征 RET1、RET5、VOL_RATIO20、VOLUME_WEIGHTED_RET 已经同时覆盖价格变化、成交量相对 20 日均量变化、量价加权收益。现有 ADD、SUB、MUL、DIV、ZSCORE20、DECAY_LINEAR20 等算子足以表达基础价量配合、量价确认或量价背离的简化形式。这里仅说明可表达性，不生成新公式。

## 4. 5 个派生因子的新增特征设计

### fp_momentum_mid_009 中期价格动量因子

建议新增基础特征：RET20、RET60、RET120。

数据来源：本地日线 close。计算逻辑摘要：按 ts_code 分组、按 trade_date 升序，仅使用当前日及历史收盘价计算指定窗口累计收益。是否只依赖日线价量：是。是否需要 warm-up：是，分别需要 20、60、120 个历史交易日窗口。是否可能引入未来函数：按当前 compute_base_features 的 groupby pct_change 风格实现，不使用未来日期，不应引入。缺失值处理：窗口不足、价格缺失或除数异常时输出 NaN，交由现有执行器覆盖率和有效行规则处理。与现有特征是否重复：RET20/RET120 不重复；RET60 与 TREND60 同属中期趋势信息但口径不同，一个是窗口收益，一个是相对均线偏离。实现复杂度：低。风险点：窗口越多越容易扩大搜索空间，需由用户审批后再暴露给 vocabulary。

### fp_low_vol_011 低波动因子

建议新增基础特征：RET_STD20、RET_STD60。

数据来源：本地日线 close 派生的 RET1。计算逻辑摘要：按 ts_code 分组，对历史 RET1 做滚动标准差。是否只依赖日线价量：是。是否需要 warm-up：是，分别需要 20、60 个有效收益样本。是否可能引入未来函数：只使用 rolling 历史窗口，不应引入。缺失值处理：窗口不足、RET1 缺失或标准差无法计算时输出 NaN。与现有特征是否重复：不重复，现有 TREND60 和 VOL_RATIO20 不等于收益波动率。实现复杂度：低。风险点：低流动性股票可能出现伪低波动，后续实验仍需保持既有可交易性和成本约束。

### fp_downside_vol_012 下行波动因子

建议新增基础特征：DOWNSIDE_RET_STD20、DOWNSIDE_RET_STD60。

数据来源：本地日线 close 派生的 RET1。计算逻辑摘要：按 ts_code 分组，将正收益视作 0 或 NaN 的口径需在实现前固定；建议优先采用负收益序列的滚动均方或标准差摘要，并在测试中锁定口径。是否只依赖日线价量：是。是否需要 warm-up：是，至少需要 20、60 个历史观测窗口。是否可能引入未来函数：只使用历史 rolling，不应引入。缺失值处理：窗口不足或无有效负收益时输出 NaN 或 0 的口径必须单测固定；建议保守输出 NaN，避免伪造稳定低风险。与现有特征是否重复：不重复。实现复杂度：低到中。风险点：不同下行波动定义会影响排序，必须在实现前明确口径并写入测试。

### fp_amount_liquidity_014 成交额流动性因子

建议新增基础特征：AMOUNT_MA20、AMOUNT_MA60。

数据来源：本地 daily_price.amount。计算逻辑摘要：在 compute_base_features 中新增可选 amount_col，若输入 bars 含 amount，则按 ts_code 分组计算 20/60 日历史平均成交额；若无 amount，则新增特征应为 NaN 或在调用侧保持兼容口径。是否只依赖日线价量：是。是否需要 warm-up：是，分别需要 20、60 日窗口。是否可能引入未来函数：只使用历史 rolling mean，不应引入。缺失值处理：amount 缺失、窗口不足输出 NaN；不得用未来成交额补齐。与现有特征是否重复：不重复，VOL_RATIO20 是成交量相对均量，AMOUNT_MA 是成交额容量。实现复杂度：中。风险点：当前 compute_base_features 的 required columns 不含 amount，批准实现时要保持旧测试和旧输入兼容，避免破坏现有 94 公式复验。

### fp_multi_frequency_trend_019 多频趋势因子

建议新增基础特征：TREND20、TREND120。

数据来源：本地日线 close。计算逻辑摘要：沿用当前 TREND60 的价格相对滚动均线偏离口径，新增 20 日和 120 日窗口。是否只依赖日线价量：是。是否需要 warm-up：是，分别需要 20、120 日窗口。是否可能引入未来函数：只使用 rolling 历史均线，不应引入。缺失值处理：窗口不足或价格缺失输出 NaN。与现有特征是否重复：TREND20/TREND120 与 TREND60 同族但窗口不同，不是完全重复。实现复杂度：低。风险点：多窗口趋势可能提升相关性和冗余度，后续仍需沿用现有相关性过滤，不调整阈值。

## 5. 是否需要新增算子

不需要新增算子。当前算子 ADD、SUB、MUL、DIV、NEG、ABS、SIGN、DELTA5、DECAY_LINEAR20、ZSCORE20 已足够承载这 7 个种子因子的最小可计算表达。5 个派生因子的问题是基础特征缺失，不是算子能力不足。因此用户若批准实现，建议保持 operators.py 不变，并通过测试确认 operator registry exact set 仍不变。

## 6. 最小代码改动范围

如果用户后续批准代码实现，预计最小改动范围为：

- ashare_research/factors/base_features.py：新增 RET20、RET60、RET120、RET_STD20、RET_STD60、DOWNSIDE_RET_STD20、DOWNSIDE_RET_STD60、AMOUNT_MA20、AMOUNT_MA60、TREND20、TREND120 的计算；保持原有特征口径不变。
- ashare_research/factors/vocabulary.py：通常不需要直接改逻辑，因为 TOKENS 从 BASE_FEATURES 自动生成；若实现新增 BASE_FEATURES，则只需确认 token 暴露符合审批范围。
- ashare_research/factors/executor.py：原则上不改逻辑；如果 BASE_FEATURES 扩展，executor 会自动要求并加载新增列，需要通过兼容性测试确认旧特征执行不受影响。
- tests/test_features_phase1.py：新增窗口、warm-up、缺失值、未来函数、amount 可选输入兼容测试。
- tests/test_expression_executor_phase1.py：新增或调整执行器兼容性测试，确认旧公式和新增基础特征 token 都能执行；确认算子集合不变。

不建议修改 factor_research_v2/config.py、pipeline.py、筛选阈值、评级规则、相关性阈值、time split 或任何回测逻辑。

## 7. 测试设计

建议新增或扩展以下测试：

- test_base_features_second_batch_windows：构造多股票、至少 130 日日线数据，确认 RET20、RET60、RET120、TREND20、TREND120 的 warm-up 行为和数值口径。
- test_volatility_features_warmup_and_missing_values：确认 RET_STD20、RET_STD60、DOWNSIDE_RET_STD20、DOWNSIDE_RET_STD60 在窗口不足时为 NaN，缺失 close/RET1 时不产生 inf。
- test_amount_features_are_optional_and_historical：输入含 amount 时计算 AMOUNT_MA20、AMOUNT_MA60；输入不含 amount 时保持旧调用兼容或输出受控 NaN，具体按审批口径固定。
- test_future_change_does_not_change_second_batch_features：沿用现有未来变化不影响过去的模式，修改最后一日 close/volume/amount，确认此前日期的新特征不变。
- test_executor_existing_formulas_still_valid：继续用旧特征表达式执行，确认 FormulaExecutor 对 RET1、RET5、VOL_RATIO20、VOLUME_WEIGHTED_RET、TREND60 的行为不变。
- test_executor_accepts_new_base_feature_tokens_after_approval：代码实现后再启用，确认新增基础特征作为 token 可被解析和执行。
- test_operator_registry_unchanged：保持现有 operator exact set，不新增算子。
- test_config_forward_cutoff_unchanged：保留 research_end 不得晚于 20260626 的保护，不触碰 forward data。

现有测试仍应全部通过，尤其是 test_features_phase1.py、test_expression_executor_phase1.py、test_formula_generation.py、test_factor_research_v2.py 中与 BASE_FEATURES、TOKENS、FormulaExecutor、forward cutoff 相关的测试。

## 8. 与当前研究口径的关系

本方案不修改筛选标准；不修改评级标准；不修改相关性阈值；不修改 time split；不访问 forward data；不启动第二批搜索；不运行回测；不改变 94 个公式复验口径。若后续批准新增基础特征，也应作为新的第二批候选特征能力单独进入审批流程，不能回写或重解释第一批 94 公式复验结果。

为了不影响现有 94 公式复验口径，后续实现应遵守三点：第一，旧 BASE_FEATURES 的名称和计算口径保持不变；第二，旧候选公式、旧 candidate_source、旧 runs 输出不重算不覆盖；第三，新增特征只在用户批准的第二批小规模实验中使用，并继续沿用现有筛选、评级、相关性和 forward data 禁止规则。

## 9. 用户审批清单

- 是否批准新增这 5 组日线价量派生基础特征：RET20/RET60/RET120，RET_STD20/RET_STD60，DOWNSIDE_RET_STD20/DOWNSIDE_RET_STD60，AMOUNT_MA20/AMOUNT_MA60，TREND20/TREND120。
- 是否批准保留现有算子不变，不新增 operators.py 算子。
- 是否批准新增对应单元测试。
- 是否批准完成代码实现但暂不运行搜索。
- 是否仍禁止回测和第二批搜索，直到代码实现和测试通过。

## 10. 禁止事项核查

- code_modified: false
- config_modified: false
- new_feature_added: false
- new_operator_added: false
- new_formula_generated: false
- new_factor_search_started: false
- new_backtest_run: false
- threshold_changed: false
- rating_rule_changed: false
- forward_data_accessed: false
- trading_advice_generated: false
- next_stage_started: false

最终结论：本阶段完成第二批种子因子特征落地方案。尚未修改 AlphaGPT 主程序，尚未新增特征，尚未回测，尚未搜索，所有因子仍不得用于交易。
