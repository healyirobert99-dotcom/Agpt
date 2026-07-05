# 成熟公开策略拆解与 AlphaGPT 重组实验设计

## 1. 方向定位

本报告标志 AlphaGPT 研究方向的调整：

- **过去**：把公开策略拆成单因子裸测 → 7 个因子只有 1 个 B 级通过
- **现在**：从公开策略中拆解"因子 + 股票池 + 过滤 + 排序 + 持仓 + 调仓 + 风控"的完整组件体系，在 AlphaGPT 统一数据/成本/回测口径下做有限重组
- **目标**：寻找优于原始 baseline 的共性组合，而非无脑跟随原策略

## 2. 策略库全貌

Firecrawl 已抓取 20 条公开操作策略。按类型分类：

| 类型 | 数量 | 代表 |
| ---- | ---- | ---- |
| 多因子选股 | 4 | 月度排序、价值+质量、基本面+技术面、TopN等权 |
| 动量 | 1 | 动量+流动性过滤 |
| 反转 | 1 | 短期反转均值回归 |
| 低波动 | 1 | 低波动防御组合 |
| 小市值 | 1 | 小市值+质量过滤 |
| 指数增强 | 2 | 行业中性增强、宏观-行业-个股分层 |
| ETF轮动 | 1 | ETF动量轮动 |
| 风控择时 | 5 | 市场过滤、止损止盈、换手预算、流动性门槛、研报覆盖 |
| 其他 | 2 | 市场中性多空（美股）、全链条审计 |
| 成长+质量/价值+质量 | 2 | 基本面组合策略 |

### 2.1 数据依赖分析

| 数据需求 | 策略数 | AlphaGPT 支持 |
| -------- | ------ | ------------- |
| 仅日线价量 | 8 | ✅ 完全支持 |
| 日线价量 + 市值 | 10 | ⚠️ 需确认市值字段 |
| 日线价量 + 财务 | 7 | ❌ 当前不支持 |
| 日线价量 + 行业 | 5 | ❌ 当前不支持 |
| ETF 数据 | 1 | ❌ 当前不支持 |
| 新闻/研报文本 | 1 | ❌ 当前不支持 |

## 3. AlphaGPT 当前引擎能力矩阵

### 3.1 已支持

| 组件类别 | 能力 | 实现位置 |
| -------- | ---- | -------- |
| 股票池 | CSI800 as-of | pipeline → ResearchContext |
| ST 过滤 | ✅ 历史 ST 状态过滤 | backtest/engine.py |
| 停牌过滤 | ✅ 不可交易日排除 | backtest/engine.py |
| 涨跌停过滤 | ✅ 涨停不可买、跌停不可卖 | backtest/engine.py |
| T+1 执行 | ✅ 信号日 + 1 交易日执行 | backtest/engine.py |
| 调仓频率 | ✅ 可配置 (rebalance_frequency) | config → BacktestConfig |
| TopN 选股 | ✅ 可配置 (top_n) | config → BacktestConfig |
| 等权持仓 | ✅ fixed | pipeline (hardcoded) |
| 交易成本 | ✅ 可配置 (20 bps) | config → BacktestConfig |
| long-only | ✅ fixed | pipeline (hardcoded) |

### 3.2 当前不支持

| 组件类别 | 缺失能力 | 影响 |
| -------- | -------- | ---- |
| 行业中性 | 行业分类数据 + 行业内排序 | 指数增强策略无法复刻 |
| 多因子加权 | 仅支持单因子排序 | 所有多因子策略无法直接复刻 |
| 市值过滤 | 需确认 CSI800 权重/total_mv 字段 | 小市值/市值中性策略受限 |
| 风险平价 | 无组合方差计算 | 风控策略受限 |
| 止盈止损 | 无事件触发退出 | 仅能做定期调仓 |
| 市场状态过滤 | 无择时信号层 | 风控择时类无法复刻 |
| 基本面数据 | 无财务/PE/PB/ROE 等 | 7 条策略无法复刻 |
| 仓位约束（非等权） | 硬编码 top_n_long_only_equal_weight | 波动加权、流动性加权不可 |
| 信号触发调仓 | 仅固定频率调仓 | 事件驱动策略不可 |

### 3.3 可最小扩展支持

以下组件可以通过少量配置变更（不修改核心引擎代码）支持：

| 扩展项 | 方式 | 难度 |
| ------ | ---- | ---- |
| 多因子组合 | 在候选公式层用 ADD/MUL 组合因子 | 低（阶段 B 已验证可行） |
| 成交额过滤 | 将 AMOUNT_MA 作为 gate（在候选层表达） | 低 |
| 波动率过滤 | 将 RET_STD 作为 gate | 低 |
| 换手预算 | 调整 rebalance_frequency | 低 |

## 4. 第一批 baseline 策略选择

从 20 条策略中选出 3 条最适合复刻的，标准：
1. 规则清楚，可精确复刻
2. 数据当前可支持（无财务/行业依赖）
3. 可在现有引擎或少量扩展下实现
4. 与阶段 A/B 结果有直接联系
5. 有明确的 AlphaGPT 改造空间

### 第一批 3 个 baseline

| # | strategy_id | 名称 | 类型 | 可复刻性 | 改造空间 |
|---|------------|------|------|---------|---------|
| 1 | ts_low_vol_defensive_006 | 低波动防御组合 | 低波动 | high | ★★★ 替换为 NEG(RET_STD20) |
| 2 | ts_momentum_liquidity_filter_004 | 动量+流动性过滤 | 动量 | high | ★★ 动量方向优化 |
| 3 | ts_short_reversal_005 | 短期反转均值回归 | 反转 | high | ★★ 量价配合确认 |

> 详见 baseline_reconstruction_candidate_list.jsonl

## 5. 优于原策略的判定标准

AlphaGPT 改造版只有同时满足以下 12 个条件，才算"优于 baseline"：

1. 与 baseline 使用同一数据库
2. 与 baseline 使用同一股票池
3. 与 baseline 使用同一交易成本（20 bps）
4. 与 baseline 使用同一时间分段（development/selection/stability）
5. 与 baseline 使用同一可交易状态、涨跌停、T+1 处理
6. 总收益不低于 baseline
7. Sharpe 或 Sortino 优于 baseline
8. 最大回撤不劣于 baseline，或收益/回撤比明显改善
9. selection / stability 表现不冲突（不能一个阶段优另一个阶段差）
10. 不依赖更多外部数据
11. 不显著增加复杂度（token 数或操作层数不翻倍）
12. 不访问 forward data

## 6. AlphaGPT 重组实验空间

### 6.1 因子组件

| 来源 | 可用因子 |
| ---- | -------- |
| 已验证种子因子 | NEG(RET_STD20) — B 级主候选 |
| 辅助观察 | NEG(DOWNSIDE_RET_STD20) — C 级 |
| 策略拆解因子 | 动量（RET60/RET120）、反转（NEG(RET1/RET5)）、波动（RET_STD20/60） |
| 禁止引入 | 无来源新因子、财务因子、行业因子 |

### 6.2 过滤组件

| 过滤条件 | 数据支持 | 表达方式 |
| -------- | -------- | -------- |
| CSI800 | ✅ | 沿用现有 pipeline |
| ST | ✅ | 回测引擎已处理 |
| 停牌/不可交易 | ✅ | 回测引擎已处理 |
| 涨跌停 | ✅ | 回测引擎已处理 |
| 成交额下限 | ✅ | AMOUNT_MA20 在候选层表达为 gate |
| 波动率上限 | ✅ | RET_STD20 在候选层表达为 gate |
| 市值 | ⚠️ | 待确认字段 |
| 行业 | ❌ | 不支持 |
| 价格下限 | ✅ | close 可直接使用 |

### 6.3 排序组件

| 排序方式 | 引擎支持 | 说明 |
| -------- | -------- | ---- |
| 单因子排序 | ✅ | 当前模式 |
| 多因子等权排序 | ⚠️ | 需在候选层用 ADD 组合（阶段 B 已验证） |
| 先过滤后排序 | ⚠️ | 需候选层表达 gate 逻辑 |
| 分层排序 | ❌ | 引擎不支持 |

### 6.4 持仓与调仓组件

| 组件 | 引擎支持 | 说明 |
| ---- | -------- | ---- |
| topN | ✅ | 可配置 N |
| 等权 | ✅ | hardcoded |
| 月度调仓 | ✅ | rebalance_frequency=20 |
| 周度调仓 | ✅ | rebalance_frequency=5 |
| 波动加权 | ❌ | 不支持非等权 |
| 信号触发 | ❌ | 仅固定频率 |

### 6.5 风控组件

| 风控 | 引擎支持 | 状态 |
| ---- | -------- | ---- |
| 最大回撤控制 | ❌ | 待开发 |
| 市场趋势过滤 | ❌ | 待开发 |
| 止损 | ❌ | 待开发 |
| 空仓等待 | ❌ | 待开发 |

## 7. 实验流程设计

### 第一阶段：baseline 复刻

```
1. 根据策略拆解 map，构造本地 baseline 表达式/配置
2. 使用阶段 A 同一口径运行 pipeline
3. 记录 baseline 的 IC / 收益 / Sharpe / 回撤
4. 作为不可修改的对照基准
```

### 第二阶段：组件替换

```
1. 对每个 baseline，在单个组件上做替换：
   - 替换因子（如原策略的波动率因子 → NEG(RET_STD20)）
   - 添加过滤（如原策略无成交额过滤 → 添加 AMOUNT_MA20 gate）
   - 调整调仓频率
2. 每次只改一个组件，保持其他不变
3. 记录每次替换的结果
```

### 第三阶段：有限组合

```
1. 将第二阶段中有效果的组件替换组合
2. 最多组合 3 个组件的变更
3. 验证组合是否产生协同效应
```

## 8. 与阶段 A/B 结果的关系

| 阶段 | 作用 | 本次关联 |
| ---- | ---- | -------- |
| 阶段 A | 验证 7 个单因子 | NEG(RET_STD20) B 级 → baseline 1 的因子层 |
| 阶段 B | 验证低波动+下行波动组合 | ADD 组合方式 → baseline 的多因子表达 |
| 操作层设计 | 本次 | 将因子嵌入完整策略结构 |

## 9. 下一步建议

- ✅ 审核并通过 3 个 baseline 策略
- ✅ 对每个 baseline 做本地最小复刻实验
- ❌ 不继续阶段 C
- ❌ 不扩大随机搜索
- ❌ 不交易

## 10. 禁止事项核查

- new_backtest_run: false
- stage_c_started: false
- new_formula_generated: false
- random_search_started: false
- new_factor_added: false
- new_feature_added: false
- new_operator_added: false
- threshold_modified: false
- rating_rule_modified: false
- backtest_modified: false
- pipeline_modified: false
- time_split_modified: false
- forward_data_accessed: false
- trading_advice_generated: false

## 11. 最终结论

本阶段完成成熟公开策略拆解与 AlphaGPT 重组实验设计。尚未运行新回测，尚未生成新公式，尚未进入交易。
