# AlphaGPT 研究数据库位置定位报告

## 1. 结论摘要

**`ashare_research.sqlite3` 已找到，位于旧项目目录，未丢失。**

| 项目 | 值 |
| ---- | --- |
| 数据库是否存在 | ✅ **存在** |
| 实际路径 | `C:\Users\Admin\alphaGPT\stock-data\ashare_research.sqlite3` |
| 文件大小 | 6.3 GB |
| 修改时间 | 2026-06-27 22:58 |
| `a_stock_selector.sqlite3` | 同目录，4.4 GB |

## 2. 当前机器数据库存在性检查

### 2.1 ashare_research.sqlite3

| 路径 | 状态 |
| ---- | ---- |
| `D:\alphaGPT\github_safe_sync\stock-data\ashare_research.sqlite3` | ❌ 不存在 |
| `C:\Users\Admin\alphaGPT\stock-data\ashare_research.sqlite3` | ✅ **存在（6.3 GB）** |
| D 盘其他位置 | ❌ 不存在 |

### 2.2 a_stock_selector.sqlite3

| 路径 | 状态 |
| ---- | ---- |
| `D:\alphaGPT\github_safe_sync\stock-data\a_stock_selector.sqlite3` | ❌ 不存在 |
| `C:\Users\Admin\alphaGPT\stock-data\a_stock_selector.sqlite3` | ✅ 存在（4.4 GB） |
| `D:\stock-data\a_stock_selector.sqlite3` | ✅ 存在（4.4 GB，副本） |

## 3. 旧项目完整路径

旧 AlphaGPT 项目根目录：

```text
C:\Users\Admin\alphaGPT\
```

目录结构：

```text
C:\Users\Admin\alphaGPT\
├── stock-data\
│   ├── ashare_research.sqlite3        (6.3 GB, 2026-06-27)
│   ├── a_stock_selector.sqlite3       (4.4 GB, 2026-06-14)
│   ├── a_stock_selector.sqlite3-shm   (32 KB)
│   ├── a_stock_selector.sqlite3-wal   (0 B)
│   └── sector_etf_map.csv             (12 KB)
├── ashare_research\
├── config\
├── tests\
├── .venv\
├── .gitignore
├── .env.example
├── CATREADME.md
├── MANIFEST.json
├── SHA256SUMS.txt
└── ...
```

## 4. 第一批 run_config 中记录的 db_path

所有历史 run 的配置文件均使用相对路径：

| 运行 | run_config 路径 | sqlite_path |
| ---- | --------------- | ----------- |
| factor_research_v2_20260628_110010 | `/d/alphaGPT_runtime/runs/.../run_config.yaml` | `stock-data/ashare_research.sqlite3` |
| factor_research_v2_20260630_220303 | `/d/alphaGPT_runtime/runs/.../run_config.yaml` | `stock-data/ashare_research.sqlite3` |
| factor_research_v2_revalidation_20260703_215238 | `/d/alphaGPT_runtime/runs/.../run_config.yaml` | `stock-data/ashare_research.sqlite3` |

所有配置文件均写为 `sqlite_path: stock-data/ashare_research.sqlite3` 的相对路径形式。

## 5. 旧 WorkBuddy 路径检查

交接文件记录的路径：

```text
/Users/Zhuanz/WorkBuddy/alphaGPT/
```

| 路径 | 可访问性 |
| ---- | -------- |
| `/Users/Zhuanz/WorkBuddy/alphaGPT/` | ❌ 不可访问（Linux/macOS 路径，当前为 Windows） |
| `C:\Users\Admin\WorkBuddy\` | ✅ 存在，但无 alphaGPT 子目录 |
| `C:\Users\Admin\alphaGPT\` | ✅ **存在，即实际旧项目位置** |

## 6. 路径差异原因分析

### 6.1 旧项目 → 新项目的安全同步

`docs/SAFE_SYNC_AUDIT.md` 记录了第一次 GitHub 安全同步的完整性审计。关键排除项：

```text
Excluded: stock-data/    ← 数据库被排除
Excluded: local SQLite databases
Excluded: .venv/
Excluded: raw market data
Excluded: full run directories
```

`D:\alphaGPT\github_safe_sync\` 是精选公开同步包，不是旧项目的完整副本。

### 6.2 数据库未被排除原因

- 大小：6.3 GB（远超 20MB 限制）
- 性质：本地派生数据，不应同步到 GitHub
- 在 `.gitignore` 中被忽略

### 6.3 两条路径的关系

```text
旧项目（完整）：  C:\Users\Admin\alphaGPT\          ← 包含数据库
                    │
                    │ 精选文件同步（排除 stock-data/）
                    ▼
新仓库（代码）：  D:\alphaGPT\github_safe_sync\      ← 不含数据库
                    │
                    │ 接续开发
                    ▼
                  D:\alphaGPT\github_safe_sync\      ← 需要恢复数据库访问
```

## 7. 可操作性评估

| 操作 | 可行性 | 说明 |
| ---- | ------ | ---- |
| 从旧目录拷贝数据库 | ✅ | `copy "C:\Users\Admin\alphaGPT\stock-data\ashare_research.sqlite3" "D:\alphaGPT\github_safe_sync\stock-data\"` |
| 从旧目录创建符号链接 | ⚠️ | Windows `mklink` 需管理员权限 |
| 从 D:\stock-data\ 恢复 | ❌ | 只有 `a_stock_selector.sqlite3`，无研究派生表 |
| 重新构建 | ❌ | 缺乏构建脚本和数据源 |

## 8. 下一步建议

1. **推荐方案**：将 `C:\Users\Admin\alphaGPT\stock-data\ashare_research.sqlite3` 复制到 `D:\alphaGPT\github_safe_sync\stock-data\ashare_research.sqlite3`。
2. **替代方案**：修改 pipeline 配置指向旧路径（但会破坏相对路径约定）。
3. **长期方案**：将数据库构建流程也纳入版本管理，使数据库可在任何环境中重建。

## 9. 禁止事项核查

- database_rebuilt_from_scratch: false
- pipeline_modified: false
- backtest_run: false
- new_formula_generated: false
- search_started: false
- external_data_downloaded: false
- trading_advice_generated: false

---

**最终结论：本阶段只完成数据库位置定位。未回测，未搜索，未生成公式，未重建数据库。**
