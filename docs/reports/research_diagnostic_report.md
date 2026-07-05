# AlphaGPT v2 第一批正式因子研究诊断报告

本报告只读取已经完成的正式 run 产物，没有重新生成公式、没有启动第二轮搜索、没有修改筛选阈值或评级规则。

## 一句话结论

E. Multiple issues coexist: fast-screen thresholds are permissive, formula space is highly redundant, configured time splits are not actually used by this v2 pipeline, and the original report used generic risk text with incomplete diagnostic detail.

这轮不是简单的“因子空间完全无效”。更准确地说：快筛门槛很宽、公式空间重复严重、配置中的时间分段没有真正进入计算、原始报告解释太粗。

## 漏斗对账

- 目标生成数: 10000
- 实际唯一公式: 2970
- 未形成唯一候选: 7030
- 快筛通过: 2757 (92.83%)
- 相关性输入: 500
- 相关性去重后保留: 94
- 完整回测: 50
- 稳健性通过: 2
- B 级: 2；A 级: 0；Rejected: 48

## 为什么 10000 只得到 2970

生成器实际做了 300000 次尝试，但只落盘唯一有效公式 2970 个。运行产物没有保存每次失败的具体原因，所以不能诚实地把 7030 精确分摊到非法表达式、重复公式、复杂度超限等桶里。代码路径显示这些情况都可能被跳过，但本报告不会伪造精确分布。

## 为什么快筛通过率高

Configured enforced fast-screen thresholds are very permissive: min_abs_rank_ic_mean is 0.001, min_coverage is 0.30, and only coverage, dispersion, and abs(rank_ic_mean) are hard filters. Metrics such as rank_ic_ir, positive_period_ratio, monotonicity, spread, turnover, and stability are computed but not enforced in fast screen.

快筛拒绝原因:
- constant_or_all_missing: 123
- weak_rank_ic: 80
- insufficient_valid_rows: 10

## 时间分段是否生效

- time_split_configured: True
- time_split_effective: False
- fast screen 实际区间: ['20190704', '20260626']
- full backtest 实际区间: ['20190704', '20260626']

配置里有 development / selection / stability，但 v2 流水线实际只用 research_start 到 research_end 的全历史区间。现有产物不能给出三个分段的独立表现。

## 公式重复性

- 相关性输入: 500
- 去重后保留: 94
- 冗余比例: 81.20%
- 最大相关性簇大小: 99

主要原因是公式空间很窄，只有少数基础特征和算子，生成策略又大量围绕近期收益、成交量加权收益和趋势做包装；0.95 相关性阈值会把这些输出很像的公式合并。

## Top 10 完整回测因子

|canonical_formula|grade|total_return|annualized_return|max_drawdown|sharpe|sortino|
|---|---|---|---|---|---|---|
|DECAY_LINEAR20(MUL(RET1,TREND60))|B|0.139385|0.0196246|-0.68722|0.0583669|0.0877012|
|DECAY_LINEAR20(MUL(RET5,RET5))|B|0.0759111|0.0109569|-0.644771|0.0337306|0.0519275|
|DECAY_LINEAR20(DECAY_LINEAR20(VOLUME_WEIGHTED_RET))|Rejected|-0.00786241|-0.00117493|-0.662564|-0.0037778|-0.0060301|
|SUB(DELTA5(RET1),TREND60)|Rejected|-0.131667|-0.0208073|-0.604443|-0.0792117|-0.121364|
|ADD(DECAY_LINEAR20(TREND60),TREND60)|Rejected|-0.137349|-0.0217643|-0.656403|-0.065225|-0.0965856|
|DECAY_LINEAR20(MUL(TREND60,VOLUME_WEIGHTED_RET))|Rejected|-0.208336|-0.0341959|-0.711206|-0.106667|-0.161287|
|DECAY_LINEAR20(ABS(RET1))|Rejected|-0.220022|-0.0363326|-0.725837|-0.107482|-0.17135|
|DECAY_LINEAR20(MUL(RET1,RET5))|Rejected|-0.256062|-0.0430986|-0.68222|-0.133715|-0.205327|
|SUB(MUL(RET1,VOL_RATIO20),TREND60)|Rejected|-0.268315|-0.0454625|-0.613505|-0.174496|-0.262326|
|DECAY_LINEAR20(DECAY_LINEAR20(RET1))|Rejected|-0.274334|-0.0466361|-0.747893|-0.145823|-0.22261|

## Bottom 10 完整回测因子

|canonical_formula|grade|total_return|annualized_return|max_drawdown|sharpe|sortino|
|---|---|---|---|---|---|---|
|ADD(DELTA5(RET5),TREND60)|Rejected|-0.810991|-0.219735|-0.864708|-0.762592|-1.09232|
|ABS(MUL(RET5,VOLUME_WEIGHTED_RET))|Rejected|-0.807957|-0.217882|-0.866557|-0.838783|-1.24306|
|ADD(ADD(VOLUME_WEIGHTED_RET,VOLUME_WEIGHTED_RET),TREND60)|Rejected|-0.782252|-0.203112|-0.84621|-0.718677|-1.04255|
|MUL(ABS(RET1),TREND60)|Rejected|-0.780124|-0.201957|-0.859552|-0.694609|-0.990593|
|ADD(SIGN(VOL_RATIO20),TREND60)|Rejected|-0.76642|-0.194738|-0.845364|-0.659602|-0.940394|
|ADD(DECAY_LINEAR20(RET5),RET5)|Rejected|-0.757398|-0.19018|-0.831294|-0.656371|-0.957986|
|ADD(ADD(TREND60,TREND60),VOL_RATIO20)|Rejected|-0.757294|-0.190128|-0.808833|-0.735312|-1.08646|
|ADD(ABS(RET5),RET5)|Rejected|-0.753099|-0.188059|-0.833644|-0.678101|-0.996778|
|ADD(SIGN(RET5),TREND60)|Rejected|-0.748708|-0.185924|-0.838503|-0.638702|-0.91091|
|ADD(RET5,SIGN(TREND60))|Rejected|-0.746998|-0.185101|-0.81895|-0.677482|-0.968699|

## 两个 B 级因子

### B 因子 1: `DECAY_LINEAR20(MUL(RET1,TREND60))`

- 中文解释: 20日线性衰减(相乘(1日收益,60日趋势))
- 年化收益: 0.0196246
- 总收益: 0.139385
- 最大回撤: -0.68722
- Sharpe: 0.0583669
- Sortino: 0.0877012
- 完成交易数: 8264
- 交易胜率: None（summary_only 产物未提供）
- 稳健性结果: not_run_mvp / not_run_mvp；MVP positive_period_ratio=None
- 为什么是 B: abs_rank_ic_mean 0.051082 >= grade_b_min_abs_ic 0.015000; total_return 0.139385 > 0; not_A_because_abs_max_drawdown 0.687220 > grade_a_max_drawdown 0.350000
- 为什么不是 A: 最大回撤绝对值超过 A 级上限 0.35，且 A 级还要求更强的回撤约束。

### B 因子 2: `DECAY_LINEAR20(MUL(RET5,RET5))`

- 中文解释: 20日线性衰减(相乘(5日收益,5日收益))
- 年化收益: 0.0109569
- 总收益: 0.0759111
- 最大回撤: -0.644771
- Sharpe: 0.0337306
- Sortino: 0.0519275
- 完成交易数: 8107
- 交易胜率: None（summary_only 产物未提供）
- 稳健性结果: not_run_mvp / not_run_mvp；MVP positive_period_ratio=None
- 为什么是 B: abs_rank_ic_mean 0.055887 >= grade_b_min_abs_ic 0.015000; total_return 0.075911 > 0; not_A_because_abs_max_drawdown 0.644771 > grade_a_max_drawdown 0.350000
- 为什么不是 A: 最大回撤绝对值超过 A 级上限 0.35，且 A 级还要求更强的回撤约束。

特别说明：`RET5 * RET5` 会丢失涨跌方向，更接近近期波动强度或绝对动量强度。系统判定它有正向选股意义，不是因为它知道方向，而是因为完整回测中按该信号排序后的组合在扣成本后仍为正收益，同时快筛的 `abs(rank_ic_mean)` 达到 B 门槛。

## Rejected 淘汰原因统计

- 成本后总收益为负: 48
- 稳健性未通过: 48
- 滚动/分段正收益比例不足(MVP口径): 48
- Sortino为负或为零: 48
- 最大回撤超过A级门槛: 48

## 文件

- full_backtest_detail_file: `D:\alphaGPT_runtime\runs\factor_research_v2_20260630_220303\diagnostics\full_backtest_50_factors.csv`
- fast_screen_audit_file: `D:\alphaGPT_runtime\runs\factor_research_v2_20260630_220303\diagnostics\fast_screen_rule_audit.json`
- fast_screen_metric_distribution_file: `D:\alphaGPT_runtime\runs\factor_research_v2_20260630_220303\diagnostics\fast_screen_metric_distribution.csv`
- fast_screen_rejection_matrix_file: `D:\alphaGPT_runtime\runs\factor_research_v2_20260630_220303\diagnostics\fast_screen_rejection_matrix.csv`
- rating_audit_file: `D:\alphaGPT_runtime\runs\factor_research_v2_20260630_220303\diagnostics\rating_rule_audit.json`
- redundancy_report_file: `D:\alphaGPT_runtime\runs\factor_research_v2_20260630_220303\diagnostics\formula_redundancy_report.json`

## 建议

Do not simply expand candidate_count first. First make the next approved engineering round decide whether time splits and required robustness checks should become real computations, and whether the formula generator should reduce duplicate motifs; keep thresholds unchanged unless separately approved.

本报告不构成投资建议，也不表示两个 B 级因子可以直接进入前向观察。
