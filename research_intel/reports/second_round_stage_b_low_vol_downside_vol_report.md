# AlphaGPT 第二轮阶段 B：低波动 + 下行波动极窄组合报告

## 1. 运行信息

| 项目 | 值 |
| ---- | --- |
| run_id | factor_research_v2_20260705_151421 |
| stage_a_run_id | factor_research_v2_20260705_145716 |
| stage_a_run_commit | 2ea176cf6d9a826099679cda971a01bb0d57bfec |
| stage_a_report_commit | f5296209300799f3805e3991a7b2cbc80669a784 |
| current_head_commit | f5296209300799f3805e3991a7b2cbc80669a784 |
| 运行时间 | 74.9 秒 |
| 数据库 | stock-data/ashare_research.sqlite3 |
| 固定候选数量 | 2 |
| 是否只使用 fp_low_vol_011 + fp_downside_vol_012 | ✅ |
| 是否启动阶段 C | 否 |
| 是否使用库外因子 | 否 |
| 是否新增特征或算子 | 否 |
| 是否修改筛选/评级/回测逻辑 | 否 |
| 是否访问 forward data | 否 |

## 2. Commit 口径说明

阶段 A 运行时 HEAD 为 2ea176c，报告在 f529620 提交。两者代码完全一致（仅新增报告文件），无代码差异，可追溯。

## 3. 阶段 B 候选结果

| # | 候选 ID | 公式 | fast_screen | IC | 相关性 | 回测收益 | Sharpe | 评级 | 状态 |
|---|---------|------|-------------|-----|-------|---------|--------|------|------|
| B1 | 等权组合 | ADD(NEG(RET_STD20),NEG(DOWNSIDE_RET_STD20)) | ✅ | +0.0149 | kept | +3.90% | 0.822 | **C** | ✅ shortlisted |
| B2 | 交互组合 | MUL(NEG(RET_STD20),NEG(DOWNSIDE_RET_STD20)) | ✅ | -0.0112 | deduped (r=-0.997) | — | — | — | ❌ 相关性剔除 |

B2 与 B1 高度相关（r=-0.997），被相关性去重剔除。仅 B1 进入 Phase 2 回测。

## 4. 阶段统计

| 阶段 | 输入 | 通过 |
| ---- | ---- | ---- |
| fast_screen | 2 | 2 |
| 相关性去重 | 2 | 1 |
| Phase 2 回测 | 1 | 1 |
| 稳健性 | 1 | 1 |

## 5. 评级分布

| 评级 | 数量 | 因子 |
| ---- | ---- | ---- |
| A | 0 | — |
| B | 0 | — |
| C | 1 | ADD(NEG(RET_STD20),NEG(DOWNSIDE_RET_STD20)) |
| Rejected | 1 | MUL(…)（相关性剔除） |

**final_shortlist_count: 1**

## 6. 与阶段 A 对比

| 指标 | NEG(RET_STD20) 阶段 A | NEG(DOWNSIDE_RET_STD20) 阶段 A | ADD(…) 阶段 B |
| ---- | ---------------------- | ------------------------------ | ------------- |
| rank_ic_mean | **+0.0247** | -0.0045 | +0.0149 |
| 回测总收益 | +3.68% | **+5.73%** | +3.90% |
| Sharpe | 0.771 | **1.173** | 0.822 |
| 最大回撤 | -5.01% | -7.29% | **-5.54%** |
| 评级 | **B** | C | C |

### 对比结论

**stage_b_improved_over_stage_a: false**

- B1 的 IC（+0.0149）低于低波动单因子（+0.0247），约减弱 40%
- B1 的回测收益（+3.90%）仅比低波动单因子（+3.68%）高 0.22%，几乎无增量
- B1 的 Sharpe（0.822）介于两者之间，未超越下行波动单因子（1.173）
- B1 的评级为 C，低于低波动单因子 B 级的水平
- 等权组合实际上削弱了低波动因子的核心优势（IC），下行波动因子的加入并未提供实质性增量

## 7. recommended_factors

仅 ADD(NEG(RET_STD20),NEG(DOWNSIDE_RET_STD20)) 进入 shortlist，评级 C。

## 8. 阶段 C 建议

不建议继续阶段 C。理由：
- 阶段 B 组合未优于阶段 A 最佳单因子
- 波动率族的派生组合空间已通过 ADD/MUL 覆盖，未产生新信息
- 继续同源窄派生预期不会显著改进

## 9. 禁止事项核查

- stage_c_started: false
- rejected_factors_used: false
- random_formula_generated: false
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

## 10. 最终结论

本阶段完成第二轮阶段 B：低波动 + 下行波动极窄组合历史检查。结果仅为历史研究结果，尚未经过未来前向验证，不得用于交易。
