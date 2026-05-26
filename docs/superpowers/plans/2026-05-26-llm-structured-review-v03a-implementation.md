# v0.3a LLM Structured Review Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate `StructuredReviewDTO` with an LLM when configured, while preserving deterministic rule fallback and offline testability.

**Architecture:** Extend the existing LLM provider boundary with structured-review generation, add an OpenAI-compatible provider with injected-client tests, and introduce a small orchestration service that selects rule vs LLM and records status. Keep report rendering unchanged: HTML consumes `report.structured_review` no matter whether it came from rules or LLM.

**Tech Stack:** Python 3.12, OpenAI Python SDK, Pydantic v2, FastAPI, pytest, ruff, Next.js, TypeScript, pnpm, uv.

---

## File Structure

Create or modify these files:

```text
apps/api/app/config.py                         # add LLM/structured review settings
apps/api/app/providers/factory.py              # create configured LLM provider
apps/api/app/providers/llm.py                  # extend protocol, fake/openai provider, fallback errors
apps/api/app/services/structured_review_builder.py # add seed builder reusable by LLM
apps/api/app/services/structured_review_generator.py # select rule/LLM/fallback and status
apps/api/app/services/report_generator.py      # use generator and persist status/call metadata
apps/api/tests/test_llm_provider.py            # provider unit tests
apps/api/tests/test_structured_review.py       # generator/status tests
apps/api/tests/test_report_api.py              # snapshot + llm_calls assertions
.env.example                                   # document local config knobs
README.md                                      # document LLM structured review mode
```

---

### Task 1: Add LLM Settings and Factory Wiring

**Files:**
- Modify: `apps/api/app/config.py`
- Modify: `apps/api/app/providers/factory.py`
- Modify: `apps/api/tests/test_real_providers.py`

- [ ] **Step 1: Add failing settings/factory tests**

Append to `apps/api/tests/test_real_providers.py`:

```python
from app.providers.llm import OpenAILLMProvider


def test_settings_default_to_rule_structured_review() -> None:
    settings = Settings()

    assert settings.llm_provider == "fake"
    assert settings.structured_review_provider == "rule"
    assert settings.structured_review_fallback_enabled is True


def test_provider_factory_can_create_openai_llm_provider() -> None:
    settings = Settings(
        llm_provider="openai",
        openai_api_key="sk-test-local",
        openai_base_url="https://api.openai.com/v1",
        llm_model="gpt-4.1-mini",
    )

    bundle = create_provider_bundle(settings)

    assert isinstance(bundle.llm_provider, OpenAILLMProvider)
    assert bundle.llm_provider.model_name == "gpt-4.1-mini"
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
cd apps/api
uv run pytest tests/test_real_providers.py::test_settings_default_to_rule_structured_review tests/test_real_providers.py::test_provider_factory_can_create_openai_llm_provider -v
```

Expected: FAIL because settings and `OpenAILLMProvider` do not exist yet.

- [ ] **Step 3: Add config fields**

Modify `apps/api/app/config.py` in `Settings` after `llm_model`:

```python
    llm_provider: str = "fake"
    structured_review_provider: str = "rule"
    structured_review_fallback_enabled: bool = True
```

- [ ] **Step 4: Add OpenAILLMProvider shell and factory wiring**

Modify `apps/api/app/providers/llm.py` imports:

```python
from app.schemas.structured_review import StructuredReviewDTO
```

Add to `LLMProvider` protocol:

```python
    def generate_structured_review(self, seed: dict[str, object]) -> StructuredReviewDTO:
        raise NotImplementedError
```

Add to `FakeLLMProvider` for now:

```python
    def generate_structured_review(self, seed: dict[str, object]) -> StructuredReviewDTO:
        from app.services.structured_review_builder import build_structured_review_from_seed

        return build_structured_review_from_seed(seed)
```

Add `OpenAILLMProvider` shell:

```python
class LLMFallbackError(RuntimeError):
    pass


class OpenAILLMProvider:
    provider_name = "openai"

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model_name: str,
        client: object | None = None,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url
        self.model_name = model_name
        self.client = client

    def generate_narrative(self, seed: dict[str, object]) -> ReportNarrative:
        return FakeLLMProvider().generate_narrative(seed)

    def generate_structured_review(self, seed: dict[str, object]) -> StructuredReviewDTO:
        raise LLMFallbackError("OpenAI structured review generation not implemented")
```

Modify `apps/api/app/providers/factory.py` imports:

```python
from app.providers.llm import FakeLLMProvider, LLMProvider, OpenAILLMProvider
```

Change `create_provider_bundle` LLM provider:

```python
        llm_provider=_create_llm_provider(settings),
```

Add helper:

```python
def _create_llm_provider(settings: Settings) -> LLMProvider:
    if settings.llm_provider == "fake":
        return FakeLLMProvider()
    if settings.llm_provider == "openai":
        return OpenAILLMProvider(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            model_name=settings.llm_model,
        )
    raise ValueError(f"Unsupported LLM_PROVIDER: {settings.llm_provider}")
```

- [ ] **Step 5: Add seed-to-report helper for fake provider**

Modify `apps/api/app/services/structured_review_builder.py` imports:

```python
from app.schemas.report import IndexSnapshot, MarketBreadth, ReportNarrative, ReportKind
```

Add helper at bottom:

```python
def build_structured_review_from_seed(seed: dict[str, object]) -> StructuredReviewDTO:
    report = ReportDTO(
        trade_date=str(seed.get("trade_date") or "unknown"),
        kind=ReportKind.CLOSE,
        title=f"{seed.get('trade_date') or 'unknown'} A股复盘",
        indices=[IndexSnapshot.model_validate(item) for item in seed.get("indices", [])],
        breadth=MarketBreadth.model_validate(seed.get("breadth", {})),
        turnover_cny=float(seed.get("turnover_cny") or 0),
        market_state_tags=[str(item) for item in seed.get("market_state_tags", [])],
        sectors=[],
        narrative=ReportNarrative(
            conclusion="",
            overview="",
            sector_commentary=[],
            watchlist=[],
            tomorrow="",
            risks=[],
        ),
        news=[],
    )
    return build_structured_review(report)
```

- [ ] **Step 6: Run settings/factory tests**

Run:

```bash
cd apps/api
uv run pytest tests/test_real_providers.py::test_settings_default_to_rule_structured_review tests/test_real_providers.py::test_provider_factory_can_create_openai_llm_provider -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add apps/api/app/config.py apps/api/app/providers/factory.py apps/api/app/providers/llm.py apps/api/app/services/structured_review_builder.py apps/api/tests/test_real_providers.py
git commit -m "feat: configure llm structured review providers"
```

---

### Task 2: Implement OpenAI Structured Review Provider

**Files:**
- Modify: `apps/api/app/providers/llm.py`
- Create: `apps/api/tests/test_llm_provider.py`

- [ ] **Step 1: Write provider mapping and error tests**

Create `apps/api/tests/test_llm_provider.py`:

```python
import json

import pytest

from app.providers.llm import LLMFallbackError, OpenAILLMProvider


class FakeMessage:
    def __init__(self, content: str) -> None:
        self.content = content


class FakeChoice:
    def __init__(self, content: str) -> None:
        self.message = FakeMessage(content)


class FakeCompletion:
    def __init__(self, content: str) -> None:
        self.choices = [FakeChoice(content)]


class FakeCompletions:
    def __init__(self, content: str | None = None, error: Exception | None = None) -> None:
        self.content = content
        self.error = error
        self.last_kwargs: dict[str, object] = {}

    def create(self, **kwargs: object) -> FakeCompletion:
        self.last_kwargs = kwargs
        if self.error is not None:
            raise self.error
        if self.content is None:
            raise RuntimeError("missing fake content")
        return FakeCompletion(self.content)


class FakeChat:
    def __init__(self, completions: FakeCompletions) -> None:
        self.completions = completions


class FakeClient:
    def __init__(self, completions: FakeCompletions) -> None:
        self.chat = FakeChat(completions)


def _valid_structured_payload() -> dict[str, object]:
    return {
        "topic": "科技内部淘汰赛 · 主线换挡日",
        "prediction_review": {
            "previous_prediction": "昨日预判机器人方向有分歧承接。",
            "actual_result": "机器人方向继续领涨。",
            "correct_items": ["机器人延续强势"],
            "missed_items": ["PCB强度略超预期"],
            "revision": "继续观察科技内部轮动。",
            "source": "manual_placeholder",
        },
        "tomorrow_judgement": {
            "most_likely_to_continue": "机器人",
            "most_likely_to_diverge": "PCB",
            "rotation_candidates": ["PCB"],
            "defensive_candidates": ["高股息"],
            "core_view": "科技内部去弱留强。",
        },
        "market_overview": {
            "index_rows": [{"name": "上证指数", "close": "3100.50", "change": "+1.20%"}],
            "emotion_rows": [{"label": "涨停 / 跌停", "value": "86 / 8"}],
            "structure_features": ["放量", "分化"],
            "capital_flow_summary": "资金在科技方向内部切换。",
        },
        "sector_reviews": [
            {
                "sector": "机器人",
                "headline": "机器人：主线承接仍强",
                "stage": "主升延续",
                "strengths": ["涨幅居前"],
                "weaknesses": ["高位分歧"],
                "logic": "短线强度和消息催化共振。",
                "sustainability": "high",
                "next_day_view": "观察核心股承接。",
                "watch_items": ["回踩承接"],
                "avoid_items": ["缩量冲高"],
            }
        ],
        "sustainability_ranking": [
            {"rank": 1, "sector": "机器人", "rating": "high", "reason": "强度领先"}
        ],
        "action_discipline": {
            "focus": ["观察机器人核心方向"],
            "avoid": ["回避跟风补涨"],
            "final_view": "围绕机器人去弱留强。",
        },
    }


def test_openai_llm_provider_maps_json_to_structured_review() -> None:
    completions = FakeCompletions(json.dumps(_valid_structured_payload(), ensure_ascii=False))
    provider = OpenAILLMProvider(
        api_key="sk-test-local",
        base_url="https://api.openai.com/v1",
        model_name="gpt-4.1-mini",
        client=FakeClient(completions),
    )

    review = provider.generate_structured_review({"trade_date": "2026-05-26"})

    assert review.topic == "科技内部淘汰赛 · 主线换挡日"
    assert review.sector_reviews[0].sector == "机器人"
    assert completions.last_kwargs["model"] == "gpt-4.1-mini"
    assert completions.last_kwargs["response_format"] == {"type": "json_object"}


def test_openai_llm_provider_rejects_missing_key() -> None:
    provider = OpenAILLMProvider(api_key="", base_url="https://api.openai.com/v1", model_name="gpt-4.1-mini")

    with pytest.raises(LLMFallbackError, match="OPENAI_API_KEY"):
        provider.generate_structured_review({"trade_date": "2026-05-26"})


def test_openai_llm_provider_sanitizes_errors() -> None:
    leaked_key = "sk-secret-leak"
    provider = OpenAILLMProvider(
        api_key=leaked_key,
        base_url="https://api.openai.com/v1",
        model_name="gpt-4.1-mini",
        client=FakeClient(FakeCompletions(error=RuntimeError(f"boom {leaked_key}"))),
    )

    with pytest.raises(LLMFallbackError) as exc_info:
        provider.generate_structured_review({"trade_date": "2026-05-26"})

    message = str(exc_info.value)
    assert "OpenAI 请求失败" in message
    assert leaked_key not in message
```

- [ ] **Step 2: Run provider tests to verify failure**

Run:

```bash
cd apps/api
uv run pytest tests/test_llm_provider.py -v
```

Expected: FAIL because `OpenAILLMProvider.generate_structured_review` is not implemented.

- [ ] **Step 3: Implement provider with JSON-object Chat Completions**

Modify `apps/api/app/providers/llm.py`:

```python
import json
from typing import Any, Protocol

from openai import OpenAI
from pydantic import ValidationError

from app.schemas.structured_review import StructuredReviewDTO
```

Add helper constants/functions:

```python
STRUCTURED_REVIEW_SYSTEM_PROMPT = """你是A股盘后复盘助手。只基于用户提供的结构化事实生成 JSON。
不得编造未提供的数字、板块、个股、新闻来源。
没有前一日报告时 prediction_review.source 必须为 manual_placeholder。
所有买卖建议必须改写为观察条件、风险分层、回避清单。
输出必须是合法 JSON，且字段匹配 StructuredReviewDTO。"""


def _safe_error(prefix: str, exc: Exception) -> str:
    return f"{prefix}: {exc.__class__.__name__}"
```

Replace `OpenAILLMProvider.generate_structured_review`:

```python
    def generate_structured_review(self, seed: dict[str, object]) -> StructuredReviewDTO:
        if not self.api_key:
            raise LLMFallbackError("OPENAI_API_KEY 未配置")

        client = self.client or OpenAI(api_key=self.api_key, base_url=self.base_url)
        try:
            completion = client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": STRUCTURED_REVIEW_SYSTEM_PROMPT},
                    {"role": "user", "content": json.dumps(seed, ensure_ascii=False)},
                ],
                response_format={"type": "json_object"},
                temperature=0.2,
            )
            content = completion.choices[0].message.content
        except Exception as exc:
            raise LLMFallbackError(_safe_error("OpenAI 请求失败", exc)) from exc

        if not content:
            raise LLMFallbackError("OpenAI 返回空内容")
        try:
            payload = json.loads(content)
        except json.JSONDecodeError as exc:
            raise LLMFallbackError("OpenAI JSON 解析失败") from exc
        try:
            return StructuredReviewDTO.model_validate(payload)
        except ValidationError as exc:
            raise LLMFallbackError("OpenAI 结构化复盘字段校验失败") from exc
```

- [ ] **Step 4: Run provider tests**

Run:

```bash
cd apps/api
uv run pytest tests/test_llm_provider.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/providers/llm.py apps/api/tests/test_llm_provider.py
git commit -m "feat: add openai structured review provider"
```

---

### Task 3: Add Structured Review Generator Orchestration

**Files:**
- Create: `apps/api/app/services/structured_review_generator.py`
- Modify: `apps/api/tests/test_structured_review.py`

- [ ] **Step 1: Append generator status tests**

Append to `apps/api/tests/test_structured_review.py`:

```python
import pytest

from app.providers.llm import LLMFallbackError
from app.services.structured_review_generator import generate_structured_review


class SuccessfulStructuredLLM:
    provider_name = "openai"

    def generate_structured_review(self, seed: dict[str, object]):
        review = build_structured_review(_fake_report())
        review.topic = "LLM生成 · 科技内部复盘"
        return review


class BrokenStructuredLLM:
    provider_name = "openai"

    def generate_structured_review(self, seed: dict[str, object]):
        raise LLMFallbackError("OPENAI_API_KEY 未配置")


def test_structured_review_generator_rule_mode_returns_rule_status() -> None:
    report = _fake_report()

    review, status = generate_structured_review(
        report=report,
        llm_provider=BrokenStructuredLLM(),
        provider_mode="rule",
        fallback_enabled=True,
    )

    assert review.topic == "放量分化 · 机器人领涨 · PCB轮动"
    assert status.model_dump(mode="json") == {
        "provider": "rule",
        "status": "success",
        "fallback_used": False,
        "reason": None,
    }


def test_structured_review_generator_llm_mode_uses_llm_on_success() -> None:
    report = _fake_report()

    review, status = generate_structured_review(
        report=report,
        llm_provider=SuccessfulStructuredLLM(),
        provider_mode="llm",
        fallback_enabled=True,
    )

    assert review.topic == "LLM生成 · 科技内部复盘"
    assert status.provider == "llm"
    assert status.status == "success"
    assert status.fallback_used is False


def test_structured_review_generator_falls_back_to_rule_on_llm_failure() -> None:
    report = _fake_report()

    review, status = generate_structured_review(
        report=report,
        llm_provider=BrokenStructuredLLM(),
        provider_mode="llm",
        fallback_enabled=True,
    )

    assert review.topic == "放量分化 · 机器人领涨 · PCB轮动"
    assert status.provider == "llm"
    assert status.status == "fallback"
    assert status.fallback_used is True
    assert status.reason == "OPENAI_API_KEY 未配置"


def test_structured_review_generator_can_raise_when_fallback_disabled() -> None:
    report = _fake_report()

    with pytest.raises(LLMFallbackError, match="OPENAI_API_KEY"):
        generate_structured_review(
            report=report,
            llm_provider=BrokenStructuredLLM(),
            provider_mode="llm",
            fallback_enabled=False,
        )
```

- [ ] **Step 2: Run generator tests to verify failure**

Run:

```bash
cd apps/api
uv run pytest tests/test_structured_review.py::test_structured_review_generator_rule_mode_returns_rule_status tests/test_structured_review.py::test_structured_review_generator_llm_mode_uses_llm_on_success tests/test_structured_review.py::test_structured_review_generator_falls_back_to_rule_on_llm_failure tests/test_structured_review.py::test_structured_review_generator_can_raise_when_fallback_disabled -v
```

Expected: FAIL because service does not exist.

- [ ] **Step 3: Implement structured review generator**

Create `apps/api/app/services/structured_review_generator.py`:

```python
from typing import Literal

from pydantic import BaseModel

from app.providers.llm import LLMProvider
from app.schemas.report import ReportDTO
from app.schemas.structured_review import StructuredReviewDTO
from app.services.structured_review_builder import build_structured_review, build_structured_review_seed

StructuredReviewProviderMode = Literal["rule", "llm"]
StructuredReviewState = Literal["success", "fallback", "failed"]


class StructuredReviewStatus(BaseModel):
    provider: str
    status: StructuredReviewState
    fallback_used: bool = False
    reason: str | None = None


def generate_structured_review(
    report: ReportDTO,
    llm_provider: LLMProvider,
    provider_mode: StructuredReviewProviderMode,
    fallback_enabled: bool,
) -> tuple[StructuredReviewDTO, StructuredReviewStatus]:
    if provider_mode == "rule":
        return build_structured_review(report), StructuredReviewStatus(
            provider="rule",
            status="success",
            fallback_used=False,
            reason=None,
        )
    if provider_mode != "llm":
        raise ValueError(f"Unsupported STRUCTURED_REVIEW_PROVIDER: {provider_mode}")

    try:
        review = llm_provider.generate_structured_review(build_structured_review_seed(report))
    except Exception as exc:
        reason = str(exc) or exc.__class__.__name__
        if not fallback_enabled:
            raise
        return build_structured_review(report), StructuredReviewStatus(
            provider="llm",
            status="fallback",
            fallback_used=True,
            reason=reason,
        )

    return review, StructuredReviewStatus(
        provider="llm",
        status="success",
        fallback_used=False,
        reason=None,
    )
```

- [ ] **Step 4: Add seed builder**

Modify `apps/api/app/services/structured_review_builder.py` add before `build_structured_review_from_seed`:

```python
def build_structured_review_seed(report: ReportDTO) -> dict[str, object]:
    return {
        "trade_date": report.trade_date,
        "indices": [index.model_dump(mode="json") for index in report.indices],
        "breadth": report.breadth.model_dump(mode="json"),
        "turnover_cny": report.turnover_cny,
        "market_state_tags": report.market_state_tags,
        "sectors": [
            {
                "name": sector.name,
                "rank": sector.rank,
                "score": sector.score,
                "pct_change": sector.pct_change,
                "factor_scores": sector.factor_scores,
                "news_summaries": sector.news_summaries,
            }
            for sector in report.sectors
        ],
        "news": [item.model_dump(mode="json") for item in report.news],
        "narrative": report.narrative.model_dump(mode="json"),
    }
```

- [ ] **Step 5: Run structured review tests**

Run:

```bash
cd apps/api
uv run pytest tests/test_structured_review.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/api/app/services/structured_review_generator.py apps/api/app/services/structured_review_builder.py apps/api/tests/test_structured_review.py
git commit -m "feat: orchestrate structured review llm fallback"
```

---

### Task 4: Thread LLM Structured Status Through ReportGenerator

**Files:**
- Modify: `apps/api/app/services/report_generator.py`
- Modify: `apps/api/app/main.py`
- Modify: `apps/api/tests/test_report_api.py`

- [ ] **Step 1: Add report generator snapshot status test**

Append to `apps/api/tests/test_report_api.py`:

```python
from app.providers.llm import LLMFallbackError


class BrokenStructuredReviewLLM(FakeLLMProvider):
    provider_name = "openai"

    def generate_structured_review(self, seed: dict[str, object]):
        raise LLMFallbackError("OPENAI_API_KEY 未配置")


def test_report_generator_writes_structured_review_status_on_llm_fallback(tmp_path: Path) -> None:
    generator = ReportGenerator(
        reports_root=tmp_path,
        market_provider=FakeMarketDataProvider(),
        news_provider=FakeNewsProvider(),
        llm_provider=BrokenStructuredReviewLLM(),
        structured_review_provider="llm",
        structured_review_fallback_enabled=True,
    )

    result = generator.generate_close_report("2026-05-26")

    assert result.structured_review_status == {
        "provider": "llm",
        "status": "fallback",
        "fallback_used": True,
        "reason": "OPENAI_API_KEY 未配置",
    }
    snapshot = json.loads(result.assets.snapshot.read_text(encoding="utf-8"))
    assert snapshot["structured_review_status"] == result.structured_review_status
```

- [ ] **Step 2: Run test to verify failure**

Run:

```bash
cd apps/api
uv run pytest tests/test_report_api.py::test_report_generator_writes_structured_review_status_on_llm_fallback -v
```

Expected: FAIL because `ReportGenerator` does not accept structured review config/status.

- [ ] **Step 3: Update GeneratedReport and ReportGenerator constructor**

Modify `apps/api/app/services/report_generator.py` imports:

```python
from app.services.structured_review_generator import generate_structured_review
```

Update dataclass:

```python
    structured_review_status: dict[str, object]
```

Update `ReportGenerator.__init__` signature:

```python
        structured_review_provider: str = "rule",
        structured_review_fallback_enabled: bool = True,
```

Set fields:

```python
        self.structured_review_provider = structured_review_provider
        self.structured_review_fallback_enabled = structured_review_fallback_enabled
```

Replace:

```python
        report.structured_review = build_structured_review(report)
```

with:

```python
        structured_review, structured_review_status = generate_structured_review(
            report=report,
            llm_provider=self.llm_provider,
            provider_mode=self.structured_review_provider,
            fallback_enabled=self.structured_review_fallback_enabled,
        )
        report.structured_review = structured_review
```

Add snapshot field:

```python
                "structured_review_status": structured_review_status.model_dump(mode="json"),
```

Add `llm_calls` second item after narrative call:

```python
                {
                    "provider": _provider_metadata(self.llm_provider, "provider_name"),
                    "model": _provider_metadata(self.llm_provider, "model_name"),
                    "prompt": "structured-review-json",
                    "parameters": {"provider_mode": self.structured_review_provider},
                    "output": report.structured_review.model_dump(mode="json") if report.structured_review else {},
                    "validation_errors": [],
                },
```

Update return:

```python
            structured_review_status=structured_review_status.model_dump(mode="json"),
```

- [ ] **Step 4: Update API construction**

Modify `apps/api/app/main.py` ReportGenerator construction:

```python
            structured_review_provider=settings.structured_review_provider,
            structured_review_fallback_enabled=settings.structured_review_fallback_enabled,
```

- [ ] **Step 5: Run report tests**

Run:

```bash
cd apps/api
uv run pytest tests/test_report_api.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/api/app/services/report_generator.py apps/api/app/main.py apps/api/tests/test_report_api.py
git commit -m "feat: persist structured review generation status"
```

---

### Task 5: Documentation and Environment Defaults

**Files:**
- Modify: `.env.example`
- Modify: `README.md`

- [ ] **Step 1: Update `.env.example`**

Add after `LLM_MODEL`:

```dotenv
LLM_PROVIDER=fake
STRUCTURED_REVIEW_PROVIDER=rule
STRUCTURED_REVIEW_FALLBACK_ENABLED=true
```

- [ ] **Step 2: Update README**

Add after `Real Data Providers` section:

```markdown
## LLM Structured Review

v0.3a can use an OpenAI-compatible LLM to generate `structured_review` content for the long-form HTML report:

```dotenv
LLM_PROVIDER=openai
STRUCTURED_REVIEW_PROVIDER=llm
STRUCTURED_REVIEW_FALLBACK_ENABLED=true
OPENAI_API_KEY=
OPENAI_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4.1-mini
```

Behavior:

- Default local mode remains `LLM_PROVIDER=fake` and `STRUCTURED_REVIEW_PROVIDER=rule`.
- LLM output is parsed into `StructuredReviewDTO`; invalid JSON or schema failures fall back to the deterministic rule builder when fallback is enabled.
- `snapshot.json` includes `structured_review_status` so the frontend and generated assets can explain whether the review came from rules, LLM, or fallback.
- API keys must be supplied through local environment variables only and are never written to generated assets.
```

- [ ] **Step 3: Run docs diff check**

Run:

```bash
git diff -- .env.example README.md
```

Expected: new LLM config documented, no keys.

- [ ] **Step 4: Commit**

```bash
git add .env.example README.md
git commit -m "docs: document llm structured review mode"
```

---

### Task 6: Full Verification and Fallback Smoke

**Files:**
- No production file changes expected.

- [ ] **Step 1: Run backend checks**

Run:

```bash
cd apps/api
uv run pytest -v
uv run ruff check .
```

Expected: PASS.

- [ ] **Step 2: Run frontend checks**

Run:

```bash
corepack pnpm --filter @stock-review/web test
corepack pnpm --filter @stock-review/web lint
```

Expected: PASS.

- [ ] **Step 3: Run no-key LLM fallback smoke**

Run:

```bash
cd apps/api
MARKET_PROVIDER=fake NEWS_PROVIDER=fake LLM_PROVIDER=openai STRUCTURED_REVIEW_PROVIDER=llm OPENAI_API_KEY= REPORTS_ROOT=/tmp/stock-review-v03a-smoke uv run python - <<'PY'
from fastapi.testclient import TestClient
from app.config import get_settings
from app.main import app

get_settings.cache_clear()
with TestClient(app) as client:
    response = client.post('/api/reports/close', json={'trade_date': '2026-05-26'})
response.raise_for_status()
payload = response.json()
print(payload['assets']['html'])
print(payload['report']['structured_review']['topic'])
assert payload['report']['structured_review']['prediction_review']['source'] == 'manual_placeholder'
PY
```

Then inspect snapshot:

```bash
SNAPSHOT_PATH=$(find /tmp/stock-review-v03a-smoke -name snapshot.json | sort | tail -1)
python - <<'PY'
import json
import os
from pathlib import Path
snapshot = json.loads(Path(os.environ['SNAPSHOT_PATH']).read_text(encoding='utf-8'))
print(snapshot['structured_review_status'])
assert snapshot['structured_review_status']['status'] == 'fallback'
assert snapshot['structured_review_status']['reason'] == 'OPENAI_API_KEY 未配置'
PY
```

Expected: fallback succeeds and reason is visible.

- [ ] **Step 4: Ensure worktree clean**

Run:

```bash
git status --short
```

Expected: no tracked changes.

---

## Self-Review

Spec coverage:

- LLM config, provider, seed, fallback, status, llm_calls, docs, and no-key smoke are covered.
- TickFlow/同花顺/OCR are explicitly out of scope for this phase.
- Real API keys are not written to tests, docs, or generated assets.

Placeholder scan:

- No `TBD`, `TODO`, or vague “add tests” placeholders remain.
- Every task has concrete tests, commands, expected outcomes, and commit commands.

Type consistency:

- `StructuredReviewStatus` uses the same `provider/status/fallback_used/reason` shape as existing provider diagnostics.
- `STRUCTURED_REVIEW_PROVIDER` values are consistently `rule | llm`.
- `LLM_PROVIDER` values are consistently `fake | openai`.
