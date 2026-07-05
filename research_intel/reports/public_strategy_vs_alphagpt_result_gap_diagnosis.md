# 公开策略先验与 AlphaGPT 阶段 A/B 结果差异诊断

## 1. 结论摘要

- Firecrawl 已抓取公开量化社区（Wikipedia Smart Beta / Qlib / Stockformer / arXiv 论文）的因子和策略先验。资料库包含 20 个因子先验 + 20 条操作策略参考。
- **社区明星策略不等于单因子裸测有效。** 公开策略的回报通常来自因子选择、组合结构、股票池过滤、调仓频率、风险控制等多层次叠加，而 AlphaGPT 阶段 A/B 做的是最严格的单因子裸测。
- **当前最有效的历史线索是低波动（NEG(RET_STD20)，评级 B）。** 这是唯一一个在 AlphaGPT 严格口径下通过全部 gate 的因子。
- **后续研究重点应从"继续堆因子"转向"还原公开策略的操作层结构"。**

## 2. 阶段 A/B 结果回顾

| 因子 | IC | 收益 | Sharpe | 评级 | 状态 |
|------|-----|------|--------|------|------|
| fp_momentum_mid_009 — ZSCORE20(RET60) | -0.1206 | — | — | Rejected | 覆盖率 0.281 < 0.30 |
| fp_reversal_short_010 — NEG(RET5) | +0.0364 | -20.28% | -1.313 | Rejected | 回测负收益 |
| **fp_low_vol_011 — NEG(RET_STD20)** | **+0.0247** | **+3.68%** | **0.771** | **B** | ✅ **主候选** |
| fp_downside_vol_012 — NEG(DOWNSIDE_RET_STD20) | -0.0045 | +5.73% | 1.173 | C | ✅ 辅助 |
| fp_amount_liquidity_014 — ZSCORE20(AMOUNT_MA20) | -0.0579 | -21.80% | -1.964 | Rejected | |
| fp_price_volume_interaction_018 — MUL(RET5,VOLUME_WEIGHTED_RET) | -0.0175 | -17.09% | -1.223 | Rejected | |
| fp_multi_frequency_trend_019 — ADD(TREND20,TREND60) | -0.0572 | -11.39% | -1.440 | Rejected | |

阶段 B 等权组合：IC +0.0149（↓40% vs 低波动单因子），评级 C，未优于阶段 A。

## 3. 公开策略与 AlphaGPT 验证口径差异

### 3.1 Firecrawl 抓取的公开策略操作层特征

Firecrawl 抓取的策略库包含以下操作层条件，而 AlphaGPT 阶段 A 裸测**均未使用**：

| 操作层维度 | 公开策略常见做法 | AlphaGPT 阶段 A/B 做法 | 差异影响 |
| ---------- | -------------- | --------------------- | -------- |
| 股票池过滤 | ^ 排除 ST、停牌、退市、极低流动性 | Phase 2 回测已含 tradability | 影响较小 |
| 市值过滤 | ^ 常见中大盘偏好 | 无 | 策略偏好可能排除大量小盘噪声 |
| 行业过滤/行业中性 | ★ 指数增强和风险控制常见 | 无 | 可能大幅改变因子排序和回测表现 |
| 流动性过滤 | ★★ 几乎所有策略都要求 | Phase 2 含成交过滤但不做排名前过滤 | **核心差异** |
| 排名方式 | topN、分位、行业标准化 | Phase 2 硬编码 top_n=20 | 接近 |
| 调仓频率 | weekly～monthly，部分 daily | 固定 5 日 | 接近 |
| 持有周期 | 数周到数月 | 随调仓（约 1 周） | 短期策略可能摩擦更大 |
| 止盈止损 | 部分策略含移动止损 | 无 | 可能平滑回撤 |
| 择时条件 | 市场状态过滤、仓位控制 | 无 | 系统性回撤期可能表现差 |
| 多因子权重 | 等权、风险平价、学习权重 | 无（单因子/简单二元组合） | **核心差异** |
| 风险控制 | 行业暴露、单票权重、beta、波动 | 只有 topN 等权 | **核心差异** |
| 交易成本 | 显式计入，部分策略 10-30 bps | 20 bps（单向） | 接近 |
| long-only/long-short | 多数 long-only | long-only | 接近 |
| 财务数据依赖 | ^ 质量、价值、成长类需要 | 阶段 A 仅用日线价量 | 阶段 A 排除全部财务因子 |

> ★ 表示出现频率高  
> ★★ 表示几乎所有公开策略都包含  
> ^ 表示公开策略常用但 AlphaGPT 已部分覆盖

### 3.2 关键差异总结

公开策略的收益来源可分为三层：

1. **因子层**（Alpha）：单因子的预测能力。AlphaGPT 阶段 A 裸测的就是这层。
2. **过滤层**（Gate）：流动性、市值、ST、行业中性、可交易性。AlphaGPT Phase 2 回测已含部分但不等同于策略级别的全面过滤。
3. **组合层**（Portfolio）：多因子权重分配、风险控制、仓位管理、止盈止损。AlphaGPT 阶段 A/B 未涉及。

**AlphaGPT 阶段 A 只测了第一层，而公开策略的收益来自三层协同。**

## 4. 7 个种子因子逐项诊断

### 4.1 fp_momentum_mid_009 — 中期价格动量

```
public_strategy_context: 动量是 Smart Beta + Qlib + Stockformer 的核心类别之一。
  公开策略中动量通常与流动性过滤、行业中性、波动控制搭配使用，
  且以 3-12 个月窗口为主，排除最近 1 个月（剔除反转效应）。
alphaGPT_current_expression: ZSCORE20(RET60)，仅用 60 日收益做标准化。
  简化为单一窗口收益，丢失了动量策略中"排除短期反转"的关键设计。
stage_a_result: Rejected（覆盖率 0.281 < 0.30）
possible_missing_strategy_layer: 
  - 动量策略通常需要多窗口确认（3/6/12 月），而非单窗口
  - 排除最近 1 个月反转窗口是标准做法
  - 公开策略中动量常与流动性+低波动搭配，不是裸因子
likely_reason_for_gap: RET60 需要 60 个有效日，在小股票/新股上 warm-up 不足导致覆盖率低；
  且单一窗口不足以表达动量因子的"多时间维度确认"逻辑
should_continue_as_factor: false
should_continue_as_strategy_structure: true（作为操作层的选择方向之一）
```

### 4.2 fp_reversal_short_010 — 短期反转

```
public_strategy_context: 反转策略在公开资料中普遍包含严格的可成交控制。
  Qlib 论文和社区实践强调：反转策略的纯因子收益通常会被交易成本侵蚀。
alphaGPT_current_expression: NEG(RET5)，取 5 日收益的负值。
  最简洁的反转表达。
stage_a_result: Rejected（IC +0.0364 为正，但回测 -20.28%）
possible_missing_strategy_layer: 
  - 反转策略需要"跌停不可买"的强约束（AlphaGPT 已有但可能不够）
  - 公开策略中反转常与量价配合信号连用（超跌+放量才入场），不是无条件反转
  - 持有周期是决定性参数：持有过短成本吞噬，过长反转失效
likely_reason_for_gap: IC 为正说明因子方向对（超跌后反弹），但 Phase 2 回测负收益说明：
  前向收益被成本、流动性不足、或样本外反转失败吞噬。
  反转因子的收益精细程度对成本和可成交条件极度敏感
should_continue_as_factor: false
should_continue_as_strategy_structure: true（但成本极高，不适合作为首选）
```

### 4.3 fp_low_vol_011 — 低波动

```
public_strategy_context: 低波动是 Smart Beta 的经典类别。
  Stockformer 量价模型中也包含波动率维度。
  公开策略中低波动常作为防御/核心因子，而非短期 alpha。
alphaGPT_current_expression: NEG(RET_STD20)
stage_a_result: B（IC +0.0247，收益 +3.68%，Sharpe 0.771）
possible_missing_strategy_layer: 
  - 公开策略中低波动常与行业中性搭配（避免集中于公用事业）
  - 低波动策略通常更低频（monthly），AlphaGPT 的 5 日调仓可能换手偏高
  - 可补充流动性过滤剔除伪低波动
likely_reason_for_gap: 无 gap——这是唯一通过全部 gate 的因子。
  低波动的经济逻辑在这个时间窗口内成立，且对成本和换手相对不敏感
should_continue_as_factor: true
should_continue_as_strategy_structure: true（作为策略核心因子）
```

### 4.4 fp_downside_vol_012 — 下行波动

```
public_strategy_context: 来自论文"市场中性多因子策略"。
  论文强调下行波动在防御角色中的价值，但通常不是独立的收益因子。
alphaGPT_current_expression: NEG(DOWNSIDE_RET_STD20)
stage_a_result: C（IC -0.0045 极弱，但收益 +5.73% 和 Sharpe 1.173 均超低波动）
possible_missing_strategy_layer:
  - 论文强调 risk-control agent 和 回撤控制，不是裸因子选股
  - 下行波动更适合作为"风险覆盖层"（降低仓位/过滤高风险标的），
    而非独立的选股排序信号
likely_reason_for_gap: IC 几乎为零，说明下行波动的截面排序能力弱。
  正收益可能来自防御属性（低风险资产在下跌市中更抗跌），
  而非真正的 alpha 排序能力
should_continue_as_factor: false（不适合作为独立因子）
should_continue_as_strategy_structure: true（作为操作层的风险覆盖层）
```

### 4.5 fp_amount_liquidity_014 — 成交额流动性

```
public_strategy_context: Stockformer 和 Qlib 都包含成交量/成交额作为关键量价信息。
  但公开资料通常将成交额用于流动性过滤和仓位限制，而非直接作为收益因子。
alphaGPT_current_expression: ZSCORE20(AMOUNT_MA20)
stage_a_result: Rejected（IC -0.0579，收益 -21.80%）
possible_missing_strategy_layer:
  - 成交额的方向性就是错的：公开策略"过滤低流动性"，不是"做多高流动性"
  - 高成交额可能伴随高位放量、趋势末端，方向不稳定
  - 在操作层中应是 gate（最低成交额门槛），不是 signal
likely_reason_for_gap: 将过滤条件当成了排序因子。ZSCORE20(AMOUNT_MA20)
  做多高成交额股票在这个时间段恰好是负 alpha
should_continue_as_factor: false
should_continue_as_strategy_structure: true（作为流动性 gate，不是因子）
```

### 4.6 fp_price_volume_interaction_018 — 量价配合

```
public_strategy_context: Stockformer 明确强调 price-volume factors。
  但公开文献中的用法是"成交确认趋势"或"量价背离预警"，而非简单的乘积累加。
alphaGPT_current_expression: MUL(RET5, VOLUME_WEIGHTED_RET)
stage_a_result: Rejected（IC -0.0175，收益 -17.09%）
possible_missing_strategy_layer:
  - 量价配合信号是条件性的：趋势行情中价量同向有效，震荡市中噪声
  - 公开策略中量价配合常与市场状态过滤一起使用
  - MUL 操作可能引入极端值和不稳定性
likely_reason_for_gap: 简单的乘法组合在噪音市中产生了反向信号。
  量价配合的效力高度依赖市场状态，裸用单因子无法捕获这种条件性
should_continue_as_factor: false
should_continue_as_strategy_structure: true（作为条件覆盖层）
```

### 4.7 fp_multi_frequency_trend_019 — 多频趋势

```
public_strategy_context: Stockformer 提出多频分解。但论文中是用 Transformer
  学习多尺度特征，而非简单的多窗口加法。
alphaGPT_current_expression: ADD(TREND20, TREND60)
stage_a_result: Rejected（IC -0.0572，收益 -11.39%）
possible_missing_strategy_layer:
  - 多频趋势的"频率分离"是核心，不是窗口加总
  - 不同频率可能方向相反（短多长空），简单加法消除了这种信息
  - Stockformer 中的多频表示是通过注意力机制学习的，不是手工设计的简单组合
likely_reason_for_gap: ADD 操作将有可能方向相反的信号简单加总，
  消除了最有价值的方向分歧信息。这与论文中的多频分解理念有本质差异
should_continue_as_factor: false
should_continue_as_strategy_structure: false（表达方式与论文理念差距过大）
```

## 5. 为什么明星策略拆成单因子后会失效

### 5.1 策略收益来自组合结构，不是单因子

公开策略的回报是"因子选择 × 过滤 × 权重 × 调仓 × 风控"的乘积。每一层都可能贡献正收益。拆成单因子后，过滤层、组合层、风控层的贡献全部消失。

以动量策略为例：
- 单因子裸测：IC 不显著 → Rejected
- 加上流动性过滤：排除无法成交的小票 → IC 可能改善
- 加上行业中性：消除行业集中偏误 → 风险调整后收益提升
- 加上波动控制：降低极端收益 → Sharpe 改善

**每一层都可能在单因子裸测中表现为失败。**

### 5.2 单因子表达过度简化

AlphaGPT 的候选公式受限于 8 tokens / 深度 2。公开策略中的许多经济逻辑无法在如此短的表达式中体现：
- "动量排除最近 1 个月" 需要 SUB + 条件逻辑
- "量价确认" 需要市场状态判断
- "流动性过滤" 是 gate 而非 formula

### 5.3 社区回测口径不同

公开社区的回测通常：
- 使用更长的历史（5-10 年 vs AlphaGPT 的 6 个月）
- 股票池更大（全 A 股 vs CSI800）
- 成本假设更宽松（0-10 bps vs 20 bps）
- 不做分段样本外验证（AlphaGPT 提供 development → selection → stability 三阶段严格验证）

### 5.4 AlphaGPT 口径更严格

AlphaGPT 的要求：
- 三段独立时间段严格验证
- 成本 20 bps（单向）
- T+1 成交
- 涨跌停不可交易
- required metric 缺失不得评为 A/B
- robustness 未运行不得评为 A/B

**在这些严格约束下，只有最稳健的因子（低波动）才能通过。**

## 6. 当前因子：为什么低波动能留下

`NEG(RET_STD20)` 通过所有 gate 的原因：

1. **经济逻辑稳健**：低波动异象（low-vol anomaly）是全球性、跨资产、跨时间段的实证现象，有深厚的学术支撑。
2. **对短期噪声不敏感**：波动率是二阶矩，比一阶矩（收益）更稳定。RET_STD20 的 20 日窗口在 6 个月样本中 warm-up 充分。
3. **方向明确且单向**：低波动因子不存在"方向反转"问题（如趋势和反转的冲突）。更低波动 → 更优，方向清晰。
4. **成本敏感度低**：波动率变化慢，换手率 14.9（vs 反转等短期因子可能高达 30+），交易成本冲击小。
5. **样本外稳定性好**：在 selection 和 stability 阶段没有出现方向性反转。

## 7. 下一步建议

- ✅ 保留 NEG(RET_STD20) 为历史主候选（评级 B）
- ✅ 保留 NEG(DOWNSIDE_RET_STD20) 为辅助观察（评级 C）
- ✅ 暂停阶段 C
- ✅ 做操作层结构映射草案：
  - 将公开策略中的股票池过滤、流动性 gate、调仓频率、行业中性、风险控制等操作层条件逐一登记
  - 评估 AlphaGPT 当前引擎对每层的支持程度
  - 识别最小可实施的"操作层验证实验"
- ❌ 不扩大随机搜索
- ❌ 不交易
- ❌ 不自动下单

## 8. 禁止事项核查

- new_formula_generated: false
- new_factor_search_started: false
- new_backtest_run: false
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

## 9. 最终结论

本阶段完成公开策略先验与 AlphaGPT 阶段 A/B 结果差异诊断。当前不扩大搜索，不进入阶段 C，不交易。
