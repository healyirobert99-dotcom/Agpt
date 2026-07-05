# AlphaGPT 第一批94公式复验后的下一步决策备忘录

## 1. 本次判断依据

本备忘录基于以下文件的已有内容编写：

| 文件 | 存在性 |
|---|---|
| `D:\alphaGPT_runtime\runs\factor_research_v2_revalidation_20260703_215238\revalidation_report.md` | ✅ 已读取 |
| `D:\alphaGPT_runtime\runs\factor_research_v2_revalidation_20260703_215238\revalidation_report.json` | ✅ 已读取 |
| `D:\alphaGPT_runtime\runs\factor_research_v2_revalidation_20260703_215238\revalidation_failure_diagnosis.md` | ✅ 已读取（上一步生成） |
| `D:\alphaGPT_runtime\PROJECT_STATUS.md` | ❌ 不存在 |

**不依赖代码分析，不运行新回测，不启动新搜索。**

## 2. 当前事实确认

| 项目 | 确认值 |
|---|---|
| 94 个公式已完成独立分期复验 | ✅ 是 |
| development 阶段通过 | 94 |
| selection 阶段通过 | 0 |
| stability 阶段通过 | 0（无候选进入） |
| A 级 | 0 |
| B 级 | 0 |
| C 级 | 0 |
| Rejected | 94 |
| final_shortlist | 0 |
| recommended_factors | 空数组 `[]` |
| 第二批搜索已启动 | ❌ 否 |
| forward data 已访问 | ❌ 否 |
| 阈值已修改 | ❌ 否 |
| correlation threshold 已修改 | ❌ 否 |
| B-v1.0 已修改 | ❌ 否 |

## 3. selection 全灭的主要原因

### 3.1 revalidation_report.json 中记录的拒绝原因

`revalidation_report.json` 的 `final_ratings` 数组共 94 条记录，每条记录的：

- `rejection_reasons`: `["selection_not_passed"]`（**全部 94 个公式唯一通用原因**）
- `selection_rejection_reasons`（来自 `selection_status.jsonl`）: **全部为空数组 `[]`**
- `grade_reasons`: `["selection_not_passed"]`（全部 94 个通用）
- `missing_metrics`: `[]`（全部为空，无指标缺失）

**现有报告无法支持更细分的拒绝原因分类。** revalidation_report.json 不记录每个公式在 selection 阶段因哪个具体阈值被淘汰（例如净收益不达标、Sortino 不达标、回撤过大等），仅记录总体状态 `selection_not_passed`。

### 3.2 从 selection_phase2_results.jsonl 可以确认的事实

虽然细粒度拒绝原因缺失，但 Phase 2 回测指标提供了客观数据：

| 指标 | 94 个公式的分布 |
|---|---|
| **total_return** | 全部为负值（范围 -0.636 至 -0.141，均值 -0.406）。**没有一个公式在 selection 时段产生正收益。** |
| **annualized_return** | 全部为负值（范围 -0.409 至 -0.076，均值 -0.241） |
| **sharpe** | 全部为负值（范围 -1.567 至 -0.257，均值 -0.908） |
| **sortino** | 全部为负值（范围 -2.309 至 -0.424，均值 -1.409） |
| **max_drawdown** | 全部为负值（范围 -0.678 至 -0.333，均值 -0.542） |
| **trade_win_rate** | 全部低于 0.50（范围 0.389—0.489，均值 0.433） |
| **profit_loss_ratio** | 范围 0.745—2.114，均值 1.268。但胜率不足导致整体亏损 |
| **calmar** | 全部为负值（范围 -0.616 至 -0.198，均值 -0.435） |

### 3.3 快速筛选（fast screen）在 selection 阶段的结果

`selection_metrics.csv` 记录了 selection 阶段的快速筛选指标：

| 项目 | 值 |
|---|---|
| fast_screen_status | 全部 94 个 "passed" |
| rank_ic_mean | 12 个正值，82 个负值（范围 -0.080 至 0.063） |
| positive_period_ratio | 范围 0.236—0.760，均值 0.367 |

94 个公式全部通过了 selection 时段的快速筛选（rank_ic_mean 和 coverage 等），但在后续 Phase 2 完整回测中全部失败。

### 3.4 根本原因的核心表述

**现有报告无法将 94 个公式的 rejection 分解到具体阈值层面**（如"因净收益不达标 N 个"、"因胜率不达标 M 个"、"因回撤过大 K 个"等），因为报告输出仅记录 `selection_not_passed` 一个通用状态。

但从 Phase 2 回测指标可以一致观察到：全部 94 个公式在 selection 时段（2023-01-03 至 2024-12-31）的完整回测中，**所有收益类指标均为负值**——这是所有公式被拒绝的最直接、最广泛的共通原因。

## 4. 两个旧 B 级因子的复验结论

### 因子 1: `DECAY_LINEAR20(MUL(RET5,RET5))`

| 项目 | 值 |
|---|---|
| 旧评级 | B（来自第一批正式研究） |
| 新评级 | Rejected |
| grade_changed | true |
| selection 年化收益 | -0.1591 |
| selection 总收益 | -0.2830 |
| selection 最大回撤 | -0.5252 |
| selection Sharpe | -0.5043 |
| selection Sortino | -0.8643 |
| selection 交易胜率 | 0.4681 |
| selection 盈亏比 | 1.6018 |
| selection_status | rejected |
| rejection_reasons | ["selection_not_passed"] |
| robustness_status | not_run |
| 是否可进入前向观察 | **否** |

### 因子 2: `DECAY_LINEAR20(MUL(RET1,TREND60))`

| 项目 | 值 |
|---|---|
| 旧评级 | B（来自第一批正式研究） |
| 新评级 | Rejected |
| grade_changed | true |
| selection 年化收益 | -0.1679 |
| selection 总收益 | -0.2975 |
| selection 最大回撤 | -0.4342 |
| selection Sharpe | -0.5819 |
| selection Sortino | -0.9182 |
| selection 交易胜率 | 0.4597 |
| selection 盈亏比 | 1.5788 |
| selection_status | rejected |
| rejection_reasons | ["selection_not_passed"] |
| robustness_status | not_run |
| 是否可进入前向观察 | **否** |

**说明**：两个旧 B 级因子在原完整区间（2019—2026）的全区间回测中曾取得微弱正收益（约 1%-2% 年化），但在独立 selection 时段（2023-01 至 2024-12）的复验中均录得显著负收益，被正确降级为 Rejected。无法进入前向观察。

## 5. 是否应该直接继续跑更多公式

### 5.1 已验证事实

- 94 个去重公式在独立 selection 时段（2023-01 至 2024-12）的 Phase 2 完整回测中没有一个产生正净收益。
- 94 个公式在 selection 时段的快速筛选（fast screen）全部通过，但所有后续完整回测均失败。
- `previous_grade` 分布：2 个旧 B 级，48 个原 Rejected，44 个无前序评级。**两个 B 级已被降级，其余所有被评估过的公式（48 个原本就是 Rejected）也未达到 selection 标准。**
- 没有任何因子通过 stability 评估或 robustness 验证（因无候选进入这些阶段）。

### 5.2 基于证据的推断

以下判断为基于已有事实的合理推断，并非绝对结论，且不排除未来在改变条件后产生不同结果：

1. **旧公式空间在本轮 selection 阶段没有产生任何合格因子。** 94 个来自第一批研究的去重公式在独立的样本外时段（2023-01 至 2024-12）中均未通过完整回测检验。

2. **selection 阶段的 fast screen 先于 Phase 2 回测运行，94 个全部通过 fast screen，但全部在 Phase 2 回测中失败。** 这意味着快速筛选（IC 方向、覆盖度等表层指标）无法识别这批公式在样本外时段的实际回测表现。

3. **在完全不改变基础特征、算子集合、公式生成空间和筛选评价口径的情况下，仅机械扩大搜索数量（即用相同空间生成更多公式）可能不会自动解决这个问题。** 现有 94 个已覆盖了第一批操作法、趋势类、动量类、成交量类等常见公式模式，上述所有模式在 selection 时段一致表现不佳。单纯增加公式数量但不改变空间本身，可能只是增加了搜索量，不等于找到了在 unseen 时段能有正收益的新模式。

4. **现有证据不支持判定"旧公式空间永久无效"。** 因子研究本身存在统计不确定性，不同市场阶段下公式表现可能不同。本判断仅基于当前历史数据。

### 5.3 需要用户批准的事项

如果要进入第二批搜索，必须由用户明确批准以下事项（逐项确认，批准其中任何一项不默认为批准其他项）：

1. **是否继续使用原有基础特征空间**（即 RET1、RET5、TREND60、VOLUME_WEIGHTED_RET、VOL_RATIO20、ABS 等现有特征和算子）。
2. **是否扩展基础特征**（引入新数据源、新因子表达，如估值类、质量类、情绪类特征等）。
3. **是否扩展公式生成空间**（增加新算子、新函数、新生成策略，如非线性组合、条件筛选等）。
4. **是否保持现有筛选和评级标准**（development/selection/stability 三阶段、fast screen、Phase 2 回测、required robustness 等现有标准）。
5. **是否允许生成新公式**（使用公式生成器产生超出原 94 个的新公式）。
6. **是否允许启动第二批搜索**（完整跑通生成 → 快速筛选 → Phase 2 回测 → 分段复验 → 评级链路）。
7. **是否允许修改现有配置中的任何参数**（如窗口期、回测参数、筛选阈值等）。

## 6. 建议的下一步状态

基于当前复验结果，本备忘录给出以下状态建议：

- ⏸️ **当前不直接启动第二批搜索。**
- ⏸️ **当前不生成新公式。**
- ⏸️ **当前不修改筛选阈值或评级标准。**
- ⏸️ **当前不降低任何通过标准。**
- ⏸️ **当前不扩展特征或算子。**
- ⏸️ **当前不改变研究口径。**
- ⏸️ **当前不访问 forward data。**
- ✅ **当前先等待用户基于本备忘录决定是否、何时以及以何种方式批准第二批搜索。**
- ✅ **保留现有 94 个公式的复验结果和诊断报告作为基准参考。**

## 7. 禁止事项核查

| 事项 | 当前状态 |
|---|---|
| `new_formula_generated` | false |
| `new_factor_search_started` | false |
| `screening_thresholds_changed` | false |
| `correlation_threshold_changed` | false |
| `b_v1_modified` | false |
| `forward_data_accessed` | false |
| `next_stage_started` | false |
| 代码已修改 | ❌ 未修改 |
| 配置已修改 | ❌ 未修改 |
| 评级规则已修改 | ❌ 未修改 |
| 券商已接入 | ❌ 未接入 |
| 自动交易已启动 | ❌ 未启动 |

## 8. 最终结论

**大白话总结：**

第一批 94 个公式已经按正确规则逐一复验。结果是——development 阶段 94 个全部通过，但 selection 阶段 94 个全部失败。没有一个公式在筛选期（2023-2024 年）的完整回测里能赚钱。所以 stability、robustness 都测不了，A/B/C 都是 0，final_shortlist 是 0，recommended_factors 是空数组，前向观察推荐是 0。

两个旧 B 级因子在独立筛选期里也是亏损的，已被正确降级。它们不能进入前向观察。

**当前不应为了得到 A/B 结果而放宽标准。** "没有合格因子"是现有标准下诚实的输出。如果放宽标准让某些公式勉强通过，得到的结果不会更有说服力。

**是否进入第二批搜索，需要你明确批准。** 你可以选择的路径包括：

1. **不批准**——维持现状，项目停留在第一批结果上。
2. **批准在同空间下继续搜索**——用相同特征和算子生成更多公式，但需意识到这个空间在 2023-2024 年整体表现不佳。
3. **批准扩展空间**——引入新特征或新算子，再启动搜索。
4. **批准调整标准**——要求调整筛选或评级规则后重新评估（注意：这需要明确说明理由和预期效果）。

无论你选择哪条路径，都需要指明批准范围。当前不默认推进任何下一步。

---

*生成日期：2026-07-04*
*基于：factor_research_v2_revalidation_20260703_215238 复验结果*
*未运行新回测、未生成新公式、未修改代码和配置*
