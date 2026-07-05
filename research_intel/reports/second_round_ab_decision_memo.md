# AlphaGPT 第二轮阶段 A/B 收官决策备忘录

## 1. 本次研究边界

- 只验证 7 个公开来源种子因子（来自 second_batch_seed_factor_manifest.jsonl）
- 阶段 A 为 7 个种子单因子逐一检查
- 阶段 B 只验证低波动 + 下行波动极窄组合（fp_low_vol_011 + fp_downside_vol_012）
- 未启动阶段 C
- 未使用库外因子
- 未新增特征或算子（全部使用已批准的 16 个基础特征 + 10 个算子）
- 未修改筛选、评级、回测逻辑
- 未访问 forward data（research_end = 20240628，远早于 cutoff 20260626）
- 未产生交易建议

## 2. 阶段 A 结果摘要

| seed_factor_id | 名称 | 公式 | fast_screen | IC | 回测收益 | Sharpe | 评级 | 状态 |
|---------------|------|------|-------------|-----|---------|--------|------|------|
| fp_momentum_mid_009 | 中期动量 | ZSCORE20(RET60) | ❌ rejected | -0.1206 | — | — | Rejected | 覆盖率 0.281 < 0.30 |
| fp_reversal_short_010 | 短期反转 | NEG(RET5) | ✅ passed | +0.0364 | -20.28% | -1.313 | Rejected | 回测负收益 |
| **fp_low_vol_011** | **低波动** | **NEG(RET_STD20)** | ✅ passed | **+0.0247** | **+3.68%** | **0.771** | **B** | ✅ **主候选** |
| fp_downside_vol_012 | 下行波动 | NEG(DOWNSIDE_RET_STD20) | ✅ passed | -0.0045 | +5.73% | 1.173 | C | ✅ 辅助候选 |
| fp_amount_liquidity_014 | 流动性 | ZSCORE20(AMOUNT_MA20) | ✅ passed | -0.0579 | -21.80% | -1.964 | Rejected | 回测负收益 |
| fp_price_volume_interaction_018 | 量价配合 | MUL(RET5,VOLUME_WEIGHTED_RET) | ✅ passed | -0.0175 | -17.09% | -1.223 | Rejected | 回测负收益 |
| fp_multi_frequency_trend_019 | 多频趋势 | ADD(TREND20,TREND60) | ✅ passed | -0.0572 | -11.39% | -1.440 | Rejected | 回测负收益 |

**关键发现：只有波动率/风险类因子通过全流程验证。动量、反转、流动性、量价配合在此 6 个月窗口内均无效。**

## 3. 阶段 B 结果摘要

| 候选 | 公式 | fast_screen | IC | 相关性 | 回测收益 | Sharpe | 评级 | 状态 |
|------|------|-------------|-----|-------|---------|--------|------|------|
| B1 等权 | ADD(NEG(RET_STD20),NEG(DOWNSIDE_RET_STD20)) | ✅ | +0.0149 | kept | +3.90% | 0.822 | C | shortlisted |
| B2 交互 | MUL(NEG(RET_STD20),NEG(DOWNSIDE_RET_STD20)) | ✅ | -0.0112 | deduped (r=-0.997) | — | — | — | 相关性剔除 |

### 与阶段 A 最佳单因子对比

| 指标 | NEG(RET_STD20) 阶段 A | ADD(…) 阶段 B | 变化 |
| ---- | ---------------------- | ------------- | ---- |
| rank_ic_mean | **+0.0247** | +0.0149 | ↓ 40% |
| 回测收益 | +3.68% | +3.90% | +0.22pp |
| Sharpe | 0.771 | 0.822 | +0.05 |
| 评级 | **B** | C | ↓ |

**stage_b_improved_over_stage_a: false**

下行波动因子的加入稀释了 IC，组合未能提升低波动单因子的核心指标。收益和 Sharpe 的边际改进不足以抵消 IC 削弱带来的评级降级。

## 4. 项目级候选冻结结论

```
primary_candidate: NEG(RET_STD20)
primary_candidate_grade: B

secondary_observation_candidate: NEG(DOWNSIDE_RET_STD20)
secondary_observation_candidate_grade: C

stage_b_combination_promoted: false
stage_c_recommended: false
```

说明：

- `NEG(RET_STD20)` 是当前第二轮最干净的历史候选。IC 为正（+0.0247）、回测正收益（+3.68%）、Sharpe 0.771、最大回撤 -5.01%，所有指标均通过稳健性检验，评级 B。
- `NEG(DOWNSIDE_RET_STD20)` 可作为辅助观察，其收益（+5.73%）和 Sharpe（1.173）优于主候选，但 IC 极弱（-0.0045），不应升级为主候选。
- 阶段 B ADD 组合不应推进。评级从 B 降至 C，IC 削弱 40%，未产生实质性增量。
- 阶段 C 暂停。

## 5. 为什么不继续阶段 C

1. **阶段 B 未优于阶段 A。** 组合未产生增量，继续同源派生预期也不会好于单因子。
2. **波动率族已验证出主候选。** RET_STD20 相关特征族已通过阶段 A 和阶段 B 验证，进一步挖掘边际收益递减。
3. **继续组合会增加过拟合风险。** 特征族内窄派生容易产生高相关性候选（如 B2 与 B1 的 r=-0.997），在 6 个月样本上极易过拟合。
4. **当前更需要前向观察。** 历史内的挖掘已覆盖核心场景，真正重要的是等待未来数据验证 IC 的持久性，而非继续在历史数据中寻找更复杂的组合。

## 6. 下一步建议

- 建立历史候选观察清单（见 frozen_candidate_watchlist.jsonl）
- 等待未来数据（2024-07-01 之后）做前向观察
- 不进入交易
- 不自动下单
- 不扩大搜索
- 不继续阶段 C

## 7. 禁止事项核查

- stage_c_started: false
- random_formula_generated: false
- new_factor_search_started: false
- new_backtest_run_after_stage_b: false
- new_feature_added: false
- new_operator_added: false
- external_data_added: false
- fast_screen_modified: false
- robustness_modified: false
- pipeline_modified: false
- threshold_modified: false
- rating_rule_modified: false
- forward_data_accessed: false
- trading_advice_generated: false

## 8. 最终结论

本阶段完成第二轮阶段 A/B 收官决策与候选冻结。当前仅保留 NEG(RET_STD20) 为 B 级历史主候选，NEG(DOWNSIDE_RET_STD20) 为 C 级辅助观察候选。所有结果仅为历史研究结果，尚未经过未来前向验证，不得用于交易。
