# AlphaGPT v2 第二轮最小搜索运行草案

## 1. 文档状态

- 状态：待审批草案
- 审批要求：需用户明确批准后才能启动任何阶段
- 本次未运行搜索、未运行回测、未生成公式、未修改研究口径

## 2. 前提确认

| 约束项 | 状态 |
| ------ | ---- |
| 第二轮门禁检查器 | 已完成并通过 targeted tests |
| 7 个种子因子 | 已冻结，来源已验证 |
| 16 个基础特征（5 原有 + 11 新增） | 已实现并通过 targeted tests |
| 10 个算子 | 不变，不新增 |
| 筛选标准 | 不变 |
| 评级标准 | 不变 |
| time split | 不变 |
| forward data | 禁止访问 |
| 外部数据 | 禁止新增 |

## 3. 7 个种子因子清单

| ID | 名称 | 类别 | 可计算性 | 需要新特征 |
| -- | ---- | ---- | -------- | --------- |
| fp_momentum_mid_009 | 中期价格动量 | 动量 | computable_with_minor_feature_derivation | 是 (RET20, RET60, RET120, TREND20, TREND120) |
| fp_reversal_short_010 | 短期反转 | 反转 | computable_with_current_data | 否 |
| fp_low_vol_011 | 低波动 | 波动率 | computable_with_minor_feature_derivation | 是 (RET_STD20, RET_STD60) |
| fp_downside_vol_012 | 下行波动 | 风险 | computable_with_minor_feature_derivation | 是 (DOWNSIDE_RET_STD20, DOWNSIDE_RET_STD60) |
| fp_amount_liquidity_014 | 成交额流动性 | 流动性 | computable_with_minor_feature_derivation | 是 (AMOUNT_MA20, AMOUNT_MA60) |
| fp_price_volume_interaction_018 | 量价配合 | 量价配合 | computable_with_current_data | 否 |
| fp_multi_frequency_trend_019 | 多频趋势 | 动量 | computable_with_minor_feature_derivation | 是 (TREND20, TREND120) |

说明：`fp_reversal_short_010` 和 `fp_price_volume_interaction_018` 可直接用现有特征计算；其余 5 个因子需要已批准但尚未在 AlphaGPT 词汇表中启用的派生特征。在特征正式审批并暴露给 vocabulary 之前，这 5 个因子只能做设计层面的登记，不能做实际执行。

## 4. 阶段 A：种子因子单因子检查

### 4.1 目标

对 7 个已冻结种子因子逐一做单因子可计算性和基础表现检查。这是整个第二轮搜索的起点——只有单因子性能明确后，配对和派生才有参考基准。

### 4.2 方法

每个种子因子在 AlphaGPT v2 框架中表达为**一个**候选公式：

| 种子因子 | 特征依赖 | 预期表达方式 |
| -------- | -------- | ------------ |
| fp_reversal_short_010 | RET1, RET5 | NEG(RET5) 或 ZSCORE20(NEG(RET1)) — 短期负收益选股 |
| fp_price_volume_interaction_018 | RET5, VOLUME_WEIGHTED_RET, VOL_RATIO20 | MUL(RET5, VOLUME_WEIGHTED_RET) — 收益×量价确认 |
| fp_momentum_mid_009 | RET20, RET60, RET120, TREND60 | 登记待批：中期累计收益或趋势窗口 |
| fp_low_vol_011 | RET_STD20, RET_STD60 | 登记待批：NEG(RET_STD20) — 低波动选股 |
| fp_downside_vol_012 | DOWNSIDE_RET_STD20, DOWNSIDE_RET_STD60 | 登记待批：NEG(DOWNSIDE_RET_STD20) — 低下行风险选股 |
| fp_amount_liquidity_014 | AMOUNT_MA20, AMOUNT_MA60 | 登记待批：ZSCORE20(AMOUNT_MA20) — 高流动性选股 |
| fp_multi_frequency_trend_019 | TREND20, TREND60, TREND120 | 登记待批：多窗口趋势共振表达 |

### 4.3 约束

- 只做单因子，不做组合
- 不随机扩展、不枚举变异
- 派生因子在特征未审批前跳过，记录跳过原因
- 允许结果为 0 个
- 最多 7 个候选（每个因子 1 个）

### 4.4 预期输出

- 2 个直接可执行的候选（010、018）
- 5 个因特征未审批而跳过的登记
- 执行候选结果的 fast_screen + Phase 2 回测指标

### 4.5 准入条件

仅当 `fp_reversal_short_010` 或 `fp_price_volume_interaction_018` 在样本外训练集（20230103-20241231）上有正的 `rank_ic_mean` 时，才进入阶段 B。其他 5 个因子特征审批后补做。

## 5. 阶段 B：库内有经济含义组合

### 5.1 目标

围绕阶段 A 通过的种子因子，做 5 类具有明确经济含义的配对组合。每一类组合都有独立的经济直觉支撑，不做无含义堆叠。

### 5.2 五类经济含义组合

#### B-1：动量 + 低波动

| 属性 | 内容 |
| ---- | ---- |
| 种子因子 | fp_momentum_mid_009 + fp_low_vol_011 |
| 经济直觉 | 动量提供方向，低波动过滤质量——降低动量策略在反转行情中的回撤。学术文献（如 Asness et al.）也支持动量与低波动的互补性。 |
| 预期因子方向 | 动量为正（买入高动量），低波动为正（买入低波动） |
| 候选数上限 | 1 |

#### B-2：反转 + 量价配合

| 属性 | 内容 |
| ---- | ---- |
| 种子因子 | fp_reversal_short_010 + fp_price_volume_interaction_018 |
| 经济直觉 | 短期超跌只有在成交放量确认时才可能是真正的反转信号，否则更可能是流动性枯竭导致的下跌延续。量价配合因子提供"有量确认"的过滤层。 |
| 预期因子方向 | 反转为负（买入超跌），量价为正（买入有量确认） |
| 候选数上限 | 1 |

#### B-3：趋势 + 流动性

| 属性 | 内容 |
| ---- | ---- |
| 种子因子 | fp_multi_frequency_trend_019 + fp_amount_liquidity_014 |
| 经济直觉 | 趋势策略最怕的是趋势反向时因流动性不足无法及时退出。加入流动性过滤可降低冲击成本和执行滑点。 |
| 预期因子方向 | 趋势为正（买入上行趋势），流动性为正（买入高流动性） |
| 候选数上限 | 1 |

#### B-4：多周期趋势共振

| 属性 | 内容 |
| ---- | ---- |
| 种子因子 | fp_momentum_mid_009 + fp_multi_frequency_trend_019 |
| 经济直觉 | 当中期动量与多频趋势方向一致时，信号可靠性更高。学术文献中多时间尺度趋势叠加已被证实可提升风险调整收益。 |
| 预期因子方向 | 两个动量因子方向均为正，共振买入 |
| 候选数上限 | 1 |

#### B-5：下行波动约束

| 属性 | 内容 |
| ---- | ---- |
| 种子因子 | fp_downside_vol_012 + fp_low_vol_011 |
| 经济直觉 | 低波动因子在极端下跌中可能包含大量"低波动但高下行风险"的标的。下行波动约束可以剔除这类伪低波动资产。 |
| 预期因子方向 | 下行波动为正（买入下行波动低），低波动为正 |
| 候选数上限 | 1 |

### 5.3 约束

- 每对只做 1 个候选表达式
- 不得做 3 因子及以上组合
- 不得做任意堆叠或随机组合
- 允许结果为 0 个
- 最多 5 个候选

### 5.4 准入条件

配对的两个因子中，至少有一个在阶段 A 中通过了快速筛查（rank_ic_mean 在样本外为正）。若两个因子均未通过阶段 A，该配对组合跳过。

## 6. 阶段 C：同源窄派生组合

### 6.1 目标

围绕已批准的 16 个基础特征族，在族内做窄范围派生。派生使用现有算子，不引入库外因子。

### 6.2 五大特征族

#### C-1：收益窗口族

| 属性 | 内容 |
| ---- | ---- |
| 特征 | RET1, RET5, RET20, RET60, RET120 |
| 派生思路 | 不同窗口收益的差分或加权组合（如 SUB(RET20, RET5) 表达中期动量与短期收益差异；DIV(RET60, RET_STD60) 表达收益风险比） |
| 候选数上限 | 2 |

#### C-2：波动率族

| 属性 | 内容 |
| ---- | ---- |
| 特征 | RET_STD20, RET_STD60, DOWNSIDE_RET_STD20, DOWNSIDE_RET_STD60 |
| 派生思路 | 波动率比率（如 DIV(DOWNSIDE_RET_STD20, RET_STD20) 表达下行风险占比）；波动率变化（如 DELTA5(RET_STD20) 表达波动率的近期变化） |
| 候选数上限 | 2 |

#### C-3：趋势族

| 属性 | 内容 |
| ---- | ---- |
| 特征 | TREND20, TREND60, TREND120 |
| 派生思路 | 多窗口趋势差分（如 SUB(TREND20, TREND60) 表达趋势加速/减速）；趋势衰减加权（如 DECAY_LINEAR20(TREND60) 表达平滑趋势） |
| 候选数上限 | 2 |

#### C-4：量价交互族

| 属性 | 内容 |
| ---- | ---- |
| 特征 | VOLUME_WEIGHTED_RET, VOL_RATIO20, RET1, RET5 |
| 派生思路 | 方向性量价配合（如 MUL(VOLUME_WEIGHTED_RET, SIGN(RET5)) 表达有量确认的方向）；量价背离（如 SUB(RET5, VOLUME_WEIGHTED_RET) 表达价格变动与量价加权收益的差异） |
| 候选数上限 | 2 |

#### C-5：流动性容量族

| 属性 | 内容 |
| ---- | ---- |
| 特征 | AMOUNT_MA20, AMOUNT_MA60, VOL_RATIO20 |
| 派生思路 | 流动性变化率（如 SUB(DIV(AMOUNT_MA20, AMOUNT_MA60), 1.0) 的近似表达，用 DIV/SUB 算子模拟）；流动性×趋势过滤 |
| 候选数上限 | 2 |

### 6.3 约束

- 派生必须属于同一特征族
- 只用现有算子（ADD/SUB/MUL/DIV/NEG/ABS/SIGN/DELTA5/DECAY_LINEAR20/ZSCORE20）
- 不引入库外因子
- 不新增外部数据
- 允许结果为 0 个
- 最多 10 个候选

## 7. 整体候选预算

| 阶段 | 最多候选数 | 说明 |
| ---- | -------- | ---- |
| 阶段 A | 7 | 7 个种子因子各 1 个 |
| 阶段 B | 5 | 5 类配对各 1 个 |
| 阶段 C | 10 | 5 族各最多 2 个 |
| **合计** | **22** | 允许结果为 0 个 |

## 8. 审批前的先决条件

### 8.1 必须完成的审批

- [ ] 用户批准第二轮搜索启动
- [ ] 用户批准在 vocabulary 中暴露已实现的 11 个第二批基础特征
- [ ] 用户确认 5 类经济含义组合方向
- [ ] 用户确认 5 大窄派生特征族

### 8.2 执行前置条件

- [ ] 第二轮门禁检查器全部通过
- [ ] 现有 targeted tests 全部通过
- [ ] 基础特征（含 11 个新增）在 vocabulary 中可访问
- [ ] AlphaGPT v2 pipeline 可正常初始化
- [ ] 候选上限确认（总计 ≤ 22）

## 9. 风险提示

1. **样本过小风险**：22 个候选远少于第一轮 94 公式，可能因候选太少而无法发现有效因子。这是设计意图——本轮目标是高精度少量候选，而非高召回率。
2. **派生因子依赖批准**：阶段 A 中 5 个因子依赖新增特征审批。若特征未被批准，阶段 A 实际只有 2 个因子可执行。
3. **方向一致性**：第一轮已发现方向一致性问题（Phase 2 总是做多高因子值）。本轮需在所有因子设计阶段就标注预期方向。
4. **过拟合风险**：阶段 C 的窄派生可能过度拟合已有特征族，需严格依赖现有相关性过滤（0.95 阈值）和分段评估。

## 10. 禁止事项核查

- new_formula_generated: false
- search_started: false
- backtest_run: false
- fast_screen_modified: false
- robustness_modified: false
- pipeline_modified: false
- threshold_modified: false
- rating_rule_modified: false
- correlation_threshold_modified: false
- time_split_modified: false
- new_operator_added: false
- external_data_added: false
- forward_data_accessed: false
- trading_advice_generated: false

## 11. 最终结论

本阶段完成第二轮最小搜索运行草案。三阶段设计已就绪（A: 单因子检查, B: 经济含义组合, C: 同源窄派生），但尚未批准搜索，尚未生成公式，尚未回测，所有因子仍不得用于交易。
