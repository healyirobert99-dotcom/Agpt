# AlphaGPT 第二轮阶段 A Readiness 报告

## 1. 环境检查

| 项目 | 状态 | 详情 |
| ---- | ---- | ---- |
| 当前 HEAD | f7adb0a | Add second round minimal search run draft (three-phase plan A/B/C) |
| working tree | clean | nothing to commit |
| 7 个 seed factor 是否存在 | ✅ | second_batch_seed_factor_manifest.jsonl 包含全部 7 个因子 |
| second_round_gate 通过 | ✅ | passed, no failures |
| 数据库 stock-data/ashare_research.sqlite3 | ❌ | **文件不存在，无法运行 pipeline** |
| 数据库 stock-data/a_stock_selector.sqlite3 | ❌ | **文件不存在** |

## 2. 种子因子逐项检查

### 2.1 fp_momentum_mid_009 — 中期价格动量

| 项目 | 值 |
| ---- | --- |
| 需要基础特征 | RET20, RET60, RET120, TREND20, TREND60, TREND120 |
| 当前 BASE_FEATURES 是否包含 | 部分：TREND60 ✅；RET20/RET60/RET120/TREND20/TREND120 ✅（代码已实现） |
| 当前 config allowed features 是否包含 | ❌ 配置只允许 [RET1, RET5, VOL_RATIO20, VOLUME_WEIGHTED_RET, TREND60] |
| 是否需要新增外部数据 | 否 |
| 是否需要新增算子 | 否 |
| **可执行性** | **需配置更新（扩展 allowed features 包含 RET20/RET60/RET120/TREND20/TREND120）** |

### 2.2 fp_reversal_short_010 — 短期反转

| 项目 | 值 |
| ---- | --- |
| 需要基础特征 | RET1, RET5 |
| 当前 BASE_FEATURES 是否包含 | ✅ |
| 当前 config allowed features 是否包含 | ✅ |
| 是否需要新增外部数据 | 否 |
| 是否需要新增算子 | 否 |
| **可执行性** | **✅ 可直接执行** |

### 2.3 fp_low_vol_011 — 低波动

| 项目 | 值 |
| ---- | --- |
| 需要基础特征 | RET_STD20, RET_STD60 |
| 当前 BASE_FEATURES 是否包含 | ✅（代码已实现） |
| 当前 config allowed features 是否包含 | ❌ 配置只允许 [RET1, RET5, VOL_RATIO20, VOLUME_WEIGHTED_RET, TREND60] |
| 是否需要新增外部数据 | 否 |
| 是否需要新增算子 | 否 |
| **可执行性** | **需配置更新（扩展 allowed features 包含 RET_STD20/RET_STD60）** |

### 2.4 fp_downside_vol_012 — 下行波动

| 项目 | 值 |
| ---- | --- |
| 需要基础特征 | DOWNSIDE_RET_STD20, DOWNSIDE_RET_STD60 |
| 当前 BASE_FEATURES 是否包含 | ✅（代码已实现） |
| 当前 config allowed features 是否包含 | ❌ |
| 是否需要新增外部数据 | 否 |
| 是否需要新增算子 | 否 |
| **可执行性** | **需配置更新** |

### 2.5 fp_amount_liquidity_014 — 成交额流动性

| 项目 | 值 |
| ---- | --- |
| 需要基础特征 | AMOUNT_MA20, AMOUNT_MA60 |
| 当前 BASE_FEATURES 是否包含 | ✅（代码已实现） |
| 当前 config allowed features 是否包含 | ❌ |
| 是否需要新增外部数据 | 否 |
| 是否需要新增算子 | 否 |
| **可执行性** | **需配置更新** |

### 2.6 fp_price_volume_interaction_018 — 量价配合

| 项目 | 值 |
| ---- | --- |
| 需要基础特征 | RET1, RET5, VOL_RATIO20, VOLUME_WEIGHTED_RET |
| 当前 BASE_FEATURES 是否包含 | ✅ |
| 当前 config allowed features 是否包含 | ✅ |
| 是否需要新增外部数据 | 否 |
| 是否需要新增算子 | 否 |
| **可执行性** | **✅ 可直接执行** |

### 2.7 fp_multi_frequency_trend_019 — 多频趋势

| 项目 | 值 |
| ---- | --- |
| 需要基础特征 | TREND20, TREND60, TREND120 |
| 当前 BASE_FEATURES 是否包含 | ✅（代码已实现） |
| 当前 config allowed features 是否包含 | ❌ 配置只允许 TREND60 |
| 是否需要新增外部数据 | 否 |
| 是否需要新增算子 | 否 |
| **可执行性** | **需配置更新（扩展 allowed features 包含 TREND20/TREND120）** |

## 3. 汇总

| 类别 | 数量 | 因子 |
| ---- | ---- | ---- |
| 可直接执行 | 2 | fp_reversal_short_010, fp_price_volume_interaction_018 |
| 代码已实现，需配置更新 | 5 | fp_momentum_mid_009, fp_low_vol_011, fp_downside_vol_012, fp_amount_liquidity_014, fp_multi_frequency_trend_019 |
| 需新增基础特征 | 0 | （11 个特征已在代码中实现） |
| 需新增外部数据 | 0 | |
| 需新增算子 | 0 | |

## 4. 外部依赖检查

| 项目 | 是否违反 | 说明 |
| ---- | -------- | ---- |
| 违反 second_round_gate | 否 | gate passed |
| 访问 forward data | 否 | research_end 不晚于 20260626 |
| 修改筛选标准 | 否 | 使用当前 locked_thresholds |
| 修改评级标准 | 否 | 使用当前 locked_thresholds.rating |
| 新增外部数据 | 否 | 全部 7 个因子只依赖日线价量 |
| 新增算子 | 否 | 只用现有 10 个算子 |
| 库外因子 | 否 | 全部来自 second_batch_seed_factor_manifest.jsonl |

## 5. Readiness 结论

| 结论 | 详情 |
| ---- | ---- |
| **数据库** | ❌ `stock-data/ashare_research.sqlite3` 不存在，pipeline 无法运行 |
| **配置覆盖** | ⚠️ 5 个因子需在 config 中扩展 allowed features 才能执行 |
| **可直接执行** | 2/7（fp_reversal_short_010, fp_price_volume_interaction_018） |
| **代码就绪** | 7/7（所有特征和算子已实现，无代码缺失） |

**当前结论：阶段 A 不具备完整运行条件。需要在有数据库和扩展 allowed features 配置的环境中执行。**

本报告为只读诊断，未修改任何代码或配置，未运行搜索或回测。
