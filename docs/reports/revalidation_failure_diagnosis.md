# AlphaGPT 第一批94公式复验失败原因诊断

## 1. 本次诊断范围

本报告只读取和分析以下文件的已有内容：

- `revalidation_report.md`
- `revalidation_report.json`
- `selection_phase2_results.jsonl`
- `selection_status.jsonl`
- `development_metrics.csv`
- `selection_metrics.csv`
- `run_config.yaml`

不生成新公式，不启动第二批搜索，不修改阈值、评级规则或代码，不访问前向数据，不给出买卖建议。

## 2. 文件核查

| 文件 | 路径 | 是否存在 |
|---|---|---|
| revalidation_report.md | `D:\alphaGPT_runtime\runs\factor_research_v2_revalidation_20260703_215238\revalidation_report.md` | ✅ 存在 (522 字节) |
| revalidation_report.json | `D:\alphaGPT_runtime\runs\factor_research_v2_revalidation_20260703_215238\revalidation_report.json` | ✅ 存在 (62,273 字节) |
| PROJECT_STATUS.md | `D:\alphaGPT_runtime\PROJECT_STATUS.md` | ❌ 不存在 |
| PROJECT_STATUS.md (docs/) | `D:\alphaGPT_runtime\docs\PROJECT_STATUS.md` | ❌ 不存在 |
| 第一批诊断报告 (research_diagnostic_report.md) | `D:\alphaGPT_runtime\runs\factor_research_v2_20260630_220303\research_diagnostic_report.md` | ✅ 存在 (7,934 字节) |
| 第一批诊断报告 (research_diagnostic_report.json) | `D:\alphaGPT_runtime\runs\factor_research_v2_20260630_220303\research_diagnostic_report.json` | ✅ 存在 (74,702 字节) |
| selection_phase2_results.jsonl | 同上 run 目录 | ✅ 存在 (94 条记录) |
| selection_status.jsonl | 同上 run 目录 | ✅ 存在 (94 条记录) |

**PROJECT_STATUS.md 缺失报告**：项目中不存在 `PROJECT_STATUS.md` 文件（根目录和 docs/ 目录均未找到）。由于文件不存在，无法判断其主线状态。本次后续分析完全基于用户提供的交接信息和复验 run 产物，不与任何旧主线冲突。

## 3. 总体结论

复验 run `factor_research_v2_revalidation_20260703_215238` 的 94 个去重公式的最终结果是：

- **development 阶段通过**: 94 / 94
- **selection 阶段通过**: 0 / 94
- **stability 阶段通过**: 0 / 94（因无候选进入此阶段）
- **A 级**: 0
- **B 级**: 0
- **C 级**: 0
- **Rejected**: 94
- **final_shortlist**: 0
- **recommended_factors**: 空数组

**大白话**：94 个公式全部能通过开发期校验，但在筛选期（2023-01-03 至 2024-12-31）的完整回测中全部亏损，没有一个能进入稳定期和稳健性检验。系统没有"坏"，而是诚实地返回了 0 个合格因子。

## 4. selection 失败原因分布

### 4.1 revalidation_report.json 中的字段状态

`revalidation_report.json` 中 `final_ratings` 数组的每条记录包含以下关键字段：

- `rejection_reasons`: 全部为 `["selection_not_passed"]` — **仅有这一个通用原因，无细分字段**
- `selection_rejection_reasons`（来自 `selection_status.jsonl`）: 全部为 `[]`（空数组）— **未记录具体拒绝原因**
- `missing_metrics`: 全部为 `[]`（空数组）— **所有公式指标均未缺失**
- `robustness_status`: 全部为 `"not_run"` — **稳健性未运行（因无候选）**

**结论：revalidation_report.json 不包含 selection 阶段每个公式被拒绝的具体原因分类。系统只记录了总体状态 `selection_not_passed`，没有记录每个公式因哪个具体阈值被淘汰。**

### 4.2 基于 selection_phase2_results.jsonl 的补充分析

虽然 revalidation_report.json 没有细粒度的拒绝原因分解，但 94 条 `selection_phase2_results.jsonl` 记录包含了完整的 Phase 2 回测指标。以下是从这些指标中观察到的客观分布：

#### (1) 总收益 (total_return) — 94/94 均为负值

| 范围 | 公式数 | 占比 |
|---|---|---|
| 正值（> 0） | 0 | 0% |
| -0.3 至 -0.1 | 20 | 21.3% |
| -0.5 至 -0.3 | 50 | 53.2% |
| ≤ -0.5 | 24 | 25.5% |
| **合计** | **94** | **100%** |

全部 94 个公式在 selection 阶段的总收益均为负值，范围为 [-0.636, -0.141]，均值为 -0.406。**这是 selection 全部失败的最直接原因——没有公式能产生正的净收益。**

#### (2) 年化收益 (annualized_return) — 94/94 均为负值

范围 [-0.409, -0.076]，均值 -0.241。

#### (3) 最大回撤 (max_drawdown)

| 范围 | 公式数 | 占比 |
|---|---|---|
| > -0.20（轻度） | 0 | 0% |
| -0.20 至 -0.35（中度） | 1 | 1.1% |
| -0.35 至 -0.50（严重） | 20 | 21.3% |
| ≤ -0.50（极严重） | 73 | 77.7% |
| **合计** | **94** | **100%** |

最大回撤范围 [-0.678, -0.333]，均值 -0.542。

#### (4) Sharpe 比率 — 94/94 均为负值

范围 [-1.567, -0.257]，均值 -0.908。

#### (5) Sortino 比率 — 94/94 均为负值

范围 [-2.309, -0.424]，均值 -1.409。

#### (6) 交易胜率 (trade_win_rate) — 全部低于 50%

| 范围 | 公式数 | 占比 |
|---|---|---|
| ≥ 0.50 | 0 | 0% |
| 0.45 - 0.50 | 25 | 26.6% |
| 0.40 - 0.45 | 62 | 66.0% |
| < 0.40 | 7 | 7.4% |
| **合计** | **94** | **100%** |

范围 [0.389, 0.489]，均值 0.433。

#### (7) 盈亏比 (profit_loss_ratio)

| 范围 | 公式数 | 占比 |
|---|---|---|
| ≥ 2.0 | 3 | 3.2% |
| 1.5 - 2.0 | 15 | 16.0% |
| 1.0 - 1.5 | 56 | 59.6% |
| < 1.0 | 20 | 21.3% |
| **合计** | **94** | **100%** |

范围 [0.745, 2.114]，均值 1.268。虽然平均盈亏比 > 1.0，但胜率过低（平均 43.3%），导致整体回测净收益为负。

### 4.3 关于 selection 拒绝规则的说明

**revalidation_report.json 没有记录 selection 阶段每个公式的详细拒绝规则和阈值触发情况。** 报告中未包含以下字段：

- 净收益是否达标 → 字段不存在，无法统计
- Sortino / Sharpe 是否达标 → 字段不存在，无法统计
- 最大回撤是否达标 → 字段不存在，无法统计
- 交易胜率是否达标 → 字段不存在，无法统计
- 盈亏比是否达标 → 字段不存在，无法统计
- 窗口级结果是否稳定 → 字段不存在，无法统计
- 指标是否缺失 → 全部为空（`missing_metrics: []`），无指标缺失
- robustness 是否运行 → 全部为 `not_run`（因 selection 无候选）

**补充说明**：尽管报告中缺乏细粒度拒绝原因，但从指标数据可一致观察到：所有 94 个公式在 selection 阶段的 Phase 2 回测中 total_return 均为负值，这是所有公式被拒绝的最直接的共通原因。

## 5. 关键指标分布

以下指标来自 `selection_phase2_results.jsonl`（94 条记录全部可用）：

| 指标 | 可用数 | 最小值 | 最大值 | 均值 | 中位数 | 正值个数 |
|---|---|---|---|---|---|---|
| total_return | 94/94 | -0.635741 | -0.140831 | -0.405634 | -0.403499 | 0 |
| annualized_return | 94/94 | -0.408924 | -0.075988 | -0.241141 | -0.235866 | 0 |
| max_drawdown | 94/94 | -0.678397 | -0.333167 | -0.541996 | -0.559539 | 0 |
| sharpe | 94/94 | -1.566866 | -0.256609 | -0.907867 | -0.905233 | 0 |
| sortino | 94/94 | -2.308754 | -0.423962 | -1.408599 | -1.432044 | 0 |
| calmar | 94/94 | -0.615501 | -0.198116 | -0.434683 | -0.433097 | 0 |
| annualized_volatility | 94/94 | 0.170010 | 0.345128 | 0.267428 | 0.273346 | 94 |
| trade_win_rate | 94/94 | 0.388575 | 0.488922 | 0.433108 | 0.432620 | 94 |
| profit_loss_ratio | 94/94 | 0.744835 | 2.114249 | 1.268164 | 1.262683 | 94 |
| 窗口级净收益 (window_level) | 140,929 行 | — | — | 需逐窗口分析 | — | — |

注意：`window_level_results_persisted` 为 `true`，窗口级结果已保存（`selection_window_results.csv`，140,929 行），但本诊断报告未逐窗口展开分析。

**报告未提供的字段**：

- `trade_win_rate` 是否被用作淘汰阈值 → 报告未提供该判断规则
- `profit_loss_ratio` 是否被用作淘汰阈值 → 报告未提供该判断规则
- 窗口级稳定性的具体评判标准 → 报告未提供
- 是否存在复合淘汰规则 → 报告未提供

## 6. 两个旧 B 级因子的复验结果

### 因子 1: `DECAY_LINEAR20(MUL(RET5,RET5))`

| 项目 | 值 |
|---|---|
| 旧评级 | B（来自第一批正式研究） |
| 新评级 | Rejected |
| 评级变化 | 是（grade_changed: true） |
| selection 阶段年化收益 | -0.1591 |
| selection 阶段总收益 | -0.2830 |
| selection 阶段最大回撤 | -0.5252 |
| selection 阶段 Sharpe | -0.5043 |
| selection 阶段 Sortino | -0.8643 |
| selection 阶段交易胜率 | 0.4681（46.8%） |
| selection 阶段盈亏比 | 1.6018 |
| 拒绝原因 | selection_not_passed |
| 稳健性状态 | not_run |

### 因子 2: `DECAY_LINEAR20(MUL(RET1,TREND60))`

| 项目 | 值 |
|---|---|
| 旧评级 | B（来自第一批正式研究） |
| 新评级 | Rejected |
| 评级变化 | 是（grade_changed: true） |
| selection 阶段年化收益 | -0.1679 |
| selection 阶段总收益 | -0.2975 |
| selection 阶段最大回撤 | -0.4342 |
| selection 阶段 Sharpe | -0.5819 |
| selection 阶段 Sortino | -0.9182 |
| selection 阶段交易胜率 | 0.4597（46.0%） |
| selection 阶段盈亏比 | 1.5788 |
| 拒绝原因 | selection_not_passed |
| 稳健性状态 | not_run |

**说明**：两个旧 B 级因子在原来的完整区间（2019-2026）回测中曾取得微弱正收益（旧研究中年化约 1%-2%）。但在独立 selection 时段（2023-01-03 至 2024-12-31）的复验中，两者均录得显著负收益，被正确降级为 Rejected。

## 7. 对旧公式空间的初步判断

基于已有证据：

1. **旧公式空间在本轮 selection 阶段没有产生合格因子。** 94 个去重公式在 selection 时段（2023-01 至 2024-12）的所有 Phase 2 回测均为负收益。

2. **这不是"系统坏了"或"标准太高"，而是旧公式空间在独立的样本外时段（相对开发期而言）确实表现不佳。** 所有指标方向一致地指向负值。

3. **是否需要扩展特征或公式空间，需要用户另行批准。** 本诊断报告不给出"应该扩大搜索"或"应该降低标准"的建议。

4. **无法判断旧公式空间永久无效。** 本报告仅反映特定公式空间、特定时间段的研究结果。

5. **不推荐进入低频模拟或人工下单观察。** 本轮没有任何因子达到前向观察标准。

## 8. 下一步状态

```
new_formula_generated: false
new_factor_search_started: false
forward_data_accessed: false
recommended_factors: []
next_stage_started: false
```

---

*诊断日期：2026-07-04*
*诊断范围：仅基于已有复验产物，未运行新研究、新公式或新测试*
