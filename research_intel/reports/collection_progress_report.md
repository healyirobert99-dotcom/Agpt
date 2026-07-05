# 第一批信息收集进度报告

生成时间：2026-07-05

## 采集方式

由于当前机器没有 Docker / Node.js，且未设置 `FIRECRAWL_API_KEY`，本轮没有执行 Firecrawl 真实联网抓取。

本轮完成的是第一批公开来源登记和代表性资料摘要整理，作为 Firecrawl 可用后的采集种子和人工复核基线。

## 已登记公开来源

- Firecrawl 官方 GitHub
- Firecrawl self-hosting 官方文档
- Microsoft Qlib GitHub
- Qlib Alpha158-style workflow 配置公开路径
- Qlib 论文
- Smart Beta 公开百科条目
- Stockformer 公开论文摘要
- 多因子市场中性公开论文摘要
- A 股分层基本面投资公开论文摘要

实际登记来源数量：9

## 成功解析资料

- `parsed/extracted_factor_notes.jsonl`：20 条因子笔记
- `parsed/extracted_strategy_notes.jsonl`：20 条策略操作笔记
- `library/factor_prior_library.jsonl`：20 条因子先验
- `library/trading_strategy_library.jsonl`：20 条交易操作策略

## 失败或未采集项

- 聚宽社区、米筐、BigQuant 的真实页面尚未执行 Firecrawl 抓取。
- 原因：Firecrawl API key 未设置，当前环境也没有自托管依赖。
- 处理：已在 `sources/source_seed_list.md` 保留为第一优先级来源，待 Firecrawl 可用后小批量采集 5-10 条代表性资料。

## Markdown 抽取质量

- 本轮没有真实 Firecrawl Markdown 抽取，因此不评价页面正文抽取质量。
- 当前库为公开资料摘要和结构化整理，不含完整文章或完整策略代码。

## 限制检查

- 登录限制：未尝试绕过
- 版权限制：未复制完整文章、完整研报或完整策略代码
- robots/反爬限制：未尝试绕过
- AlphaGPT 主程序：未修改
- AlphaGPT 回测/搜索：未运行
- forward data：未访问
