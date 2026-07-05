# 低波动 locked blind test 失败与 IC/PnL 背离诊断

## 1. 结论摘要

```
historical_blind_test_passed: false (absolute return)
excess_return_vs_benchmark: positive in 4/5 periods
primary_candidate_status: relative_factor_watch_only
trading_allowed: false
forward_observation_recommended: only_as_relative_benchmark_alpha
```

**核心发现：该因子不是"策略失败"，而是被误解了。它是一个强相对收益因子，在绝对熊市中无法独立盈利，但跑赢基准的能力一致且显著。**

## 2. locked blind test 结果回顾

| 区间 | IC | 收益 | Sharpe | DD | 评级 |
|------|-----|------|--------|-----|------|
| 2021 | +0.076 | -1.18% | -0.151 | -12.4% | Rejected |
| 2022 | +0.077 | -17.79% | -1.569 | -19.9% | Rejected |
| 2023 | +0.075 | -12.26% | -1.356 | -19.4% | Rejected |
| 2021-2023 | +0.080 | -24.02% | -0.884 | -29.8% | Rejected |
| 2024 发现期 | +0.025 | +3.68% | +0.771 | -5.0% | B |

## 3. benchmark 与 excess return 诊断

| 区间 | 组合收益 | CSI800 收益 | **超额收益** | 跑赢基准 |
|------|---------|------------|------------|---------|
| 2021 | -1.18% | -1.98% | **+0.80%** | ✅ |
| 2022 | -17.79% | -21.03% | **+3.24%** | ✅ |
| 2023 | -12.26% | -11.00% | **-1.26%** | ❌ |
| **2021-2023** | **-24.02%** | **-30.87%** | **+6.85%** | ✅ |
| 2024 发现期 | +3.68% | -0.72% | **+4.40%** | ✅ |

**2021-2023 三年累计超额 +6.85%。五个区间中四个跑赢基准。**

## 4. IC/PnL 背离原因分析

### 4.1 根本原因：long-only 在熊市中必然亏损

2021-2023 是 A 股整体下跌周期：CSI800 三年累计 -30.87%。任何全仓 long-only 策略在这个周期中都难以产生正收益。低波动组合虽然提供了防御属性（只亏 24%），但不具备独立产生正收益的能力。

**IC 测量的是截面排序能力（选股 alpha），PnL 测量的是绝对收益（选股 alpha + 市场 beta）。两者不在同一维度。**

### 4.2 IC 与收益的转换过程

```
IC +0.080 (强截面排序)
  ↓ 选股：选对了相对低波动的标的
  ↓ 但在全市场下跌中，选对的股票也在跌
  ↓ 绝对收益为负
  ↓ 但相对收益为正 (excess +6.85%)
```

这是典型的"相对 alpha"——因子能做的是在下跌市场中少跌，而不是不跌。

### 4.3 成本与换手

| 区间 | 年化换手 | 成本侵蚀估计 | 成本前收益估计 |
|------|---------|------------|-------------|
| 2021 | 24.4x | -4.88% | +3.53% |
| 2022 | 20.5x | -4.10% | -13.85% |
| 2023 | 33.8x | -6.76% | -5.77% |

- 年化换手 20-34x，对 20 bps 单向成本，成本侵蚀 4-7%/年
- 2021 年成本前为正（+3.53%），成本后转为 -1.18%
- 2022 年和 2023 年即使成本前也为负
- 成本是重要因素但不是主要因素——市场方向才是

## 5. 因子方向诊断

- `NEG(RET_STD20)` 确实表示低波动高分 ✅
- Phase 2 做多高因子值 ✅
- 方向逻辑正确：低波动 → 高因子值 → 做多 ✅
- 无 sign inversion 问题
- 不需要 long-low

## 6. 市场环境诊断

| 区间 | 市场环境 | 组合表现 | 特征 |
|------|---------|---------|------|
| 2021 | 震荡微跌 (-2%) | -1.18%，轻微跑赢 | 防御属性适中 |
| 2022 | 大幅下跌 (-21%) | -17.79%，跑赢 3.24% | 强防御属性 |
| 2023 | 中幅下跌 (-11%) | -12.26%，微幅跑输 | 防御属性弱化 |
| 2024H1 | 微跌 (-0.7%) | +3.68%，大幅跑赢 | 防御 + 选股协同 |

**低波动因子在弱市中提供防御，但防御效果不稳定。2023 年跑输基准说明单纯低波动在特定市场结构中可能不够。**

## 7. 未来函数审计复核

| 审计项 | 状态 | 说明 |
|--------|------|------|
| factor_lookback_only | ✅ true | RET_STD20 只用信号日及之前数据 |
| csi800_asof_membership | ✅ true | CSI800 使用 as-of 历史成分 |
| t_plus_1_execution | ✅ true | t 日信号 → t+1 执行 |
| tradability_asof | ✅ true | 使用交易当时可交易状态 |
| rebalance_calendar_fixed | ✅ true | 5d 固定调仓 |
| post_period_data_not_used | ✅ true | 每区间独立运行，不跨区间泄漏 |

**未发现未来函数问题。**

## 8. 候选状态建议

```
primary_candidate_status: relative_factor_watch_only
```

选择理由：

- absolute return 在 2021-2023 为负 → 不能作为独立绝对收益策略
- excess return 在 4/5 区间为正，三年累计 +6.85% → 有相对价值
- IC 持续强正（0.075-0.080），截面排序能力稳定 → 因子本身有效
- 它是 alpha 因子，不是市场择时因子 → 功能定义准确
- **降级为相对收益观察候选，不做绝对收益推荐**

```json
{
  "historical_blind_test_passed": false,
  "historical_blind_test_excess_passed": true,
  "primary_candidate_status": "relative_factor_watch_only",
  "trading_allowed": false,
  "forward_observation_recommended": true,
  "forward_observation_scope": "relative_excess_return_only",
  "notes": "该因子是强相对alpha，不是绝对收益策略。做多低波动在熊市中只是少跌。需配合市场方向判断才能产生绝对正收益。"
}
```

## 9. 下一步建议

- ✅ 将 NEG(RET_STD20) 降级为相对收益观察候选
- ✅ 保留前向观察，但仅记录 excess return
- ✅ 识别该因子为"防御/相对 alpha"，不是"绝对收益策略"
- ❌ 不继续调参试图让它在熊市中产生正收益
- ❌ 不加择时/止损来"救"它
- ❌ 不交易
- ❌ 不扩大搜索

## 10. 禁止事项核查

- formula_changed: false
- rebalance_frequency_changed: false
- topN_changed: false
- parameter_search_started: false
- new_formula_generated: false
- new_factor_search_started: false
- new_feature_added: false
- new_operator_added: false
- screening_threshold_modified: false
- rating_rule_modified: false
- backtest_logic_modified: false
- forward_data_accessed: false
- trading_advice_generated: false

## 11. 最终结论

本阶段完成低波动 locked blind test 失败诊断。当前不交易，不调参，不继续挽救候选。
