# 低波动主候选前向观察框架设计

## 1. 前向观察目的

低波动主候选 NEG(RET_STD20) + 5d rebalance 已完成全部历史验证（阶段 A→B→baseline→10d 确认），评级 B，当前状态为冻结。

前向观察的目标是：从下一个可用交易日开始，每日仅记录该候选的理论表现，用真实新增数据判断其 IC 和回测收益是否在样本外继续成立。

## 2. 固定候选

```
candidate_id: primary_low_vol_5d
formula: NEG(RET_STD20)
rebalance_frequency: 5d
stock_pool: CSI800 as-of
top_n: 20
weighting: equal_weight
```

不可变更。

## 3. 固定参数

| 参数 | 值 | 是否可变 |
|------|-----|---------|
| formula | NEG(RET_STD20) | ❌ |
| rebalance_frequency | 5 | ❌ |
| stock_pool | CSI800 as-of | ❌ |
| topN | 20 | ❌ |
| weighting | equal_weight | ❌ |
| trading_allowed | false | ❌ |
| order_generation_allowed | false | ❌ |
| broker_connection_allowed | false | ❌ |

## 4. 每日输出

每次运行生成两个文件：

```
research_intel/forward_observation/low_vol_5d/{YYYYMMDD}_observation.json
research_intel/forward_observation/low_vol_5d/{YYYYMMDD}_observation.md
```

JSON 包含完整数据，Markdown 为可读报告。

### 4.1 每日输出字段

| 字段 | 说明 |
|------|------|
| observation_date | 观察日（数据库最新交易日） |
| database_latest_trade_date | 数据库最新日期 |
| candidate_id | primary_low_vol_5d |
| formula | NEG(RET_STD20) |
| rebalance_frequency | 5d |
| is_rebalance_day | 是否为调仓日 |
| top_n | 20 |
| csi800_member_count | CSI800 成分股数量 |
| top20 理论观察名单 | rank, code, factor_value, close, tradable, theory_weight |
| trading_allowed | **false** |
| orders_generated | **false** |
| broker_connected | **false** |

### 4.2 每只股票字段

| 字段 | 说明 |
|------|------|
| ts_code | 股票代码 |
| factor_value | NEG(RET_STD20) 的值 |
| rank | CSI800 内排名 |
| close | 收盘价 |
| is_st | 是否 ST |
| at_limit_up | 是否涨停 |
| at_limit_down | 是否跌停 |
| tradable | 可交易性判断 |
| theory_weight | 理论等权 = 1/20 |

## 5. 禁止交易说明

```
trading_allowed: false
orders_generated: false
broker_connected: false
```

本框架**永远不生成订单、不连接券商、不发出买卖建议**。所有输出仅供研究观察。

## 6. 何时判断未来是否有效

前向观察至少积累以下任一条件后，才允许重新评估：

1. 满 20 个真实交易日
2. 满 4 次 5d 调仓周期
3. 出现明显异常（连续多周期严重跑输基准）

在此之前不得因一两天涨跌下结论。

## 7. 何时停止观察

出现以下任一条件时考虑停止：

- 连续 N 个调仓周期（N ≥ 增持周期数）内 IC 持续为负或大幅弱于历史
- 前向回测收益持续为负且区别于历史结果
- 候选因子数据质量持续恶化
- 用户明确下令停止

## 8. 何时允许重新评估

满足第 6 节条件，且前向收益/IC 允许重新纳入考虑时，可生成前向评估报告。但重新评估不等于自动升级为实盘——仍需用户单独批准。

## 9. 运行方式

```powershell
python -m ashare_research.forward_observation.observe_low_vol_5d --config config/forward_observation_low_vol_5d.yaml
```

数据库不存在时安全停止。

## 10. 禁止事项

- new_backtest_run: false
- new_formula_generated: false
- parameter_optimized: false
- forward_data_accessed: false
- trading: false
- broker_connected: false

## 11. 最终结论

本阶段完成低波动主候选前向观察框架设计。仅观察 NEG(RET_STD20) + 5d rebalance，不交易、不生成订单、不接券商。
