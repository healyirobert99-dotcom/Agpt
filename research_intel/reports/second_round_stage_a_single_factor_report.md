# AlphaGPT 第二轮阶段 A：7 个种子因子单因子检查报告

## 1. 运行信息

| 项目 | 值 |
| ---- | --- |
| run_id | factor_research_v2_20260705_145716 |
| commit SHA | 2ea176cf6d9a826099679cda971a01bb0d57bfec |
| 运行时间 | 247.8 秒（4分8秒） |
| 数据库是否存在 | ✅ stock-data/ashare_research.sqlite3（6.3 GB） |
| 是否只运行 7 个固定候选 | 是 |
| 是否启动 B/C | 否 |
| 是否使用库外因子 | 否 |
| 是否新增特征或算子 | 否 |
| 是否修改筛选/评级/回测逻辑 | 否 |
| 是否访问 forward data | 否 |

## 2. 逐因子结果

| # | seed_factor_id | 名称 | 公式 | fast_screen | IC | Phase 2 收益 | Sharpe | 稳健性 | 评级 | 状态 |
|---|---------------|------|------|-------------|-----|------------|--------|------|------|------|
| 1 | fp_momentum_mid_009 | 中期动量 | ZSCORE20(RET60) | ❌ rejected | -0.1206 | — | — | — | Rejected | 覆盖率不足 |
| 2 | fp_reversal_short_010 | 短期反转 | NEG(RET5) | ✅ passed | +0.0364 | -20.28% | -1.313 | ❌ rejected | Rejected | 回测为负 |
| 3 | fp_low_vol_011 | 低波动 | NEG(RET_STD20) | ✅ passed | +0.0247 | +3.68% | +0.771 | ✅ passed | **B** | ✅ shortlisted |
| 4 | fp_downside_vol_012 | 下行波动 | NEG(DOWNSIDE_RET_STD20) | ✅ passed | -0.0045 | +5.73% | +1.173 | ✅ passed | **C** | ✅ shortlisted |
| 5 | fp_amount_liquidity_014 | 流动性 | ZSCORE20(AMOUNT_MA20) | ✅ passed | -0.0579 | -21.80% | -1.964 | ❌ rejected | Rejected | 回测为负 |
| 6 | fp_price_volume_interaction_018 | 量价配合 | MUL(RET5,VOLUME_WEIGHTED_RET) | ✅ passed | -0.0175 | -17.09% | -1.223 | ❌ rejected | Rejected | 回测为负 |
| 7 | fp_multi_frequency_trend_019 | 多频趋势 | ADD(TREND20,TREND60) | ✅ passed | -0.0572 | -11.39% | -1.440 | ❌ rejected | Rejected | 回测为负 |

## 3. 阶段统计

| 阶段 | 输入 | 通过 | 说明 |
| ---- | ---- | ---- | ---- |
| fast_screen (development) | 7 | 6 | fp_momentum_mid_009 覆盖率不达标（0.281 < 0.30） |
| 相关性去重 | 6 | 6 | 无重复 |
| Phase 2 回测 | 6 | 6 | 全部可执行 |
| 稳健性 | 6 | 2 | 仅 fp_low_vol_011 和 fp_downside_vol_012 通过 |

## 4. 评级分布

| 评级 | 数量 | 因子 |
| ---- | ---- | ---- |
| **A** | 0 | — |
| **B** | 1 | fp_low_vol_011 — NEG(RET_STD20) |
| **C** | 1 | fp_downside_vol_012 — NEG(DOWNSIDE_RET_STD20) |
| **Rejected** | 4 | fp_momentum_mid_009, fp_reversal_short_010, fp_amount_liquidity_014, fp_price_volume_interaction_018, fp_multi_frequency_trend_019 |
| **fast_screen 未通过** | 1 | fp_momentum_mid_009 |

**final_shortlist_count: 2**

## 5. recommended_factors

### B 级：fp_low_vol_011 — NEG(RET_STD20)

| 指标 | 值 |
| ---- | --- |
| rank_ic_mean | +0.0247 |
| 回测总收益 | +3.68% |
| Sharpe | 0.771 |
| 最大回撤 | -5.01% |
| 覆盖率 | 78.6% |
| 正周期比率 | 55.4% |

### C 级：fp_downside_vol_012 — NEG(DOWNSIDE_RET_STD20)

| 指标 | 值 |
| ---- | --- |
| rank_ic_mean | -0.0045 |
| 回测总收益 | +5.73% |
| Sharpe | 1.173 |
| 最大回撤 | -7.29% |
| 覆盖率 | 78.6% |
| 正周期比率 | 54.3% |

**注意：** fp_downside_vol_012 虽然回测收益和 Sharpe 均优于低波动因子，但 IC 极弱（-0.0045），评级被限制在 C。

## 6. 失败原因分布

| 原因 | 数量 | 因子 |
| ---- | ---- | ---- |
| coverage < 0.30 | 1 | fp_momentum_mid_009 |
| 回测负收益 | 4 | fp_reversal_short_010, fp_amount_liquidity_014, fp_price_volume_interaction_018, fp_multi_frequency_trend_019 |

## 7. 关键观察

### 7.1 波动率类因子表现最佳

两个通过稳健性检验的因子均为波动率/风险类：
- 低波动（B）：正 IC + 正回测收益
- 下行波动（C）：弱 IC 但正回测收益

### 7.2 反转因子 IC 为正但回测为负

NEG(RET5) 的 IC 为 +0.0364（合理级别），但 Phase 2 回测收益 -20.28%。可能原因：
- 回测覆盖全时段（development + selection），development 期间信号有效但 selection 期间反转失效
- 方向一致性：Phase 2 总是做多高因子值股票（即买入超跌股），但样本外可能反转不成立

### 7.3 量价配合同样问题

MUL(RET5, VOLUME_WEIGHTED_RET) IC 为负（-0.0175），做多高因子值 = 做多高收益×高量价配合股，但回测为负。可能该组合在样本外表现与样本内相反。

### 7.4 动量类全面失败

中期动量（ZSCORE20(RET60)）覆盖率不足；多频趋势（ADD(TREND20,TREND60)）IC 为负且回测为负。动量类因子在此 6 个月窗口内无有效性。

## 8. 阶段 B 准入

| 条件 | 状态 |
| ---- | ---- |
| 存在通过 selection 的因子 | ✅ 2 个（fp_low_vol_011, fp_downside_vol_012） |
| 存在正 IC 因子 | ✅ fp_low_vol_011 (IC +0.0247) |
| 用户批准阶段 B | ⚠️ 待审批 |

可用的阶段 B 组合方向（两因子属于波动率和风险类别）：
- B4 下行波动约束：fp_downside_vol_012 + fp_low_vol_011 ✅

其他 3 个组合方向的种子因子均被淘汰，无法执行。

## 9. 禁止事项核查

- new_formula_generated: false
- random_search: false
- stage_b_started: false
- stage_c_started: false
- fast_screen_modified: false
- robustness_modified: false
- pipeline_modified: false
- threshold_modified: false
- rating_rule_modified: false
- forward_data_accessed: false
- external_data_added: false
- new_operator_added: false
- trading_advice_generated: false

## 10. 最终结论

本阶段完成第二轮阶段 A：7 个种子因子单因子历史检查。结果仅为历史研究结果，尚未经过未来前向验证，不得用于交易。
