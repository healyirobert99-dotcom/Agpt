# Firecrawl 部署核查报告

生成时间：2026-07-05

## 环境核查

- 操作系统：Microsoft Windows NT 10.0.19044.0
- PowerShell：5.1.19041.7058
- Python：3.12.7，可用
- Docker：不可用，`docker` 命令不存在
- Docker Compose：不可用，`docker` 命令不存在
- Node.js：不可用，`node` 命令不存在
- npm：不可用，`npm` 命令不存在
- pnpm：不可用，`pnpm` 命令不存在
- FIRECRAWL_API_KEY：未设置，未打印、未保存任何 token

## 部署结论

Firecrawl 自托管没有启动。

原因：

- 当前机器没有 Docker / Docker Compose。
- 当前机器没有 Node.js / npm / pnpm。
- 当前 shell 环境没有 `FIRECRAWL_API_KEY`，不能调用 Firecrawl Cloud API。

本阶段采用保守降级方案：

- 建立独立信息收集目录：`D:\alphaGPT_runtime\research_intel`
- 建立独立 Firecrawl 工具目录：`D:\alphaGPT_runtime\tools\firecrawl`
- 先生成来源登记、解析笔记、因子先验库、交易操作策略库和报告。
- 后续如果用户在本机环境变量设置 `FIRECRAWL_API_KEY`，可运行 Firecrawl Cloud API 小批量采集。

## 官方资料核对

- Firecrawl 官方 GitHub：`https://github.com/firecrawl/firecrawl`
- Firecrawl self-hosting 文档：`https://docs.firecrawl.dev/contributing/self-host`

公开资料显示 Firecrawl 可用于搜索、抓取网页并输出 Markdown/结构化数据；自托管依赖官方部署说明和本机容器环境。当前机器不满足自托管条件。

## API 可调用性

- API key：未设置
- API 测试采集：未执行真实联网调用
- Dry-run 脚本：已在沙箱目录验证

## 安全边界

- 未写入 API key、cookie、账号密码。
- 未绕过登录、付费墙、反爬限制或 robots。
- 未启动后台常驻服务。
- 未启动 AlphaGPT 回测或第二批搜索。
