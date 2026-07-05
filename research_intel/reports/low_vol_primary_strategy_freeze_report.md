# 低波动主候选最终冻结报告

## 1. 研究边界

- 不交易
- 不自动下单
- 不接券商
- 不给买卖建议
- 仅为历史研究结果
- 尚未经过未来前向验证

## 2. 历史验证路径

按时间顺序：

1. **阶段 A**（7 种子因子单因子检查）→ NEG(RET_STD20) 评级 B，唯一通过全流程的因子
2. **阶段 B**（低波动 + 下行波动组合）→ ADD 组合评级 C，未优于单因子
3. **Baseline 复刻**（低波动月度 20d）→ 收益 +2.68%，Sharpe 0.614，评级 B
4. **10d 调仓确认实验** → 收益 +2.58%，Sharpe 0.559，评级 B，不优于 baseline 也不优于 5d

## 3. 候选对比

| 版本 | 因子 | 调仓 | 收益 | Sharpe | 评级 | 结论 |
|------|------|------|------|--------|------|------|
| **AlphaGPT 当前主候选** | NEG(RET_STD20) | 5d | **+3.68%** | **0.771** | B | **保留** |
| 10d 确认实验 | NEG(RET_STD20) | 10d | +2.58% | 0.559 | B | 不推进 |
| 20d baseline | NEG(RET_STD20) | 20d | +2.68% | 0.614 | B | 被 5d 超越 |
| 下行波动观察 | NEG(DOWNSIDE_RET_STD20) | 5d | +5.73% | 1.173 | C | 辅助观察，IC 极弱 |
| 阶段 B 组合 | ADD(NEG(RET_STD20),NEG(DOWNSIDE_RET_STD20)) | 5d | +3.90% | 0.822 | C | 评级低于主候选 |

## 4. 为什么保留 5d

- 5d 收益最高（+3.68%），在所有三频率中排名第一
- 5d Sharpe 最高（0.771），风险调整后表现最佳
- 5d 明确优于 20d baseline（收益 +1.00pp，Sharpe +0.157）
- 10d 未验证线性优势（U 型关系：5d > 20d > 10d）
- 阶段 B 组合未提升评级（B → C）
- 因此不继续调仓频率优化，不继续组合扩展

## 5. 冻结状态

```
primary_strategy_candidate: NEG(RET_STD20) + 5d rebalance
grade: B
status: frozen_for_forward_observation
trading_allowed: false
forward_validated: false

candidate_frozen: true
next_action: forward_observation_only
new_backtest_recommended: false
stage_c_recommended: false
parameter_search_recommended: false
```

## 6. 后续前向观察建议

- 等待未来数据（2024-07-01 之后）做前向观察
- 记录后续真实交易日表现
- 不改变公式（NEG(RET_STD20)）
- 不改变调仓频率（5d）
- 不改变筛选/评级逻辑
- 不交易
- 不自动下单

不得：
- 继续扫调仓频率
- 扩大搜索
- 直接实盘
- 自动交易
- 接入券商

## 7. 禁止事项核查

- new_backtest_run_after_10d: false
- new_formula_generated: false
- new_factor_search_started: false
- parameter_search_started: false
- stage_c_started: false
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

本阶段完成低波动主候选最终冻结。当前主候选为 NEG(RET_STD20) + 5d rebalance，仅作为历史候选进入前向观察，不得用于交易。
