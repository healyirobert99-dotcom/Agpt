# 低波动因子相对收益状态更新

## 1. 状态修正

- **原先状态**：primary_strategy_candidate，冻结为历史主候选
- **locked blind test 后**：2021-2023 绝对收益全部为负，不得作为独立绝对收益策略
- **新状态**：`relative_factor_watch_only`
- **修正日期**：2026-07-05
- **触发事件**：locked historical blind test 2021-2023 全区间绝对收益为负，但 excess return 在 4/5 区间为正

```json
{
  "candidate_id": "relative_low_vol_5d",
  "formula": "NEG(RET_STD20)",
  "rebalance_frequency": 5,
  "previous_status": "primary_strategy_candidate",
  "new_status": "relative_factor_watch_only",
  "absolute_return_strategy": false,
  "relative_alpha_factor": true,
  "forward_observation_focus": "excess_return_vs_CSI800",
  "trading_allowed": false
}
```

## 2. 为什么不是绝对收益策略

| 证据 | 数据 |
|------|------|
| 2021 绝对收益 | -1.18% |
| 2022 绝对收益 | -17.79% |
| 2023 绝对收益 | -12.26% |
| 2021-2023 绝对收益 | -24.02% |
| 所有盲测区间 Sharpe | 全部为负 |
| long-only 在弱市场 | 无法独立产生正收益 |

该因子做多低波动股票。在全市场下跌周期（2021-2023 CSI800 -30.87%），即使选股完全正确，持仓仍然在跌。这不是因子失效，而是因子类型与市场环境不匹配：**它选的是"跌得少的"，不是"涨的"。**

## 3. 为什么仍有研究价值

| 证据 | 数据 |
|------|------|
| IC | 2021-2023 持续 +0.075 至 +0.080，是发现期的 3 倍 |
| 2021-2023 累计超额 | **+6.85%**（跑赢 CSI800） |
| 跑赢基准区间数 | 4/5（80%） |
| 2022 年防御效果 | CSI800 -21.03%，组合仅 -17.79% |
| 未来函数审计 | 6/6 true |

该因子的截面排序能力在样本外不仅没有衰减，反而更强。它的价值在于：

- **相对选股**：在给定市场中选出相对更优的标的
- **防御增强**：降低组合在市场下跌中的损失
- **组合过滤**：作为低风险资产覆盖层的候选组件

它不能独立交易，但可以作为策略体系中的"防御层"，与市场方向判断配合。

## 4. 后续观察重点

```
forward_observation_metric_priority:
1. excess_return_vs_CSI800     ← 主指标
2. rolling_5d_excess           ← 短期相对表现
3. rolling_20d_excess          ← 中期相对表现
4. relative_drawdown           ← 相对回撤
5. turnover                    ← 换手率
6. absolute_return             ← 仅作次要参考
```

判定规则：

- **组合绝对收益为负 + excess_return 为正 → 记录为"相对跑赢"，不是策略失败**
- **组合绝对收益为正 + excess_return 为负 → 记录为"相对跑输"**
- 不因绝对收益涨跌判断因子是否有效

## 5. 禁止事项核查

- absolute_strategy_promoted: false
- trading_allowed: false
- new_backtest_run: false
- new_formula_generated: false
- parameter_changed: false
- forward_data_accessed: false
- broker_connected: false
- order_generated: false
- market_timing_added: false
- stop_loss_added: false

## 6. 最终结论

本阶段完成低波动候选状态修正。NEG(RET_STD20) + 5d 不再作为绝对收益主策略推进，仅作为相对 alpha 因子进入观察，不交易、不生成订单、不接券商。
