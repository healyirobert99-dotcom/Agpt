# 低波动 10d 调仓确认实验报告

## 1. 运行信息

| 项目 | 值 |
| ---- | --- |
| run_id | factor_research_v2_20260705_160838 |
| commit SHA | 0374d064b60111d07926f74d717d1675f54c3671 |
| 耗时 | 68.6 秒 |
| 数据库 | stock-data/ashare_research.sqlite3 |
| 是否只运行 NEG(RET_STD20) | ✅ |
| 是否只改 rebalance_frequency: 10 | ✅ |
| 是否新增公式 | 否 |
| 是否新增特征或算子 | 否 |
| 是否修改筛选/评级/回测逻辑 | 否 |
| 是否访问 forward data | 否 |

## 2. 10d 结果

| 指标 | 值 |
| ---- | --- |
| 公式 | NEG(RET_STD20) |
| 调仓频率 | 10d（双周） |
| rank_ic_mean | +0.0247 |
| 回测总收益 | +2.58% |
| Sharpe | 0.559 |
| 最大回撤 | -5.78% |
| 评级 | B |

## 3. 三频率对比

| 指标 | 5d（周度） | 10d（双周） | 20d（月度 baseline） |
| ---- | --------- | ---------- | ------------------- |
| rank_ic_mean | +0.0247 | +0.0247 | +0.0247 |
| 回测总收益 | **+3.68%** | +2.58% | +2.68% |
| Sharpe | **0.771** | 0.559 | 0.614 |
| 最大回撤 | **-5.01%** | -5.78% | — |
| 评级 | B | B | B |

```
收益排序: 5d (+3.68%) > 20d (+2.68%) > 10d (+2.58%)
Sharpe 排序: 5d (0.771) > 20d (0.614) > 10d (0.559)
```

## 4. 胜出判定

### vs 20d baseline

| 条件 | 10d | baseline | 通过 |
|------|-----|----------|------|
| 收益 > +2.68% | +2.58% | +2.68% | ❌ |
| Sharpe > 0.614 | 0.559 | 0.614 | ❌ |
| 最大回撤不明显更差 | -5.78% | — | ⚠️ |
| 不增加复杂度 | ✅ | — | ✅ |
| 不访问 forward data | ✅ | — | ✅ |

**rebalance_10d_beats_20d_baseline: false**

### vs 5d 改造版

**rebalance_10d_beats_5d_variant: false**

10d 在所有指标上均逊于 5d。

## 5. 核心发现：非单调关系

```
5d  ████████████  3.68%
10d ████████      2.58%
20d █████████     2.68%
```

三频率对比呈现 U 型关系：**5d 最优，20d 次之，10d 最差。**

这否定了"调仓频率越高越好"的简单假设，也否定了单调递减假设。可能原因：

1. **10d 恰好落入了一个不理想的调仓节奏**——可能频繁在月底/月初 window-dressing 效应前后调仓，增大了 timing 噪声。
2. **5d 的高频再平衡分散了特质风险**，20d 的低频降低了成本摩擦，10d 则两边不靠——不够频繁到分散、也不够低频到省成本。
3. **样本内 noise**：6 个月样本太短，三个频率的差异可能只是噪声。

## 6. 结论

| 结论 | 值 |
|------|-----|
| rebalance_10d_beats_20d_baseline | **false** |
| rebalance_10d_beats_5d_variant | **false** |
| rebalance_frequency_is_reliable_lever | **unconfirmed** |
| 调仓频率建议 | 保持 5d（周度），不做 10d |

虽然 5d 优于 20d（已验证），但 10d 的失败说明**调仓频率不是简单的线性优化参数**，不能仅凭"更频繁"或"更低频"来保证改进。5d 的优势可能更多来自特定市场节奏匹配，而非频率本身。

**推荐将 5d 作为低波动策略的默认配置保留，不再继续调仓频率方向。**

## 7. 禁止事项核查

- other_frequencies_tested: false
- topN_optimized: false
- new_filter_added: false
- new_formula_generated: false
- new_feature_added: false
- new_operator_added: false
- screening_modified: false
- rating_modified: false
- backtest_modified: false
- time_split_modified: false
- forward_data_accessed: false
- stage_c_started: false
- momentum_or_reversal_used: false
- trading_advice_generated: false

## 8. 最终结论

本阶段完成低波动 10d 调仓确认实验。结果仅为历史研究结果，尚未经过未来前向验证，不得用于交易。
