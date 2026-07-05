# AlphaGPT 第二轮阶段 B Readiness 报告

## 1. Commit 口径核对

| 项目 | 值 |
| ---- | --- |
| stage_a_run_commit | 2ea176cf6d9a826099679cda971a01bb0d57bfec |
| stage_a_report_commit | f5296209300799f3805e3991a7b2cbc80669a784 |
| current_head_commit | f5296209300799f3805e3991a7b2cbc80669a784 |
| working tree | clean |

说明：阶段 A 运行时 HEAD 为 2ea176c，报告在 f529620 提交。两者代码完全一致（仅新增报告文件），无代码差异。

## 2. 阶段 A 结果确认

| 项目 | 状态 |
| ---- | ---- |
| 阶段 A 结果文件存在 | ✅ |
| fp_low_vol_011 — NEG(RET_STD20) 通过 | ✅ 评级 B |
| fp_downside_vol_012 — NEG(DOWNSIDE_RET_STD20) 通过 | ✅ 评级 C |

## 3. 阶段 B 候选范围检查

| 项目 | 状态 | 说明 |
| ---- | ---- | ---- |
| 只使用阶段 A 通过因子 | ✅ | 仅 fp_low_vol_011 + fp_downside_vol_012 |
| 不使用 rejected 因子 | ✅ | 5 个 rejected 因子全部排除 |
| 不使用库外因子 | ✅ | |
| 候选数量 | 2 | B1 等权、B2 交互 |
| 候选类型 | stage_b_low_vol_downside_vol_combination | |
| 随机搜索 | 否 | 固定候选 |

## 4. 特征与算子检查

| 项目 | 状态 |
| ---- | ---- |
| 新增基础特征 | 否 |
| 新增算子 | 否 |
| 新增外部数据 | 否 |
| 访问 forward data | 否 |
| 修改筛选标准 | 否 |
| 修改评级规则 | 否 |
| 修改回测逻辑 | 否 |
| 修改 time split | 否 |

## 5. 候选公示

| # | 名称 | 公式 | 特征依赖 | 算子依赖 |
|---|------|------|---------|---------|
| B1 | 等权组合 | ADD(NEG(RET_STD20),NEG(DOWNSIDE_RET_STD20)) | RET_STD20, DOWNSIDE_RET_STD20 | ADD, NEG |
| B2 | 交互组合 | MUL(NEG(RET_STD20),NEG(DOWNSIDE_RET_STD20)) | RET_STD20, DOWNSIDE_RET_STD20 | MUL, NEG |

候选 3（加权 ADD+MUL 0.5）因系统不支持常数乘法算子，跳过。

## 6. Readiness 结论

**✅ 通过。可运行阶段 B。**
