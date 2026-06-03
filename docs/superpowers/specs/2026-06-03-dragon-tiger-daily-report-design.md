# 东财龙虎榜融入日报设计

日期：2026-06-03
状态：已确认设计，待实施计划

## 目标

把 `a-stock-data` 的东方财富龙虎榜能力纳入日报，用它评价短线市场情绪、资金攻击强度、主线确认度和次日延续风险。

龙虎榜在本项目中的定位是“情绪资金确认层”，不是独立资讯列表。日报应给出紧凑结论，并把龙虎榜证据传递给市场情绪、板块深挖和次日观察模块。

## 已确认事实

本地实测东财 datacenter 接口可用：

- `RPT_DAILYBILLBOARD_DETAILSNEW`：全市场龙虎榜。
- `RPT_BILLBOARD_DAILYDETAILSBUY`：个股买入席位。
- `RPT_BILLBOARD_DAILYDETAILSSELL`：个股卖出席位。

`2026-06-03` 全市场龙虎榜返回 `91` 条记录。样例：

- `002156 通富微电`，净买额约 `162241.54` 万。
- `600487 亨通光电`，净买额约 `99262.93` 万。
- `002046 国机精工`，净买额约 `37777.68` 万。

接口过滤注意事项：

- `SECURITY_CODE` 必须使用双引号，例如 `(SECURITY_CODE="002156")`。
- 使用单引号会触发东财参数预处理错误，错误码 `9501`。
- 多接口请求需要串行执行，避免高频请求。

## 范围

### 包含

1. 新增 `a_stock_dragon_tiger` 复盘辅助源。
2. 后台数据源选项支持开启或关闭该源。
3. 日报 DTO 保存龙虎榜摘要。
4. 结构化复盘使用龙虎榜信号修正市场情绪和板块持续性判断。
5. 次日观察使用龙虎榜信号作为延续概率的加分或扣分证据。
6. HTML 日报新增一个紧凑的“龙虎榜情绪确认”模块。
7. provider status、snapshot、report_dto 输出包含龙虎榜状态。

### 不包含

- 不做营业部画像库。
- 不做席位胜率长期统计。
- 不做个股历史龙虎榜回测。
- 不把龙虎榜替代 TickFlow 行情主源。
- 不在第一版把每只龙虎榜股票逐条长表渲染进日报。

## 数据源设计

新增 `AStockDragonTigerProvider`，放在 `apps/api/app/providers/a_stock_data.py`。

该 provider 作为复盘辅助源参与 `ReviewSourceAggregator`，但需要额外输出结构化龙虎榜摘要。第一版可以通过新增独立 DTO 字段完成，避免把所有字段硬塞进 `ReviewSourceResult.market_notes`。

请求设计：

1. 请求全市场龙虎榜：

```text
reportName=RPT_DAILYBILLBOARD_DETAILSNEW
filter=(TRADE_DATE>='YYYY-MM-DD')(TRADE_DATE<='YYYY-MM-DD')
sortColumns=BILLBOARD_NET_AMT
sortTypes=-1
pageSize=200
```

2. 选取席位明细目标股票：

- 净买额 Top 3。
- 若日报 Top 板块前排股出现在龙虎榜，则优先加入。
- 最多请求 5 只股票，控制接口调用量。

3. 请求买卖席位：

```text
reportName=RPT_BILLBOARD_DAILYDETAILSBUY
filter=(TRADE_DATE='YYYY-MM-DD')(SECURITY_CODE="002156")
sortColumns=BUY
sortTypes=-1
pageSize=10
```

```text
reportName=RPT_BILLBOARD_DAILYDETAILSSELL
filter=(TRADE_DATE='YYYY-MM-DD')(SECURITY_CODE="002156")
sortColumns=SELL
sortTypes=-1
pageSize=10
```

请求策略：

- 单次报告最多 1 次全市场请求 + 10 次席位请求。
- 每次请求之间至少间隔约 1 秒。
- 席位明细失败不影响全市场龙虎榜摘要。
- 全市场请求失败时 provider 状态为 failed，但不阻断日报生成。

## 数据模型

新增日报字段建议：

```text
ReportDTO.dragon_tiger: DragonTigerSummary | None
```

核心模型：

```text
DragonTigerSummary
- trade_date
- source
- source_url
- status
- reason
- total_records
- positive_net_count
- negative_net_count
- net_buy_total_wan
- top_net_buy
- top_net_sell
- highlighted_stocks
- institution_net_buy_wan
- connect_net_buy_wan
- mainline_match_count
- sentiment
- strength
- conclusion
- risk_notes
```

股票记录：

```text
DragonTigerStock
- code
- name
- reason
- close
- change_pct
- turnover_pct
- net_buy_wan
- buy_wan
- sell_wan
- seats_buy
- seats_sell
- tags
```

席位记录：

```text
DragonTigerSeat
- name
- buy_wan
- sell_wan
- net_wan
- role
```

`role` 规则：

- `institution`：席位名称包含 `机构专用`。
- `northbound`：席位名称包含 `沪股通专用` 或 `深股通专用`。
- `brokerage`：其他券商营业部。

## 情绪与强度规则

第一版不引入复杂机器学习，只使用可解释规则。

### 情绪温度

输出值：

- `strong`
- `medium`
- `weak`
- `unknown`

建议规则：

- `strong`：上榜数较多，净买入为正股票占比高，Top 净买额集中，且机构或股通席位净买为正。
- `medium`：有大额净买，但方向分散，或席位资金结构一般。
- `weak`：上榜数量少，净卖出集中在高位核心，或正净买比例偏低。
- `unknown`：接口失败或无数据。

### 攻击强度

输出值：

- `high`
- `normal`
- `low`
- `unknown`

建议维度：

1. 净买额 Top 5 合计。
2. 单股净买额是否超过 `1` 亿。
3. 大额净买股票数量。
4. 买入席位是否集中在机构或股通。
5. 榜上股票是否集中在日报强势板块。

### 主线匹配度

计算方式：

- 龙虎榜股票名称或代码命中 `report.sectors[*].top_stocks`。
- 龙虎榜上榜原因命中日报 Top 板块名称或别名。
- 龙虎榜股票出现在复盘辅助源 hot stocks。

输出：

- `mainline_match_count`
- `mainline_match_names`
- 对命中的板块追加资金确认说明。

## 日报渲染

新增模块位置：`市场状态与情绪` 之后，`昨日/周报预判验证` 之前。

模块标题：

```text
龙虎榜情绪确认
```

显示内容控制在 5 行以内：

1. 情绪温度与攻击强度。
2. 榜上净买额 Top 3。
3. 机构/股通参与情况。
4. 主线匹配方向。
5. 风险提示。

示例文案：

```text
龙虎榜情绪：强，净买额集中在通富微电、亨通光电、国机精工。
席位结构：机构/深股通参与核心股，说明资金攻击并非纯题材脉冲。
主线确认：榜上个股与半导体、CPO等强势方向重合，主线确认度较高。
风险：若次日前排高开低走且龙虎榜大额净买股转弱，说明分歧扩大。
```

渲染约束：

- 不展示超过 5 只股票。
- 不展示完整席位长表。
- 不把席位名称堆成大段文字。
- 接口失败时展示“龙虎榜数据未取得”，但不写成“证据不足导致全部失败”。

## 结构化复盘接入

`StructuredReviewDTO.market_overview`：

- `emotion_rows` 增加龙虎榜行。
- `capital_flow_summary` 可引用龙虎榜结论。

`SectorDeepDive.capital_evidence`：

- 若板块命中龙虎榜主线，增加一条资金确认证据。
- 若高位核心出现在净卖出榜，增加风险说明。

`sustainability_ranking`：

- 龙虎榜强且主线匹配时，允许提高持续性理由质量。
- 龙虎榜弱或主线不匹配时，不因单纯板块涨幅高而给过强结论。

## 次日观察接入

`next_day_predictions` 增加龙虎榜因子：

加分：

- 主线前排出现在净买额 Top。
- 机构或股通席位净买为正。
- 龙虎榜净买额和板块涨幅方向一致。

扣分：

- 主线前排出现在净卖出 Top。
- 榜上净买方向分散，与日报 Top 板块不匹配。
- 个股高换手涨停但席位净买弱，提示次日分歧。

输出文案需要明确“观察条件”，而不是给绝对结论。

## 后台数据源选项

在 `review_sources` 增加：

```text
key: a_stock_dragon_tiger
label: a-stock 东财龙虎榜
role: 增强源 · 龙虎榜情绪资金
requires_key: false
experimental: false
```

默认策略：

- 第一版默认不强制开启。
- 部署后可在后台打开。
- 若开启后接口失败，质量门给 warning，不阻断报告。

## 质量门与状态

Provider status 至少包含：

```text
source
status
reason
record_count
seat_detail_count
```

质量门规则：

- 龙虎榜源关闭：不扣分。
- 龙虎榜源开启但失败：warning。
- 全市场成功但席位明细失败：warning，不阻断。
- 龙虎榜数据为空：在交易日盘后视为 warning；非交易日或午间报告视为 informational。

## 测试计划

### Provider 单测

- 全市场龙虎榜 payload 能映射为 `DragonTigerSummary`。
- 席位 payload 能识别 `机构专用`、`深股通专用`、普通营业部。
- `SECURITY_CODE` filter 使用双引号。
- 全市场成功、席位失败时仍返回摘要。
- 全市场失败时返回 failed status。

### 报告生成测试

- 启用 `a_stock_dragon_tiger` 后，`ReportDTO.dragon_tiger` 非空。
- `snapshot.json` 包含龙虎榜摘要和 provider status。
- 结构化复盘 `emotion_rows` 出现龙虎榜行。
- 次日预测 basis 中可出现龙虎榜依据。

### 渲染测试

- HTML 模板包含“龙虎榜情绪确认”。
- 成功数据渲染紧凑摘要。
- 失败数据渲染降级提示。
- 不出现完整席位长表。

### 端到端验证

使用 `2026-06-03` 生成盘后日报，预期：

- 龙虎榜记录数约 `91`。
- Top 净买包含 `通富微电`、`亨通光电`、`国机精工` 等东财返回样例。
- 日报中出现龙虎榜情绪模块。
- 主线持续性判断能引用龙虎榜证据。
- 现有 API 测试、日报生成测试、数据源后台测试通过。

## 实施顺序

1. 新增龙虎榜 schema 与 provider 单测。
2. 实现 `AStockDragonTigerProvider`。
3. 注册运行时数据源选项和 provider factory。
4. 将龙虎榜摘要写入 `ReportDTO`。
5. 接入结构化复盘和次日预测。
6. 更新 HTML 渲染。
7. 更新质量门和 provider status。
8. 本地生成样例日报验证。

## 风险与处理

- 东财接口字段变动：provider 解析保持容错，缺字段时降级为部分摘要。
- 请求频率限制：严格串行，限制席位明细股票数量。
- 正文变长：渲染层限制最多 5 行摘要。
- 误把龙虎榜当作强结论：规则层只作为确认或风险证据，不覆盖行情和板块排名主判断。
- 午间报告数据缺失：午间可显示未更新，不视为失败。
