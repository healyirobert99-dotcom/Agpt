# 前向观察 (Forward Observation)

> ⚠️ OBSERVATION ONLY. No trading, no orders, no broker.

此目录存储低波动主候选 `NEG(RET_STD20) + 5d rebalance` 的每日前向观察输出。

## 目录结构

```
low_vol_5d/
├── YYYYMMDD_observation.json  # 完整 JSON 数据
└── YYYYMMDD_observation.md    # 可读 Markdown 报告
```

## 运行

```powershell
cd D:\alphaGPT\github_safe_sync
python -m ashare_research.forward_observation.observe_low_vol_5d
```

## 前置条件

- 数据库 `stock-data/ashare_research.sqlite3` 必须存在
- 不修改任何配置文件
- 不生成交易指令
