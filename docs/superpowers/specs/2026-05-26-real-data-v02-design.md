# v0.2 真实数据源接入设计

日期：2026-05-26  
状态：已获用户口头确认，待 implementation plan  
目标版本：v0.2a 真实行情与新闻源优先接入

## 1. 目标

在 v0.1 本地复盘闭环基础上，接入真实 AkShare 行情与 Anspire 新闻搜索。系统默认尝试真实源，失败时自动回退 fake provider，并把失败原因清晰返回给前端和快照文件。

本阶段不追求完整历史补档，也不接入真实 LLM。目标是让当天/当前收盘后的复盘尽量使用真实行情和真实新闻，同时保持本地 MVP 的稳定性。

## 2. 已确认决策

- 数据源策略：默认真实源，失败自动回退 fake。
- 前端提示：显示详细失败原因，而不是静默回退。
- AkShare 范围：只支持当天/当前收盘后快照；历史交易日先回退 fake。
- Anspire 范围：按强势板块关键词搜索新闻；无 key、401、超时、空结果或响应异常均回退 fake。
- 单元测试：不依赖真实网络，用 monkeypatch/fake client 模拟成功、失败、无 key和历史日期。
- v0.2 不做：历史补档、自选股导入、OCR、定时任务、真实 LLM、健康检查页面、任务队列。

## 3. 架构方案

采用 Provider Factory + Fallback Wrapper。

后端 endpoint 不直接实例化具体 provider，而是调用工厂函数创建 provider bundle：

1. 工厂读取 `Settings`。
2. 若配置为真实源，构造真实 provider。
3. 用 fallback wrapper 包住真实 provider 和 fake provider。
4. 真实 provider 成功时返回真实数据和成功状态。
5. 真实 provider 失败时记录错误，调用 fake provider，并把 fallback 状态写入结果。

这样 endpoint、report generator、前端 response 都只消费统一的 provider 状态，不需要知道错误来自 AkShare、Anspire、网络还是配置。

## 4. 配置

新增或明确以下 `.env` 配置：

```dotenv
MARKET_PROVIDER=akshare
NEWS_PROVIDER=anspire
PROVIDER_FALLBACK_ENABLED=true
PROVIDER_TIMEOUT_SECONDS=12
ANSPIRE_BASE_URL=https://plugin.anspire.cn/api/ntsearch/search
ANSPIRE_API_KEY=
NEWS_TOP_K=10
NEWS_LOOKBACK_HOURS=36
```

`MARKET_PROVIDER` 支持：

- `akshare`：默认，尝试 AkShare，失败回退 fake。
- `fake`：只使用 fake provider。

`NEWS_PROVIDER` 支持：

- `anspire`：默认，尝试 Anspire，失败回退 fake。
- `fake`：只使用 fake provider。

若 `PROVIDER_FALLBACK_ENABLED=false`，真实源失败时直接抛错，API 返回错误。v0.2 默认开启 fallback。

## 5. Provider 状态模型

API response 和 `snapshot.json` 新增 `provider_status`：

```json
{
  "market": {
    "provider": "akshare",
    "status": "fallback",
    "fallback_used": true,
    "reason": "AkShare v0.2 only supports current trade date; requested 2026-05-25"
  },
  "news": [
    {
      "sector": "机器人",
      "provider": "anspire",
      "status": "success",
      "fallback_used": false,
      "reason": null
    }
  ]
}
```

字段约束：

- `status` 取值：`success`、`fallback`、`disabled`、`failed`。
- `fallback_used=true` 表示最终报告中的该部分使用 fake provider。
- `reason` 面向前端展示，必须是安全、简短、可读的中文或英文错误摘要。
- 原始异常 stack trace 不返回前端。

## 6. AkShare 行情 provider

新增 `AkShareMarketDataProvider`，实现 `MarketDataProvider`。

v0.2 使用 AkShare 的当前快照接口组合生成 `MarketCloseSnapshot`：

- 指数：优先取上证指数、创业板指等实时指数快照。
- 全市场宽度：从 A 股实时行情计算上涨/下跌数量。
- 涨停/跌停：从 A 股实时行情涨跌幅近似计算，`pct_change >= 9.8` 视作涨停，`pct_change <= -9.8` 视作跌停。
- 成交额：汇总 A 股实时行情成交额并换算为亿元。
- 强势板块：优先取东财行业/概念板块实时排行；若接口不可用，回退 fake。
- 市场标签：沿用 v0.1 简单标签，基于宽度和成交额生成。

日期处理：

- 若请求日期等于当前日期，尝试真实 AkShare。
- 若请求日期不等于当前日期，抛出可回退异常，reason 为“AkShare v0.2 暂不支持历史日期”。
- 不在 v0.2 中推断交易日历，不做历史行情补齐。

数据清洗：

- 对 AkShare 返回列名做集中映射，避免业务代码依赖中文列名散落各处。
- 缺失值、非数字、空表均抛出可回退异常。
- 成交额单位统一为亿元。

## 7. Anspire 新闻 provider

新增 `AnspireNewsProvider`，实现 `NewsProvider`。

调用方式：

- Endpoint：`GET {ANSPIRE_BASE_URL}`。
- Header：`Authorization: Bearer {ANSPIRE_API_KEY}`。
- Query：
  - `query`：板块名加 A股，例如 `机器人 A股`。
  - `top_k`：来自 `NEWS_TOP_K`。
  - `search_type`：默认 `hybrid`。
  - `FromTime` / `ToTime`：基于交易日和 `NEWS_LOOKBACK_HOURS` 生成。

响应处理：

- 解析标题、链接、来源、摘要、发布时间。
- 每条结果映射为 `NewsItem`。
- 权重先使用 v0.2 简单规则：财经可信来源 `0.9`，普通来源 `0.6`，未知来源 `0.5`。
- 空结果视为可回退失败。
- 不抓取网页全文，不保存完整正文。

安全与错误：

- 缺少 `ANSPIRE_API_KEY` 直接回退 fake，reason 为“ANSPIRE_API_KEY 未配置”。
- 401/403、超时、非 2xx、JSON 结构异常都回退 fake，并返回简短原因。
- 不把 API key、完整 URL token、原始 stack trace 写入前端 response。

## 8. ReportGenerator 变化

`ReportGenerator.generate_close_report()` 返回的 `GeneratedReport` 增加 `provider_status`。

生成过程：

1. 调用 market provider，得到行情快照和 market status。
2. 根据评分后的板块逐个调用 news provider，得到新闻和每个板块的 news status。
3. 把 `provider_status` 写入 `snapshot.json`。
4. API response 返回 `provider_status`。
5. `report.dto.json` 仍保持 ReportDTO 纯报告结构，不塞诊断字段。

## 9. 前端展示

`CreateReportResponse` 增加 `provider_status` 类型。

`ReportPreview` 顶部新增数据源诊断区域：

- 成功：显示“真实行情源 AkShare 已使用”“真实新闻源 Anspire 已使用”。
- 回退：显示黄色提示，包含 provider、fallback 和 reason。
- 多板块新闻回退：按板块列出简短原因，最多展示 5 条，多余折叠为“还有 N 条”。

UI 原则：

- 诊断提示不打断报告预览。
- fake 回退必须显眼，防止用户误以为是真实数据。
- 不显示密钥、stack trace、长原始响应。

## 10. 测试策略

后端：

- AkShare provider 成功：用 monkeypatch 模拟 AkShare DataFrame，断言转换为 `MarketCloseSnapshot`。
- AkShare 历史日期：断言 wrapper 回退 fake，reason 可读。
- AkShare 异常/空数据：断言回退 fake。
- Anspire 成功：用 fake HTTP client 响应，断言映射为 `NewsItem`。
- Anspire 无 key/401/空结果：断言回退 fake。
- API response：断言 `provider_status` 返回并写入 `snapshot.json`。

前端：

- TypeScript 类型检查通过。
- 静态组件测试暂不引入新测试框架；通过 `tsc --noEmit` 覆盖类型。

集成 smoke：

- 无 Anspire key 环境：报告可生成，前端显示 Anspire 回退原因。
- 历史日期：报告可生成，前端显示 AkShare 历史日期回退原因。
- 若本机可访问 AkShare：当天日期尝试真实行情，失败仍回退 fake。

## 11. 非目标

- 不实现 AkShare 历史补档。
- 不实现交易日历判断。
- 不实现自选股导入。
- 不实现 OCR。
- 不实现真实 LLM。
- 不实现后台任务队列或调度。
- 不实现 provider 健康检查页面。
