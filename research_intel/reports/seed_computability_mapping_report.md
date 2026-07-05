# AlphaGPT Firecrawl 补证后种子因子与策略可计算性映射

## 1. 本次任务边界

本次只做 Firecrawl 补证后的种子因子可计算性与策略可模拟性映射。不继续抓取，不生成新公式，不运行回测，不启动搜索，不修改 AlphaGPT 主程序、配置、阈值、评级规则或特征/算子。

## 2. 读取文件

- `D:\alphaGPT_runtime\research_intel\reports\firecrawl_live_collection_report.md`
- `D:\alphaGPT_runtime\research_intel\reports\library_traceability_audit_report.md`
- `D:\alphaGPT_runtime\research_intel\library\factor_prior_library.jsonl`
- `D:\alphaGPT_runtime\research_intel\library\trading_strategy_library.jsonl`
- `D:\alphaGPT_runtime\research_intel\library\factor_seed_candidate_whitelist.jsonl`
- `D:\alphaGPT_runtime\research_intel\library\strategy_seed_candidate_whitelist.jsonl`
- `D:\alphaGPT\github_safe_sync\ashare_research\factors\base_features.py`
- `D:\alphaGPT\github_safe_sync\ashare_research\factors\operators.py`
- `D:\alphaGPT\github_safe_sync\ashare_research\factors\vocabulary.py`
- `D:\alphaGPT\github_safe_sync\ashare_research\factors\executor.py`
- `D:\alphaGPT\github_safe_sync\ashare_research\factor_research_v2\config.py`
- `D:\alphaGPT\github_safe_sync\ashare_research\factor_research_v2\pipeline.py`
- `D:\alphaGPT\github_safe_sync\ashare_research\factor_research_v2\full_backtest.py`
- `C:\Users\Admin\alphaGPT\stock-data\ashare_research.sqlite3 schema only`

## 3. 当前 AlphaGPT 数据与特征能力摘要

- 当前基础特征: `RET1`, `RET5`, `VOL_RATIO20`, `VOLUME_WEIGHTED_RET`, `TREND60`。
- 当前算子: `ADD`, `SUB`, `MUL`, `DIV`, `NEG`, `ABS`, `SIGN`, `DELTA5`, `DECAY_LINEAR20`, `ZSCORE20`。
- 当前公式限制: prefix token 最大长度由配置控制；vocabulary 只暴露上述基础特征和算子。
- 当前 Phase 2 执行框架: `top_n_long_only_equal_weight` 风格，按因子排序选 TopN，显式交易成本，支持可交易性/涨跌停/停牌相关约束的既有数据输入。
- 已确认日线价量: 是，`daily_price` 含 open/high/low/close/volume/amount/pct_chg，日期范围 20190704 到 20260626。
- 已确认市值/估值: 是，`daily_basic` 含 turnover_rate/volume_ratio/pe/pb/ps/total_mv/circ_mv，日期范围 20190704 到 20260626。
- 已确认财务: 未确认完整财务报表；当前 schema 只确认 daily_basic 估值和市值字段，未确认 ROE/ROA/现金流/收入利润增长字段。
- 已确认行业: 是，`stock_basic`, `stock_basic_tushare`, `stock_lifecycle` 含 industry 字段。
- 已确认指数成分: 是，`csi800_weight_local`, `csi800_weight_tushare` 存在 CSI800 权重/成分。
- 已确认 ST / 涨跌停 / 可交易状态: 是，`historical_st_status`, `derived_limit_price`, `derived_tradability`, `suspend_d`, `stk_limit` 存在；其中 `stk_limit`/`suspend_d` 当前只确认覆盖 20260610 到 20260626，完整历史口径需谨慎。

## 4. 7 个因子种子可计算性结果

| factor_id | factor_name_cn | 来源 | 所需数据 | 当前是否支持 | 分类 | 原因 | 是否建议进入第二批最小实验候选池 |
| --------- | -------------- | -- | ---- | ------ | -- | -- | ---------------- |
| fp_momentum_mid_009 | 中期价格动量因子 | Smart Beta public reference; Stockformer abstract; Qlib reference | 日线收盘价；新增中期收益基础特征定义 | supported_for_mapping | computable_with_minor_feature_derivation | 需要中期收益窗口，如60/120/240日；当前数据支持日线价格，但当前基础特征只内置RET1、RET5、TREND60。 | true |
| fp_reversal_short_010 | 短期反转因子 | Smart Beta public reference; Qlib reference | 日线收盘价、RET1/RET5 | supported_for_mapping | computable_with_current_data | 当前基础特征已有RET1、RET5，现有算子可表达短期反转方向。 | true |
| fp_low_vol_011 | 低波动因子 | Smart Beta public reference; Stockformer abstract | 日线收益；新增滚动波动率基础特征定义 | supported_for_mapping | computable_with_minor_feature_derivation | 当前有日线价格和收益，但没有直接的滚动波动率基础特征；需要从日收益派生rolling std。 | true |
| fp_downside_vol_012 | 下行波动因子 | A multi-factor market-neutral investment strategy for NYSE equities | 日线收益；新增下行波动基础特征定义 | supported_for_mapping | computable_with_minor_feature_derivation | 当前有日线收益，但没有只统计负收益的下行波动特征；需要轻量派生。 | true |
| fp_amount_liquidity_014 | 成交额流动性因子 | Stockformer abstract; Qlib reference | daily_price.amount、daily_basic.turnover_rate/total_mv；新增流动性基础特征定义 | supported_for_mapping | computable_with_minor_feature_derivation | 数据库daily_price有amount，daily_basic有turnover_rate/total_mv/circ_mv，但当前基础特征未暴露成交额均值或容量特征。 | true |
| fp_price_volume_interaction_018 | 量价配合因子 | Stockformer abstract; Qlib reference | 日线收盘价、成交量、RET/VOL_RATIO/VOLUME_WEIGHTED_RET | supported_for_mapping | computable_with_current_data | 当前基础特征已有RET1/RET5、VOL_RATIO20、VOLUME_WEIGHTED_RET，且算子支持乘除与时间序列处理，可表达简化量价配合。 | true |
| fp_multi_frequency_trend_019 | 多频趋势因子 | Stockformer abstract | 日线价格；新增多窗口趋势基础特征定义 | supported_for_mapping | computable_with_minor_feature_derivation | 可先用多窗口日线趋势近似；当前只有TREND60，若要多频窗口需要新增RET20/RET120等基础特征定义，不引入复杂模型。 | true |

说明：建议进入候选池只代表可作为后续审批候选，不代表已经批准、有效或可交易。

## 5. 19 条策略种子可模拟性结果

| strategy_id | strategy_name_cn | 来源 | 所需数据/机制 | 当前是否支持 | 分类 | 原因 | 是否建议进入后续操作层研究 |
| ----------- | ---------------- | -- | ------- | ------ | -- | -- | ------------- |
| ts_multifactor_rank_monthly_001 | 多因子月度排序选股 | Smart Beta public reference; Qlib paper | TopN排序、月度调仓、可交易过滤、成本 | supported_for_operation_research_mapping | simulatable_with_minor_engine_extension | 当前Phase 2已有TopN长仓等权框架，但多因子预设组合、月度调仓和过滤层需要轻量表达。 | true |
| ts_value_quality_combo_002 | 价值+质量组合 | Smart Beta public reference; A-share fundamental investing paper abstract | PE/PB、ROE/ROA、现金流质量、财务滞后处理 | defer | requires_data_confirmation | PE/PB/市值字段存在，但ROE/ROA/现金流质量等财务质量字段未在schema中确认。 | false |
| ts_growth_quality_combo_003 | 成长+质量组合 | A-share fundamental investing paper abstract | 营收增长、利润增长、ROE、现金流质量 | defer | requires_data_confirmation | 收入/利润增长和质量字段未在当前schema中确认，不能直接转为操作层方案。 | false |
| ts_momentum_liquidity_filter_004 | 动量选股+流动性过滤 | Smart Beta public reference; Stockformer abstract | 动量分数、流动性过滤、TopN等权、成本 | supported_for_operation_research_mapping | simulatable_with_current_engine | 可用日线动量/流动性过滤形成TopN候选，当前Phase 2长仓等权和成本框架理论上可承载。 | true |
| ts_short_reversal_005 | 短期反转均值回归 | Smart Beta public reference; Qlib reference | 短期收益、成交额/流动性、TopN等权、成本 | supported_for_operation_research_mapping | simulatable_with_current_engine | 短期反转可由RET1/RET5表达，当前引擎可按排序信号进行TopN等权模拟。 | true |
| ts_low_vol_defensive_006 | 低波动防御组合 | Smart Beta public reference; market-neutral strategy paper | 低波动/下行波动分数、流动性过滤、TopN等权 | supported_for_operation_research_mapping | simulatable_with_current_engine | 低波动特征需派生，但操作层是排序选股与等权持有，当前Phase 2框架可表达。 | true |
| ts_size_quality_gate_007 | 小市值+基础质量过滤 | Smart Beta public reference | 市值、ROE、现金流质量、成交额 | defer | requires_data_confirmation | 市值字段存在，但质量字段未确认；需要先核实财务质量覆盖。 | false |
| ts_industry_neutral_index_enhance_008 | 行业中性指数增强 | Qlib paper; market-neutral strategy paper | 行业、指数成分、行业暴露、TopN组合 | defer | requires_data_confirmation | 行业、CSI800成分字段存在，但行业中性和指数增强约束需要确认覆盖与口径。 | false |
| ts_market_neutral_reference_009 | 多因子市场中性多空参考 | A multi-factor market-neutral investment strategy for NYSE equities | 对冲、空头或beta中性、风险平衡 | defer | requires_new_engine_logic | 市场中性需要对冲/空头或beta中性组合逻辑，当前Phase 2是长仓TopN等权框架。 | false |
| ts_risk_parity_factor_010 | 风险平价因子组合 | A multi-factor market-neutral investment strategy for NYSE equities | 协方差/波动估计、组合权重优化 | defer | requires_new_engine_logic | 风险平价需要组合权重优化或波动倒数权重，超出当前等权TopN执行逻辑。 | false |
| ts_macro_industry_topdown_011 | 宏观-行业-个股分层选股 | Hierarchical AI Multi-Agent Fundamental Investing abstract | 宏观状态、行业景气、分层配置 | defer | not_suitable_for_current_alphaGPT | 依赖宏观、行业景气和主观/模型化自上而下判断，不适合当前最小实验。 | false |
| ts_fundamental_technical_blend_012 | 基本面+技术面混合选股 | A-share fundamental investing abstract; Stockformer abstract | 价值、成长、质量、技术面 | defer | requires_data_confirmation | 技术面可支持，基本面价值/成长/质量字段需要先确认覆盖和滞后处理。 | false |
| ts_etf_rotation_momentum_013 | ETF 动量轮动 | Smart Beta public reference | ETF行情、动量、低波动、成交额 | defer | requires_data_confirmation | 当前schema确认了股票与指数数据，未确认ETF行情池；轮动标的范围需先确认。 | false |
| ts_market_filter_exposure_014 | 市场状态过滤与仓位控制 | Qlib paper; A-share fundamental investing abstract | 指数趋势、市场过滤、仓位暴露控制 | supported_for_operation_research_mapping | simulatable_with_minor_engine_extension | 指数行情存在，但市场状态过滤/降仓需要轻量扩展暴露控制表达。 | true |
| ts_turnover_budget_016 | 换手预算约束 | Qlib paper | 持仓状态、边际收益、交易成本、换手约束 | defer | requires_new_engine_logic | 换手预算是组合状态约束，当前Phase 2未确认有基于旧持仓的换手预算决策。 | false |
| ts_equal_weight_topn_017 | TopN 等权持仓 | Smart Beta public reference; Qlib paper | 任意排序分数、TopN、等权、调仓成本 | supported_for_operation_research_mapping | simulatable_with_current_engine | 当前Phase 2配置明确是top_n_long_only_equal_weight，最贴近现有执行框架。 | true |
| ts_liquidity_capacity_gate_018 | 流动性与容量门槛 | Stockformer abstract; Qlib paper | amount、turnover_rate、derived_tradability、suspend_d | supported_for_operation_research_mapping | simulatable_with_minor_engine_extension | 成交额、换手、停牌/可交易状态字段存在；容量门槛可作为轻量过滤/仓位上限研究。 | true |
| ts_report_news_overlay_019 | 研报/新闻风险覆盖层 | A-share fundamental investing paper abstract | 新闻、研报、事件文本 | defer | not_suitable_for_current_alphaGPT | 依赖研报、新闻和事件文本，当前本地结构化行情库不支持。 | false |
| ts_pipeline_audit_020 | 研究-回测-执行全链条审计 | Qlib paper | 流程记录、审计、执行层日志 | defer | not_suitable_for_current_alphaGPT | 这是研究-回测-执行流程审计框架，不是可直接模拟的交易策略。 | false |

说明：策略库内容不是买卖建议，只是后续操作层研究的结构化参考。

## 6. 适合第二批最小实验候选池的因子

- `fp_momentum_mid_009`: computable_with_minor_feature_derivation。需要中期收益窗口，如60/120/240日；当前数据支持日线价格，但当前基础特征只内置RET1、RET5、TREND60。
- `fp_reversal_short_010`: computable_with_current_data。当前基础特征已有RET1、RET5，现有算子可表达短期反转方向。
- `fp_low_vol_011`: computable_with_minor_feature_derivation。当前有日线价格和收益，但没有直接的滚动波动率基础特征；需要从日收益派生rolling std。
- `fp_downside_vol_012`: computable_with_minor_feature_derivation。当前有日线收益，但没有只统计负收益的下行波动特征；需要轻量派生。
- `fp_amount_liquidity_014`: computable_with_minor_feature_derivation。数据库daily_price有amount，daily_basic有turnover_rate/total_mv/circ_mv，但当前基础特征未暴露成交额均值或容量特征。
- `fp_price_volume_interaction_018`: computable_with_current_data。当前基础特征已有RET1/RET5、VOL_RATIO20、VOLUME_WEIGHTED_RET，且算子支持乘除与时间序列处理，可表达简化量价配合。
- `fp_multi_frequency_trend_019`: computable_with_minor_feature_derivation。可先用多窗口日线趋势近似；当前只有TREND60，若要多频窗口需要新增RET20/RET120等基础特征定义，不引入复杂模型。

这些因子都只依赖已确认的日线价量或可由日线价量轻量派生；进入候选池仍需用户后续审批，不自动启动实验。

## 7. 暂不适合第二批的因子

无。当前 7 个 Firecrawl 补证因子均可进入待审批候选池；其中需要轻量派生的因子不得在本轮新增特征，只做标记。

## 8. 适合后续操作层研究的策略

- `ts_multifactor_rank_monthly_001`: simulatable_with_minor_engine_extension。当前Phase 2已有TopN长仓等权框架，但多因子预设组合、月度调仓和过滤层需要轻量表达。
- `ts_momentum_liquidity_filter_004`: simulatable_with_current_engine。可用日线动量/流动性过滤形成TopN候选，当前Phase 2长仓等权和成本框架理论上可承载。
- `ts_short_reversal_005`: simulatable_with_current_engine。短期反转可由RET1/RET5表达，当前引擎可按排序信号进行TopN等权模拟。
- `ts_low_vol_defensive_006`: simulatable_with_current_engine。低波动特征需派生，但操作层是排序选股与等权持有，当前Phase 2框架可表达。
- `ts_market_filter_exposure_014`: simulatable_with_minor_engine_extension。指数行情存在，但市场状态过滤/降仓需要轻量扩展暴露控制表达。
- `ts_equal_weight_topn_017`: simulatable_with_current_engine。当前Phase 2配置明确是top_n_long_only_equal_weight，最贴近现有执行框架。
- `ts_liquidity_capacity_gate_018`: simulatable_with_minor_engine_extension。成交额、换手、停牌/可交易状态字段存在；容量门槛可作为轻量过滤/仓位上限研究。

这些策略可为后续操作层研究提供调仓频率、TopN持仓、流动性过滤、市场过滤和基础组合构建参考。本轮不开发新引擎、不回测。

## 9. 暂不适合当前操作层研究的策略

- `ts_value_quality_combo_002`: requires_data_confirmation。PE/PB/市值字段存在，但ROE/ROA/现金流质量等财务质量字段未在schema中确认。
- `ts_growth_quality_combo_003`: requires_data_confirmation。收入/利润增长和质量字段未在当前schema中确认，不能直接转为操作层方案。
- `ts_size_quality_gate_007`: requires_data_confirmation。市值字段存在，但质量字段未确认；需要先核实财务质量覆盖。
- `ts_industry_neutral_index_enhance_008`: requires_data_confirmation。行业、CSI800成分字段存在，但行业中性和指数增强约束需要确认覆盖与口径。
- `ts_market_neutral_reference_009`: requires_new_engine_logic。市场中性需要对冲/空头或beta中性组合逻辑，当前Phase 2是长仓TopN等权框架。
- `ts_risk_parity_factor_010`: requires_new_engine_logic。风险平价需要组合权重优化或波动倒数权重，超出当前等权TopN执行逻辑。
- `ts_macro_industry_topdown_011`: not_suitable_for_current_alphaGPT。依赖宏观、行业景气和主观/模型化自上而下判断，不适合当前最小实验。
- `ts_fundamental_technical_blend_012`: requires_data_confirmation。技术面可支持，基本面价值/成长/质量字段需要先确认覆盖和滞后处理。
- `ts_etf_rotation_momentum_013`: requires_data_confirmation。当前schema确认了股票与指数数据，未确认ETF行情池；轮动标的范围需先确认。
- `ts_turnover_budget_016`: requires_new_engine_logic。换手预算是组合状态约束，当前Phase 2未确认有基于旧持仓的换手预算决策。
- `ts_report_news_overlay_019`: not_suitable_for_current_alphaGPT。依赖研报、新闻和事件文本，当前本地结构化行情库不支持。
- `ts_pipeline_audit_020`: not_suitable_for_current_alphaGPT。这是研究-回测-执行流程审计框架，不是可直接模拟的交易策略。

## 10. 对下一步的审批建议

- 是否允许把 `computable_with_current_data` 因子转成 AlphaGPT 第二批候选特征：建议可审批。
- 是否允许为 `computable_with_minor_feature_derivation` 因子新增少量日线价量派生基础特征定义：建议单独审批。
- 是否允许把可模拟策略转成后续操作层研究方案：建议只允许小批量、非交易、非 forward data 的研究方案。
- 是否仍保持原筛选标准和评级标准：建议保持。
- 是否仍禁止访问 forward data：建议继续禁止。
- 是否仍禁止自动交易和券商接入：建议继续禁止。
- 是否先只做小批量实验：建议是。

## 11. 禁止事项核查

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

## 12. 汇总

- factor_class_counts: {'computable_with_minor_feature_derivation': 5, 'computable_with_current_data': 2}
- strategy_class_counts: {'simulatable_with_minor_engine_extension': 3, 'requires_data_confirmation': 6, 'simulatable_with_current_engine': 4, 'requires_new_engine_logic': 3, 'not_suitable_for_current_alphaGPT': 3}
- factor_recommended_for_second_batch_minimal_experiment_candidate_pool: 7
- strategy_recommended_for_followup_operation_layer_research: 7

最终结论：本阶段完成 Firecrawl 补证后种子因子与策略可计算性映射。所有因子和策略仍只是研究种子先验，尚未经过 AlphaGPT 本地回测验证，不得用于交易。
