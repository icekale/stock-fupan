# 运行时数据源选项与 a-stock-data 增强源设计

日期：2026-06-01
状态：已确认设计，待用户审阅

## 目标

在后台首页加入可保存的数据源接入选项，让用户可以在 Web 后台切换报告生成链路的数据源，而不是只查看 `.env` 当前状态。配置保存到 SQLite，服务重启后仍生效。

本阶段同时纳入 `simonlin1212/a-stock-data` 中适合当前报告链路的增强源。它作为补充数据源，不替代 TickFlow 行情主源。

## 已确认决策

- 后台配置持久化使用 SQLite。
- `.env` 保留 API Key、默认值和不可由 Web 修改的环境配置。
- 第一版只覆盖核心生成链路：行情源、新闻源、复盘辅助源。
- a-stock-data 第一版定位为增强层，不作为 TickFlow 的行情主源替代。
- 不在后台编辑或展示 API Key 明文。

## 范围

### 后台可配置项

1. 行情源
   - `tickflow`
   - `fake`
   - 第一版不提供 `a_stock_data` 作为行情主源。

2. 新闻源
   - `anspire`
   - `eastmoney_global`
   - `fake`

3. 复盘辅助源
   - `ths_fupan`
   - `eastmoney_ztfp`
   - `thsdk`
   - `a_stock_ths_hot`
   - `a_stock_industry_rank`

4. 回退策略
   - `provider_fallback_enabled`

### 非目标

- 不写回 `.env`。
- 不在 Web 后台管理 API Key。
- 不一次性接入 a-stock-data 的研报、龙虎榜、资金流、公告、财务、K 线等全部端点。
- 不把 a-stock-data 做成独立插件系统。
- 不改变周报 TickFlow 数据客户端。

## 数据模型

新增 SQLite 表 `runtime_provider_config`：

```text
id                 integer primary key
market_provider    string
news_provider      string
review_sources     json array
fallback_enabled   boolean
created_at         datetime
updated_at         datetime
```

只保留一条生效配置。若表为空，运行时配置从 `Settings` 默认值生成：

- `market_provider = settings.market_provider`
- `news_provider = settings.news_provider`
- `review_sources` 根据 `review_sources_enabled`、`thsdk_enabled` 推导
- `fallback_enabled = settings.provider_fallback_enabled`

## 后端 API

新增 `GET /api/data-sources/options`。

返回：

```json
{
  "current": {
    "market_provider": "tickflow",
    "news_provider": "anspire",
    "review_sources": ["ths_fupan", "eastmoney_ztfp"],
    "fallback_enabled": true,
    "updated_at": "2026-06-01T10:00:00+08:00"
  },
  "categories": [
    {
      "key": "market_provider",
      "label": "行情源",
      "selection": "single",
      "options": [
        {
          "key": "tickflow",
          "label": "TickFlow",
          "role": "主源 · 行情",
          "status": "ready",
          "configured": true,
          "requires_key": true,
          "detail": "TICKFLOW_API_KEY 已配置"
        }
      ]
    }
  ]
}
```

新增 `PUT /api/data-sources/options`。

请求：

```json
{
  "market_provider": "tickflow",
  "news_provider": "eastmoney_global",
  "review_sources": ["ths_fupan", "eastmoney_ztfp", "a_stock_ths_hot"],
  "fallback_enabled": true
}
```

校验规则：

- `market_provider` 必须是 `tickflow` 或 `fake`。
- `news_provider` 必须是 `anspire`、`eastmoney_global` 或 `fake`。
- `review_sources` 只能包含已注册复盘辅助源，去重后保存。
- 生产环境仍不能启用 fake provider，除非 `production_allow_fake_providers=true`。
- 不接受 unknown provider，返回 422。

保留现有 `GET /api/config/status`，但数据来源调整为运行时配置 + `.env` 密钥状态，避免后台看到的状态和实际生成使用的配置不一致。

## Provider Registry

新增轻量 registry，集中描述每个可选数据源：

```text
key
category
label
role
requires_key
env_key_name
experimental
default_enabled
```

用途：

- API 返回选项列表。
- `/api/config/status` 生成状态卡片。
- Provider factory 根据运行时配置创建 provider bundle。
- 前端不用硬编码所有 provider 文案。

## a-stock-data 接入

新增 `apps/api/app/providers/a_stock_data.py`，只迁移必要端点和解析逻辑。

### `AStockThsHotProvider`

来源：a-stock-data `ths_hot_reason()`。

用途：复盘辅助源。

输出映射：

- `source = "a-stock-data 同花顺热点"`
- `themes`: 从 `reason` 字段按 `+`、`、`、`,` 拆分，汇总为题材证据。
- `hot_stocks`: 使用 `code`、`name`、`zhangfu`、`reason`。
- `market_notes`: 保留前排强势股的题材归因摘要。

### `AStockIndustryRankProvider`

来源：a-stock-data `industry_comparison()`。

用途：复盘辅助源。

输出映射：

- `source = "a-stock-data 东财行业排名"`
- `themes`: 前 N 个行业，含涨跌幅。
- `hot_stocks`: 行业领涨股。
- `market_notes`: 行业涨跌、上涨家数、下跌家数摘要。

注意：东财接口必须串行请求并限流。第一版该 provider 单次报告只发一次行业排名请求，不做批量循环。

### `EastmoneyGlobalNewsProvider`

来源：a-stock-data `eastmoney_global_news()`。

用途：新闻源，可作为 Anspire 替代。

输出映射：

- 返回 `NewsItem` 列表。
- 因该接口是全市场资讯，不天然按板块检索，`search_sector_news()` 会抓取最近资讯后用 sector 关键词过滤。
- 若过滤为空，返回全市场前几条并降低权重，避免静默空新闻。

## Provider Factory

`create_provider_bundle()` 增加运行时配置输入：

```text
settings + runtime_config -> ProviderBundle
```

FastAPI endpoint 使用数据库中的运行时配置生成报告；CLI 若没有传入数据库配置，继续使用 `.env` 默认值，保证命令行流程不被后台配置阻断。

复盘辅助源创建逻辑：

- 运行时配置包含 `ths_fupan` 时加入 `ThsFupanProvider`。
- 包含 `eastmoney_ztfp` 时加入 `EastmoneyZtFpProvider`。
- 包含 `thsdk` 时加入 `ThsdkProvider`。
- 包含 `a_stock_ths_hot` 时加入 `AStockThsHotProvider`。
- 包含 `a_stock_industry_rank` 时加入 `AStockIndustryRankProvider`。

新闻源创建逻辑：

- `anspire`：沿用现有 Anspire provider 和 fake fallback。
- `eastmoney_global`：创建 `EastmoneyGlobalNewsProvider`，必要时套 fake fallback。
- `fake`：使用 `FakeNewsProvider`。

## 前端设计

`DataSourceStatusPanel` 升级为可配置组件：

- 行情源：单选分段控件。
- 新闻源：单选分段控件。
- 复盘辅助源：复选框列表。
- 回退策略：开关。
- 保存按钮：调用 `PUT /api/data-sources/options`。
- 状态信息：每个选项展示 `ready`、`missing_key`、`disabled`、`experimental`。

页面加载时：

1. 调用 `GET /api/data-sources/options`。
2. 填充表单。
3. 保存成功后刷新 `GET /api/config/status`。

UI 原则：

- 不显示 API Key 明文。
- 缺 Key 的选项可以展示但不可作为可用状态误导。
- 已启用但缺 Key 的源保存后，生成报告时按 fallback 策略处理；若 fallback 关闭，则生成失败并返回清晰错误。

## 错误处理

- 外部 HTTP 失败统一转为 provider status reason，不返回 stack trace。
- 东财接口失败时 reason 使用短文本，如“东财行业排名请求失败: HTTP 403”。
- 同花顺热点空结果返回 failed，不抛出未处理异常。
- 保存配置失败返回 422 或 500，前端展示错误文本并保留用户当前表单状态。

## 测试策略

后端：

- runtime config 表为空时从 Settings 推导默认配置。
- `PUT /api/data-sources/options` 能保存并被 `GET` 读回。
- unknown provider 返回 422。
- provider factory 根据运行时配置创建正确 provider 列表。
- `AStockThsHotProvider` 用 fake HTTP payload 映射为 `ReviewSourceResult`。
- `AStockIndustryRankProvider` 用 fake payload 映射为行业主题证据。
- `EastmoneyGlobalNewsProvider` 用 fake payload 映射为 `NewsItem`。
- `/api/config/status` 反映运行时配置，不泄露 key。

前端：

- 类型检查覆盖新增 API 类型。
- 组件测试覆盖 `experimental`、`missing_key`、多选复盘源、保存按钮状态。
- 首页加载配置失败时不阻断报告生成区域渲染。

验收：

- 后台能修改新闻源为 `eastmoney_global`，刷新页面后选择仍保留。
- 后台能启用 `a_stock_ths_hot` 和 `a_stock_industry_rank`。
- 生成报告后 `provider_status.review_sources` 包含启用的 a-stock-data provider 状态。
- `snapshot.json` 写入新的 provider status。
