# 来源质量报告

生成时间：2026-07-05

## 质量判断口径

本阶段只使用文字级别判断：

- high：官方项目、官方文档或结构清晰的公开论文
- medium：公开资料有明确方向，但缺少足够 A 股本地复验细节
- low：营销性、信息残缺或难以追溯
- uncertain：还需要人工复核

这不是 AlphaGPT 因子评级，也不是投资建议。

## 当前来源质量

- high
  - Firecrawl 官方 GitHub
  - Firecrawl self-hosting 文档
  - Microsoft Qlib GitHub
  - Qlib 论文

- medium
  - Qlib Alpha158-style workflow 配置公开路径
  - Smart Beta 公开条目
  - Stockformer 公开论文摘要
  - 多因子市场中性公开论文摘要
  - A 股分层基本面投资公开论文摘要

## 主要风险

- 部分资料不是 A 股专属，只能作为方法参考。
- 公开摘要无法替代完整论文和本地复验。
- 社区策略未来采集时必须区分“来源声称收益”和“AlphaGPT 本地验证收益”。
- 文本资料可能存在幸存者偏差、过拟合、成本遗漏和营销包装。

## 下一步建议

在用户设置 Firecrawl Cloud API key 或安装 Docker/Node 后，优先对聚宽、米筐、BigQuant 和 GitHub 公开项目做 5-10 条小批量真实抓取，并人工复核页面抽取质量。
