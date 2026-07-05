# AlphaGPT 初版因子/策略资料库来源可追溯性审计

生成时间：2026-07-05

## 1. 本次审计范围

本次只审计已有资料库，不新增采集、不回测、不修改 AlphaGPT 主程序。

审计对象为 `D:\alphaGPT_runtime\research_intel` 下现有来源登记、解析笔记、因子先验库和交易操作策略库。

## 2. 读取文件

- `D:\alphaGPT_runtime\research_intel\sources\source_seed_list.md`: exists
- `D:\alphaGPT_runtime\research_intel\sources\source_registry.jsonl`: exists
- `D:\alphaGPT_runtime\research_intel\reports\collection_progress_report.md`: exists
- `D:\alphaGPT_runtime\research_intel\reports\source_quality_report.md`: exists
- `D:\alphaGPT_runtime\research_intel\parsed\extracted_factor_notes.jsonl`: exists
- `D:\alphaGPT_runtime\research_intel\parsed\extracted_strategy_notes.jsonl`: exists
- `D:\alphaGPT_runtime\research_intel\library\factor_prior_library.jsonl`: exists
- `D:\alphaGPT_runtime\research_intel\library\trading_strategy_library.jsonl`: exists
- `D:\alphaGPT_runtime\research_intel\library\factor_prior_library.md`: exists
- `D:\alphaGPT_runtime\research_intel\library\trading_strategy_library.md`: exists

## 3. 当前资料库状态

- Firecrawl live 采集为 0。
- 当前库不能直接称为优质因子库。
- 当前库只能称为初版待核验先验库。
- 所有因子和策略尚未经过 AlphaGPT 本地回测验证。
- 不得用于交易。

## 4. 因子库审计结果

| 状态 | 数量 |
| --- | ---: |
| verified_source_candidate | 7 |
| partial_source_candidate | 13 |
| needs_source_verification | 0 |
| reject_for_untraceable_source | 0 |

| factor_id | factor_name_cn | source_title | source_platform | source_url_or_path | 审计状态 | 主要原因 |
| --- | --- | --- | --- | --- | --- | --- |
| fp_value_pe_001 | 低市盈率价值因子 | Smart Beta public reference; Qlib Alpha158-style feature reference | Wikipedia; GitHub | https://zh.wikipedia.org/wiki/Smart_Beta ; https://github.com/microsoft/qlib | partial_source_candidate | current_data_support=partial |
| fp_value_pb_002 | 低市净率价值因子 | Smart Beta public reference; Qlib Alpha158-style feature reference | Wikipedia; GitHub | https://zh.wikipedia.org/wiki/Smart_Beta ; https://github.com/microsoft/qlib | partial_source_candidate | current_data_support=partial |
| fp_dividend_yield_003 | 股息率因子 | Smart Beta public reference | Wikipedia | https://zh.wikipedia.org/wiki/Smart_Beta | partial_source_candidate | current_data_support=uncertain |
| fp_quality_roe_004 | ROE 质量因子 | Smart Beta public reference; A-share fundamental investing paper abstract | Wikipedia; arXiv | https://zh.wikipedia.org/wiki/Smart_Beta ; https://arxiv.org/abs/2510.21147 | partial_source_candidate | current_data_support=partial |
| fp_quality_roa_005 | ROA 质量因子 | Smart Beta public reference; A-share fundamental investing paper abstract | Wikipedia; arXiv | https://zh.wikipedia.org/wiki/Smart_Beta ; https://arxiv.org/abs/2510.21147 | partial_source_candidate | current_data_support=partial |
| fp_quality_cashflow_006 | 经营现金流质量因子 | A-share fundamental investing paper abstract | arXiv | https://arxiv.org/abs/2510.21147 | partial_source_candidate | current_data_support=partial |
| fp_growth_revenue_007 | 营收增长因子 | A-share fundamental investing paper abstract | arXiv | https://arxiv.org/abs/2510.21147 | partial_source_candidate | current_data_support=partial |
| fp_growth_earnings_008 | 利润增长因子 | A-share fundamental investing paper abstract | arXiv | https://arxiv.org/abs/2510.21147 | partial_source_candidate | current_data_support=partial |
| fp_momentum_mid_009 | 中期价格动量因子 | Smart Beta public reference; Stockformer abstract; Qlib reference | Wikipedia; arXiv; GitHub | https://zh.wikipedia.org/wiki/Smart_Beta ; https://arxiv.org/abs/2401.06139 ; https://github.com/microsoft/qlib | verified_source_candidate | traceable public source, complete required fields, marked usable_as_seed, current data support=yes |
| fp_reversal_short_010 | 短期反转因子 | Smart Beta public reference; Qlib reference | Wikipedia; GitHub | https://zh.wikipedia.org/wiki/Smart_Beta ; https://github.com/microsoft/qlib | verified_source_candidate | traceable public source, complete required fields, marked usable_as_seed, current data support=yes |
| fp_low_vol_011 | 低波动因子 | Smart Beta public reference; Stockformer abstract | Wikipedia; arXiv | https://zh.wikipedia.org/wiki/Smart_Beta ; https://arxiv.org/abs/2401.06139 | verified_source_candidate | traceable public source, complete required fields, marked usable_as_seed, current data support=yes |
| fp_downside_vol_012 | 下行波动因子 | A multi-factor market-neutral investment strategy for NYSE equities | arXiv | https://arxiv.org/abs/2412.12350 | verified_source_candidate | traceable public source, complete required fields, marked usable_as_seed, current data support=yes |
| fp_turnover_013 | 换手率因子 | Stockformer abstract; Qlib reference | arXiv; GitHub | https://arxiv.org/abs/2401.06139 ; https://github.com/microsoft/qlib | partial_source_candidate | current_data_support=partial |
| fp_amount_liquidity_014 | 成交额流动性因子 | Stockformer abstract; Qlib reference | arXiv; GitHub | https://arxiv.org/abs/2401.06139 ; https://github.com/microsoft/qlib | verified_source_candidate | traceable public source, complete required fields, marked usable_as_seed, current data support=yes |
| fp_size_015 | 市值因子 | Smart Beta public reference | Wikipedia | https://zh.wikipedia.org/wiki/Smart_Beta | partial_source_candidate | current_data_support=partial |
| fp_beta_016 | 市场 Beta 风险因子 | A multi-factor market-neutral investment strategy for NYSE equities | arXiv | https://arxiv.org/abs/2412.12350 | partial_source_candidate | current_data_support=partial |
| fp_industry_neutral_017 | 行业中性排序处理 | Qlib paper; market-neutral strategy paper | arXiv | https://arxiv.org/abs/2009.11189 ; https://arxiv.org/abs/2412.12350 | partial_source_candidate | current_data_support=partial |
| fp_price_volume_interaction_018 | 量价配合因子 | Stockformer abstract; Qlib reference | arXiv; GitHub | https://arxiv.org/abs/2401.06139 ; https://github.com/microsoft/qlib | verified_source_candidate | traceable public source, complete required fields, marked usable_as_seed, current data support=yes |
| fp_multi_frequency_trend_019 | 多频趋势因子 | Stockformer abstract | arXiv | https://arxiv.org/abs/2401.06139 | verified_source_candidate | traceable public source, complete required fields, marked usable_as_seed, current data support=yes |
| fp_composite_value_quality_momentum_020 | 价值+质量+动量复合因子组合 | Smart Beta public reference; Qlib paper | Wikipedia; arXiv | https://zh.wikipedia.org/wiki/Smart_Beta ; https://arxiv.org/abs/2009.11189 | partial_source_candidate | current_data_support=partial |

## 5. 策略库审计结果

| 状态 | 数量 |
| --- | ---: |
| verified_source_candidate | 8 |
| partial_source_candidate | 11 |
| needs_source_verification | 0 |
| reject_for_untraceable_source | 1 |

| strategy_id | strategy_name_cn | source_title | source_platform | source_url_or_path | 审计状态 | 主要原因 |
| --- | --- | --- | --- | --- | --- | --- |
| ts_multifactor_rank_monthly_001 | 多因子月度排序选股 | Smart Beta public reference; Qlib paper | Wikipedia; arXiv | https://zh.wikipedia.org/wiki/Smart_Beta ; https://arxiv.org/abs/2009.11189 | verified_source_candidate | traceable public source, complete required fields, marked useful_reference |
| ts_value_quality_combo_002 | 价值+质量组合 | Smart Beta public reference; A-share fundamental investing paper abstract | Wikipedia; arXiv | https://zh.wikipedia.org/wiki/Smart_Beta ; https://arxiv.org/abs/2510.21147 | verified_source_candidate | traceable public source, complete required fields, marked useful_reference |
| ts_growth_quality_combo_003 | 成长+质量组合 | A-share fundamental investing paper abstract | arXiv | https://arxiv.org/abs/2510.21147 | partial_source_candidate | curation_status=candidate |
| ts_momentum_liquidity_filter_004 | 动量选股+流动性过滤 | Smart Beta public reference; Stockformer abstract | Wikipedia; arXiv | https://zh.wikipedia.org/wiki/Smart_Beta ; https://arxiv.org/abs/2401.06139 | verified_source_candidate | traceable public source, complete required fields, marked useful_reference |
| ts_short_reversal_005 | 短期反转均值回归 | Smart Beta public reference; Qlib reference | Wikipedia; GitHub | https://zh.wikipedia.org/wiki/Smart_Beta ; https://github.com/microsoft/qlib | partial_source_candidate | curation_status=candidate |
| ts_low_vol_defensive_006 | 低波动防御组合 | Smart Beta public reference; market-neutral strategy paper | Wikipedia; arXiv | https://zh.wikipedia.org/wiki/Smart_Beta ; https://arxiv.org/abs/2412.12350 | verified_source_candidate | traceable public source, complete required fields, marked useful_reference |
| ts_size_quality_gate_007 | 小市值+基础质量过滤 | Smart Beta public reference | Wikipedia | https://zh.wikipedia.org/wiki/Smart_Beta | partial_source_candidate | curation_status=candidate |
| ts_industry_neutral_index_enhance_008 | 行业中性指数增强 | Qlib paper; market-neutral strategy paper | arXiv | https://arxiv.org/abs/2009.11189 ; https://arxiv.org/abs/2412.12350 | partial_source_candidate | curation_status=candidate |
| ts_market_neutral_reference_009 | 多因子市场中性多空参考 | A multi-factor market-neutral investment strategy for NYSE equities | arXiv | https://arxiv.org/abs/2412.12350 | partial_source_candidate | curation_status=candidate |
| ts_risk_parity_factor_010 | 风险平价因子组合 | A multi-factor market-neutral investment strategy for NYSE equities | arXiv | https://arxiv.org/abs/2412.12350 | partial_source_candidate | curation_status=candidate |
| ts_macro_industry_topdown_011 | 宏观-行业-个股分层选股 | Hierarchical AI Multi-Agent Fundamental Investing abstract | arXiv | https://arxiv.org/abs/2510.21147 | partial_source_candidate | curation_status=candidate |
| ts_fundamental_technical_blend_012 | 基本面+技术面混合选股 | A-share fundamental investing abstract; Stockformer abstract | arXiv | https://arxiv.org/abs/2510.21147 ; https://arxiv.org/abs/2401.06139 | partial_source_candidate | curation_status=candidate |
| ts_etf_rotation_momentum_013 | ETF 动量轮动 | Smart Beta public reference | Wikipedia | https://zh.wikipedia.org/wiki/Smart_Beta | partial_source_candidate | curation_status=candidate |
| ts_market_filter_exposure_014 | 市场状态过滤与仓位控制 | Qlib paper; A-share fundamental investing abstract | arXiv | https://arxiv.org/abs/2009.11189 ; https://arxiv.org/abs/2510.21147 | partial_source_candidate | curation_status=candidate |
| ts_stop_loss_take_profit_015 | 止损止盈操作规则 | Public strategy operation reference | public_reference | research_intel/sources/source_seed_list.md | reject_for_untraceable_source | source_url_or_path cannot fully map to source_registry; source_quality=uncertain; curation_status=candidate; reported_backtest_period is not clearly marked as source claim only |
| ts_turnover_budget_016 | 换手预算约束 | Qlib paper | arXiv | https://arxiv.org/abs/2009.11189 | verified_source_candidate | traceable public source, complete required fields, marked useful_reference |
| ts_equal_weight_topn_017 | TopN 等权持仓 | Smart Beta public reference; Qlib paper | Wikipedia; arXiv | https://zh.wikipedia.org/wiki/Smart_Beta ; https://arxiv.org/abs/2009.11189 | verified_source_candidate | traceable public source, complete required fields, marked useful_reference |
| ts_liquidity_capacity_gate_018 | 流动性与容量门槛 | Stockformer abstract; Qlib paper | arXiv | https://arxiv.org/abs/2401.06139 ; https://arxiv.org/abs/2009.11189 | verified_source_candidate | traceable public source, complete required fields, marked useful_reference |
| ts_report_news_overlay_019 | 研报/新闻风险覆盖层 | A-share fundamental investing paper abstract | arXiv | https://arxiv.org/abs/2510.21147 | partial_source_candidate | curation_status=candidate |
| ts_pipeline_audit_020 | 研究-回测-执行全链条审计 | Qlib paper | arXiv | https://arxiv.org/abs/2009.11189 | verified_source_candidate | traceable public source, complete required fields, marked useful_reference |

## 6. 可进入后续种子候选白名单的内容

白名单只代表“可作为后续研究种子候选”，不代表有效因子，不代表可交易策略。

### 因子白名单

- `fp_momentum_mid_009` 中期价格动量因子: traceable public source, complete required fields, marked usable_as_seed, current data support=yes
- `fp_reversal_short_010` 短期反转因子: traceable public source, complete required fields, marked usable_as_seed, current data support=yes
- `fp_low_vol_011` 低波动因子: traceable public source, complete required fields, marked usable_as_seed, current data support=yes
- `fp_downside_vol_012` 下行波动因子: traceable public source, complete required fields, marked usable_as_seed, current data support=yes
- `fp_amount_liquidity_014` 成交额流动性因子: traceable public source, complete required fields, marked usable_as_seed, current data support=yes
- `fp_price_volume_interaction_018` 量价配合因子: traceable public source, complete required fields, marked usable_as_seed, current data support=yes
- `fp_multi_frequency_trend_019` 多频趋势因子: traceable public source, complete required fields, marked usable_as_seed, current data support=yes

### 策略白名单

- `ts_multifactor_rank_monthly_001` 多因子月度排序选股: traceable public source, complete required fields, marked useful_reference
- `ts_value_quality_combo_002` 价值+质量组合: traceable public source, complete required fields, marked useful_reference
- `ts_momentum_liquidity_filter_004` 动量选股+流动性过滤: traceable public source, complete required fields, marked useful_reference
- `ts_low_vol_defensive_006` 低波动防御组合: traceable public source, complete required fields, marked useful_reference
- `ts_turnover_budget_016` 换手预算约束: traceable public source, complete required fields, marked useful_reference
- `ts_equal_weight_topn_017` TopN 等权持仓: traceable public source, complete required fields, marked useful_reference
- `ts_liquidity_capacity_gate_018` 流动性与容量门槛: traceable public source, complete required fields, marked useful_reference
- `ts_pipeline_audit_020` 研究-回测-执行全链条审计: traceable public source, complete required fields, marked useful_reference

## 7. 需要重新采集或补证的内容

### 因子待补证

- `fp_value_pe_001` 低市盈率价值因子: current_data_support=partial
- `fp_value_pb_002` 低市净率价值因子: current_data_support=partial
- `fp_dividend_yield_003` 股息率因子: current_data_support=uncertain
- `fp_quality_roe_004` ROE 质量因子: current_data_support=partial
- `fp_quality_roa_005` ROA 质量因子: current_data_support=partial
- `fp_quality_cashflow_006` 经营现金流质量因子: current_data_support=partial
- `fp_growth_revenue_007` 营收增长因子: current_data_support=partial
- `fp_growth_earnings_008` 利润增长因子: current_data_support=partial
- `fp_turnover_013` 换手率因子: current_data_support=partial
- `fp_size_015` 市值因子: current_data_support=partial
- `fp_beta_016` 市场 Beta 风险因子: current_data_support=partial
- `fp_industry_neutral_017` 行业中性排序处理: current_data_support=partial
- `fp_composite_value_quality_momentum_020` 价值+质量+动量复合因子组合: current_data_support=partial

### 策略待补证

- `ts_growth_quality_combo_003` 成长+质量组合: curation_status=candidate
- `ts_short_reversal_005` 短期反转均值回归: curation_status=candidate
- `ts_size_quality_gate_007` 小市值+基础质量过滤: curation_status=candidate
- `ts_industry_neutral_index_enhance_008` 行业中性指数增强: curation_status=candidate
- `ts_market_neutral_reference_009` 多因子市场中性多空参考: curation_status=candidate
- `ts_risk_parity_factor_010` 风险平价因子组合: curation_status=candidate
- `ts_macro_industry_topdown_011` 宏观-行业-个股分层选股: curation_status=candidate
- `ts_fundamental_technical_blend_012` 基本面+技术面混合选股: curation_status=candidate
- `ts_etf_rotation_momentum_013` ETF 动量轮动: curation_status=candidate
- `ts_market_filter_exposure_014` 市场状态过滤与仓位控制: curation_status=candidate
- `ts_stop_loss_take_profit_015` 止损止盈操作规则: source_url_or_path cannot fully map to source_registry; source_quality=uncertain; curation_status=candidate; reported_backtest_period is not clearly marked as source claim only
- `ts_report_news_overlay_019` 研报/新闻风险覆盖层: curation_status=candidate

主要补证方向：

- 对聚宽、米筐、BigQuant 等社区资料进行真实 Firecrawl 采集或人工登记。
- 给每条来源补充明确的采集方式：live、dry-run、手工登记、公开资料整理或无法确认。
- 对 `partial` 条目补充 AlphaGPT 当前数据支持情况、具体可实现字段和更直接来源。
- 对策略操作条目补充更具体的社区策略或论文来源，避免只停留在模板化操作描述。

## 8. 被排除内容

### 因子排除

- 无

### 策略排除

- `ts_stop_loss_take_profit_015` 止损止盈操作规则: source_url_or_path cannot fully map to source_registry; source_quality=uncertain; curation_status=candidate; reported_backtest_period is not clearly marked as source claim only

## 9. 对下一步的影响

当前已有若干 `verified_source_candidate`，可以进入下一步“种子因子映射到 AlphaGPT 可计算特征”的方案设计，但仍不得自动执行。

由于 Firecrawl live 采集仍为 0，且聚宽、米筐、BigQuant 尚未真实抓取，不建议直接启动 AlphaGPT 第二批搜索。更稳妥的下一步是先配置 Firecrawl API key 或补充真实采集，再把白名单条目映射到本地可计算字段。

不得启动回测或搜索。

## 10. 禁止事项核查

- new_crawl_started: false
- new_formula_generated: false
- new_factor_search_started: false
- new_backtest_run: false
- alphaGPT_code_modified: false
- alphaGPT_config_modified: false
- forward_data_accessed: false
- trading_advice_generated: false
- next_stage_started: false
