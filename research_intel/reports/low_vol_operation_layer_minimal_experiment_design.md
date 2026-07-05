# 低波动操作层最小改造实验设计

## 1. 当前证据

### 1.1 低波动是唯一通过全流程验证的主线

| 来源 | 公式 | IC | 收益 | Sharpe | 评级 |
|------|------|-----|------|--------|------|
| 阶段 A（周度 5d） | NEG(RET_STD20) | +0.0247 | +3.68% | 0.771 | B |
| B1 baseline（月度 20d） | NEG(RET_STD20) | +0.0247 | +2.68% | 0.614 | B |

> IC 相同（0.0247）说明因子选择逻辑不变；收益和 Sharpe 差异来自调仓频率。

### 1.2 动量/反转暂时冻结

B2（动量，3/3 Rejected）和 B3（反转，2/2 Rejected）在此 6 个月窗口内方向性全面错误。不继续投入。

### 1.3 关键发现

周度调仓（5d）较月度调仓（20d）：
- 收益 +1.00pp（+3.68% vs +2.68%）
- Sharpe +0.157（0.771 vs 0.614）

这是因为低波动因子的信号衰减慢，周度调仓带来了更频繁的再平衡，分散了特质风险，且换手成本（14.9 倍/年）未显著侵蚀收益。

## 2. 实验目的

确认调仓频率是否是低波动策略的有效操作层改造点。

核心问题：

> 在固定因子 NEG(RET_STD20) 不变的前提下，AlphaGPT 能否通过调仓频率稳定优于公开 baseline（月度 20d）？

## 3. 实验范围

| 维度 | 值 |
|------|-----|
| 固定因子 | NEG(RET_STD20) |
| 比较维度 | 调仓频率 |
| 候选频率 | 5d / 10d / 20d |
| 数据库 | stock-data/ashare_research.sqlite3 |
| 时间段 | 2024-01-01 至 2024-06-28 |
| 成本 | 20 bps 单向 |
| 股票池 | CSI800 as-of |
| topN | 20 |
| 持仓方式 | 等权 |

不得加入更多参数。不得同时优化 topN、过滤条件、风控规则。

## 4. Baseline 定义

```
baseline: NEG(RET_STD20) + 20d 调仓
```

选择 20d 的理由：
- 对应公开策略 ts_low_vol_defensive_006 的"月度调仓"
- 已在 B1 baseline 复刻中运行并记录完整结果
- 收益 +2.68%，Sharpe 0.614，评级 B

## 5. AlphaGPT 改造定义

| 候选 | 公式 | 调仓 | 状态 |
|------|------|------|------|
| 改造 A | NEG(RET_STD20) | 5d | 已有阶段 A 结果 |
| 改造 B | NEG(RET_STD20) | 10d | 待运行 |

5d 结果已知（阶段 A），10d 作为中间确认点待运行。

## 6. 优于 Baseline 的判定标准

AlphaGPT 改造版必须同时满足以下条件才算"优于 baseline"：

1. 与 baseline 使用同一数据库（stock-data/ashare_research.sqlite3）
2. 与 baseline 使用同一股票池（CSI800 as-of）
3. 与 baseline 使用同一时间区间（2024-01-01 至 2024-06-28）
4. 与 baseline 使用同一交易成本（20 bps 单向）
5. 与 baseline 使用同一 T+1、涨跌停、可交易状态处理
6. 收益高于 20d baseline（即 > +2.68%）
7. Sharpe 高于 20d baseline（即 > 0.614）
8. 最大回撤不明显更差（不超 baseline 的 1.5 倍）
9. selection / stability 结果不冲突（不能一个阶段优于 baseline 而另一个阶段差于 baseline 且幅度超过 2pp）
10. 不增加策略复杂度（仅改变 rebalance_frequency 配置项）
11. 不访问 forward data

## 7. 预期结果与已知数据

| 指标 | 20d（baseline） | 10d（待测） | 5d（已知） |
|------|----------------|------------|-----------|
| 收益 | +2.68% | ? | +3.68% |
| Sharpe | 0.614 | ? | 0.771 |
| vs baseline | — | ? | 收益+1.00pp, Sharpe+0.157 |

如果 10d 的结果介于 5d 和 20d 之间且单调递增（收益：20d < 10d < 5d），则调仓频率是有效操作层参数。

## 8. 实验执行计划

```
步骤 1：生成 10d 调仓配置（仅改 rebalance_frequency: 10）
步骤 2：运行 pipeline（1 个候选，NEG(RET_STD20)）
步骤 3：与 20d（B1 baseline）和 5d（阶段 A）对比
步骤 4：判定是否满足"优于 baseline"标准
```

总计运行时间：约 70 秒（与 B1 相同规模）。

## 9. 引擎支持确认

`rebalance_frequency` 是 `BacktestConfig` 的整数参数，直接映射到 `config["backtest"]["rebalance_frequency"]`。无需修改任何代码，仅需 YAML 配置变更。

## 10. 禁止事项

- new_formula_generated: false
- new_factor_added: false
- new_feature_added: false
- new_operator_added: false
- screening_threshold_modified: false
- rating_rule_modified: false
- backtest_logic_modified: false
- pipeline_modified: false
- forward_data_accessed: false
- momentum_or_reversal_used: false
- stage_c_started: false
- trading_advice_generated: false

## 11. 最终结论

本阶段完成低波动操作层最小改造实验设计。尚未运行新回测，尚未生成新公式，尚未进入交易。
