# v0.2b 结构化 HTML 复盘设计

日期：2026-05-26  
状态：已确认方案 C，待实现计划  
目标参考：`docs/superpowers/specs/2026-05-26-reference-html-north-star.md`

## 1. 背景与目标

v0.2 已经完成真实数据源底座：AkShare 行情、Anspire 新闻、fake fallback、provider diagnostics。下一阶段要优先服务项目的核心目的：稳定生成接近参考 HTML 的结构化 A 股复盘长文/长图。

本阶段选择垂直切片方案：同时建立结构化数据骨架、fake/规则生成逻辑、HTML 核心章节模板和必要测试。它不追求一次覆盖参考 HTML 的全部内容，但必须让端到端产物明显从“轻量 dashboard 报告”转向“冷静金融长文”。

## 2. 范围

v0.2b 必须实现 6 个核心模块：

1. 昨日预判验证
2. 先给结论 + 明日核心判断表
3. 盘面总览
4. 板块详细分析
5. 板块持续性排序
6. 去弱留强 / 回避清单

`昨日预判验证` 在本阶段先使用结构化占位或手动输入预留字段，不强制自动读取前一日报告。自动对比前一日报告放到后续版本。

## 3. 非目标

- 不接 TickFlow。TickFlow key 已收到，但需要接口文档后再作为独立 provider 设计。
- 不做自动昨日预测回放和命中率统计。
- 不输出直接买卖/仓位指令；用观察清单、触发条件、风险分层等表述替代。
- 不移除现有 `ReportDTO`、API 响应、provider diagnostics 或前端工作台能力。
- 不追求逐字逐像素复制参考 HTML；目标是吸收信息架构和视觉语言。

## 4. 数据模型设计

新增结构化复盘模型，建议放在 `apps/api/app/schemas/structured_review.py`，并通过 `ReportDTO.structured_review` 可选字段挂载。

核心模型：

- `PredictionReview`
  - `previous_prediction`: 昨日核心预判摘要。
  - `actual_result`: 今日实际表现。
  - `correct_items`: 命中点列表。
  - `missed_items`: 偏差点列表。
  - `revision`: 后续修正判断。
  - `source`: `manual_placeholder` / `previous_report`。

- `TomorrowJudgement`
  - `most_likely_to_continue`: 最容易继续方向。
  - `most_likely_to_diverge`: 最容易分化方向。
  - `rotation_candidates`: 轮动候选方向。
  - `defensive_candidates`: 防御候选方向。
  - `core_view`: 一句话核心判断。

- `MarketOverviewTable`
  - `index_rows`: 指数表现行。
  - `emotion_rows`: 情绪/涨跌/涨跌停/成交额行。
  - `structure_features`: 市场结构特征。
  - `capital_flow_summary`: 资金轮动摘要。

- `StructuredSectorReview`
  - `sector`: 板块名。
  - `headline`: 板块状态标题。
  - `stage`: 当前阶段判断。
  - `strengths`: 强势证据。
  - `weaknesses`: 弱势/分歧证据。
  - `logic`: 板块逻辑分析。
  - `sustainability`: 持续性评级：`high` / `medium` / `low`。
  - `next_day_view`: 下个交易日看法。
  - `watch_items`: 可观察条件。
  - `avoid_items`: 要回避条件。

- `SustainabilityRank`
  - `rank`: 排名。
  - `sector`: 板块。
  - `rating`: 持续性评级。
  - `reason`: 排序理由。

- `ActionDiscipline`
  - `focus`: 去弱留强方向。
  - `avoid`: 回避清单。
  - `final_view`: 最实战的一句话结论。

- `StructuredReviewDTO`
  - `topic`: 当日行情性质，例如“科技内部淘汰赛 · 主线换挡日”。
  - `prediction_review`
  - `tomorrow_judgement`
  - `market_overview`
  - `sector_reviews`
  - `sustainability_ranking`
  - `action_discipline`

## 5. 生成逻辑

新增 `StructuredReviewBuilder` 服务，输入现有 `ReportDTO` 和必要事实，输出 `StructuredReviewDTO`。

v0.2b 使用确定性规则生成，不依赖 LLM 新能力：

- `topic`: 根据市场标签和前两名板块生成简短行情性质。
- `PredictionReview`: 使用占位文本，明确标注 `source=manual_placeholder`。
- `TomorrowJudgement`: 基于第一、第二强板块和风险项生成。
- `MarketOverviewTable`: 复用 `indices`、`breadth`、`turnover_cny`、`market_state_tags`。
- `StructuredSectorReview`: 基于 `SectorCandidate`、`news_summaries`、`factor_scores` 生成阶段和持续性。
- `SustainabilityRank`: 按 `score`、`news_summaries`、`pct_change` 组合排序。
- `ActionDiscipline`: 从高分板块生成 focus，从低持续性或风险条件生成 avoid。

这些规则先让结构稳定，后续再替换为 LLM/人工输入/真实资金流数据。

## 6. HTML 视觉设计

现有 `mobile_report.html.j2` 升级为结构化长文模板。视觉语言向参考 HTML 靠拢：

- 页面宽度约 640px。
- 背景为米灰，正文为白色/暖白文章卡片。
- 主色为海军蓝，强调色为金色。
- 每个大章节使用编号块，例如 `01`、`02`。
- 结论框使用金色左边框或金色描边。
- 回避/风险框使用克制绿色或低饱和风险色。
- 高频结构信息用表格，不用一堆 dashboard 小卡。
- 板块详细分析要像文章段落与表格混排，而不是后台组件。
- 保留 disclaimer，但措辞应和“观察/复盘”一致。

模板兼容策略：

- 如果 `report.structured_review` 存在，渲染新结构化长文。
- 如果不存在，渲染当前轻量报告布局，避免旧报告崩坏。

## 7. API、快照与前端

API 不新增 endpoint。`POST /api/reports/close` 仍返回现有响应，但 `report` 中增加 `structured_review` 字段。

资产写入：

- `report_dto.json` 包含 `structured_review`。
- `snapshot.json` 保留 `provider_status`，同时包含结构化报告。
- `report.html` 使用结构化模板输出。
- `report.png` 沿用现有导出链路。

前端工作台：

- `apps/web/lib/types.ts` 增加结构化类型。
- `ReportPreview` 可以先不完整复刻 HTML，只需保证不会因新字段破坏现有预览。
- 本阶段主要验收物是生成的 HTML/PNG 资产，而不是工作台 UI 的完整结构化渲染。

## 8. 测试策略

后端测试：

- schema 序列化测试：`StructuredReviewDTO` 能 JSON dump。
- builder 测试：fake report 生成 6 个核心模块。
- generator 测试：`result.report.structured_review` 存在。
- snapshot 测试：`snapshot.json.report.structured_review` 存在。
- renderer 测试：HTML 包含核心章节文案：`昨日预判验证`、`明日核心判断`、`板块详细分析`、`持续性排序`、`去弱留强`、`回避清单`。

前端测试：

- TypeScript 类型检查通过。
- `CreateReportResponse.report.structured_review` 为可选字段，兼容旧数据。

回归测试：

- 全量 `uv run pytest -v`。
- 全量 `uv run ruff check .`。
- `corepack pnpm --filter @stock-review/web test`。
- `corepack pnpm --filter @stock-review/web lint`。

## 9. 验收标准

v0.2b 完成后，使用 fake/fallback 数据生成任意收盘报告时：

- `report.html` 第一眼应明显接近参考 HTML 的“冷静金融长文”方向。
- HTML 至少包含 6 个核心模块。
- 结构化内容来自 `structured_review` 数据，而不是模板硬编码死文案。
- `snapshot.json` 可作为后续回放、调试和 OCR/自选股扩展的数据底座。
- 旧 API 调用方式不变，provider diagnostics 不丢失。
- 测试和类型检查全绿。
