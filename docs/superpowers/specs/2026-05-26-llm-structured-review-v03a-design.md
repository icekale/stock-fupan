# v0.3a LLM 结构化复盘生成设计

日期：2026-05-26  
状态：用户已确认，待实施计划  
前置版本：v0.2b 结构化 HTML 长文已完成

## 1. 背景与目标

v0.2b 已经建立 `StructuredReviewDTO`、规则 builder 和结构化 HTML 模板。当前报告形态已经接近参考 HTML，但结构化复盘内容仍主要来自确定性规则，表达较机械。

v0.3a 的目标是让 LLM 负责生成更像交易员复盘的结构化判断，同时保留规则 builder 作为稳定兜底。系统必须做到：有 key 和配置时尝试 LLM；LLM 失败、输出不合规、空 key 或网络错误时自动回退规则 builder；整个报告链路继续可离线、可测试、可复现。

## 2. 范围

本阶段实现：

1. 新增 LLM 配置开关：`LLM_PROVIDER`、`STRUCTURED_REVIEW_PROVIDER`、`STRUCTURED_REVIEW_FALLBACK_ENABLED`。
2. 扩展 `LLMProvider` 协议，支持 `generate_structured_review(seed)`。
3. 新增 OpenAI 兼容 provider，使用现有 `OPENAI_API_KEY`、`OPENAI_BASE_URL`、`LLM_MODEL`。
4. 新增结构化 prompt/seed 生成器，只允许 LLM 基于结构化事实生成 `StructuredReviewDTO`。
5. 增加 Pydantic 校验和 fallback 状态记录。
6. `llm_calls.json` 记录 narrative 与 structured review 调用元数据，但不记录任何 API key。
7. `snapshot.json` 增加 `structured_review_status`，显示 `llm_success` / `fallback_rule` / `validation_failed` 等原因。
8. 保持 fake provider 和无 key 环境下全量测试可通过。

## 3. 非目标

- 不接 TickFlow、同花顺自选股、OCR；这些进入下一阶段。
- 不做前一日报告自动对比；`PredictionReview.source` 仍可为 `manual_placeholder`。
- 不新增用户界面的 prompt 编辑器。
- 不把 LLM 输出绕过事实校验直接写入报告。
- 不在仓库、测试、文档中写入任何真实 API key。

## 4. 配置设计

新增配置字段：

```dotenv
LLM_PROVIDER=fake
STRUCTURED_REVIEW_PROVIDER=rule
STRUCTURED_REVIEW_FALLBACK_ENABLED=true
```

含义：

- `LLM_PROVIDER=fake | openai`
  - 控制 `llm_provider` 工厂创建 fake 或 OpenAI provider。
- `STRUCTURED_REVIEW_PROVIDER=rule | llm`
  - `rule`: 使用当前 deterministic builder。
  - `llm`: 先调用 `llm_provider.generate_structured_review(seed)`，失败时按配置回退。
- `STRUCTURED_REVIEW_FALLBACK_ENABLED=true | false`
  - true: LLM 失败自动回退规则 builder。
  - false: LLM 失败直接抛错，用于严格测试。

默认值必须保持本地稳定：`LLM_PROVIDER=fake`、`STRUCTURED_REVIEW_PROVIDER=rule`。

## 5. Provider 设计

`LLMProvider` 协议新增：

```python
def generate_structured_review(self, seed: dict[str, object]) -> StructuredReviewDTO:
    raise NotImplementedError
```

`FakeLLMProvider`：

- 继续返回现有 deterministic narrative。
- 新增 `generate_structured_review`，内部可复用规则 builder 或返回固定合规结构。
- 测试环境默认不走网络。

`OpenAILLMProvider`：

- 使用 `openai.OpenAI(api_key=..., base_url=...)`。
- 通过 Responses API 或 SDK 可用接口请求模型输出 JSON。
- 输出必须解析为 `StructuredReviewDTO`。
- 不把 API key 写入错误信息或日志。
- 请求失败、JSON 解析失败、Pydantic 校验失败统一抛 `LLMFallbackError`。

> 实施时优先检查本地安装的 `openai` SDK 能力；若 Responses API 的 structured output 用法不确定，使用 Chat Completions JSON object fallback，但必须保留 Pydantic 校验。

## 6. Orchestration 设计

新增服务 `StructuredReviewGenerator`：

输入：

- `report: ReportDTO`
- `llm_provider: LLMProvider`
- `provider_mode: rule | llm`
- `fallback_enabled: bool`

输出：

- `review: StructuredReviewDTO`
- `status: StructuredReviewStatus`

`StructuredReviewStatus` 字段：

- `provider`: `rule` / `llm`
- `status`: `success` / `fallback` / `failed`
- `fallback_used`: bool
- `reason`: string | None

生成规则：

1. mode 为 `rule`：直接调用当前 `build_structured_review(report)`，状态为 `provider=rule, status=success`。
2. mode 为 `llm`：构造结构化 seed，调用 `llm_provider.generate_structured_review(seed)`。
3. LLM 成功：状态为 `provider=llm, status=success`。
4. LLM 失败且 fallback enabled：调用规则 builder，状态为 `provider=llm, status=fallback` 并记录脱敏原因。
5. LLM 失败且 fallback disabled：抛出异常。

## 7. Seed 与事实边界

LLM seed 必须只包含结构化事实，不包含 API key 或内部路径：

- `trade_date`
- `indices`
- `breadth`
- `turnover_cny`
- `market_state_tags`
- `sectors`
  - name, rank, score, pct_change, factor_scores, news_summaries
- `news`
  - title, source, summary, matched_sector, published_at
- `narrative`
  - conclusion, overview, watchlist, tomorrow, risks

Prompt 必须明确：

- 不得编造未提供的数字、板块、个股、新闻来源。
- 没有前一日报告时，`prediction_review.source` 必须为 `manual_placeholder`。
- 输出必须是 `StructuredReviewDTO` JSON。
- 买卖建议必须改写为观察条件、风险分层、回避清单。

## 8. 资产与 API 输出

`GeneratedReport` 增加：

```python
structured_review_status: dict[str, object]
```

`snapshot.json` 增加：

```json
"structured_review_status": {
  "provider": "llm",
  "status": "fallback",
  "fallback_used": true,
  "reason": "OPENAI_API_KEY 未配置"
}
```

`llm_calls.json` 对 structured review 增加一条记录：

- provider
- model
- prompt: `structured-review-json`
- parameters: 不含 key
- output: 成功时为结构化 JSON；fallback 时可以记录 `{}` 或规则结果
- validation_errors

## 9. 测试策略

必须使用 TDD。测试不走真实网络。

核心测试：

- `FakeLLMProvider.generate_structured_review` 返回合规 DTO。
- `OpenAILLMProvider` 能用 injected fake client 将 JSON 映射为 `StructuredReviewDTO`。
- OpenAI provider 缺 key 时抛出脱敏 fallback error。
- OpenAI provider 错误不泄露 key。
- `StructuredReviewGenerator` 在 `rule` 模式返回规则状态。
- `StructuredReviewGenerator` 在 `llm` 模式成功返回 LLM 状态。
- `StructuredReviewGenerator` 在 LLM 失败时 fallback 到规则 builder。
- `ReportGenerator` 将 `structured_review_status` 写入 snapshot。
- `.env.example` 和 README 文档说明新增配置。
- 全量后端/前端验证通过。

## 10. 验收标准

完成后：

- 默认无 key 环境继续稳定生成报告。
- 设置 `STRUCTURED_REVIEW_PROVIDER=llm` 且无 key 时，前端/API 不崩，snapshot 显示 fallback 原因。
- 使用 fake client 单测可覆盖 LLM 成功路径。
- 真实 key 只允许本地 smoke 使用环境变量注入，不写入仓库。
- `report.html` 仍渲染 v0.2b 的结构化长文，但内容来源可由 LLM 提供。
- `uv run pytest -v`、`uv run ruff check .`、前端 typecheck/lint 全部通过。
