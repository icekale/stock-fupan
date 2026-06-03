from __future__ import annotations

import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.providers.review_sources import (
    ReviewSourceResult,
    ReviewStockEvidence,
    ReviewThemeEvidence,
)


@dataclass(frozen=True)
class ThsdkProbeResult:
    provider: str
    status: str
    reason: str | None = None
    next_step: str | None = None
    started_at: str | None = None
    account: dict[str, bool] | None = None
    checks: list[dict[str, Any]] | None = None
    summary: dict[str, object] | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "provider": self.provider,
            "status": self.status,
        }
        for key in ("reason", "next_step", "started_at", "account", "checks", "summary"):
            value = getattr(self, key)
            if value is not None:
                payload[key] = value
        return payload


class ThsdkProvider:
    provider_name = "thsdk"
    source_name = "THSDK"
    source_url = "thsdk://local"

    def __init__(self, client_factory: Callable[[], Any] | None = None) -> None:
        self.client_factory = client_factory

    @classmethod
    def from_installed_package(cls) -> "ThsdkProvider":
        try:
            from thsdk import THS
        except ModuleNotFoundError:
            return cls(client_factory=None)
        return cls(client_factory=THS)

    def check_available(self) -> ThsdkProbeResult:
        if self.client_factory is None:
            return ThsdkProbeResult(
                provider=self.provider_name,
                status="unavailable",
                reason="THSDK 未安装",
                next_step="在本地或容器内执行 `uv add thsdk` 或 `pip install thsdk` 后重试。",
            )
        return ThsdkProbeResult(
            provider=self.provider_name,
            status="available",
            next_step="去掉 --skip-live 执行真实接口探测。",
        )

    def probe(self, keyword: str = "今日涨停", symbol: str = "300033") -> ThsdkProbeResult:
        if self.client_factory is None:
            return self.check_available()

        checks: list[dict[str, Any]] = []
        started_at = datetime.now().astimezone().isoformat(timespec="seconds")
        try:
            with self.client_factory() as ths:
                checks.append(_run_check("complete_ths_code", lambda: ths.complete_ths_code(symbol)))
                checks.append(_run_check("wencai_nlp", lambda: ths.wencai_nlp(keyword)))
                checks.append(_run_check("ths_concept", ths.ths_concept))
                checks.append(_run_check("market_data_block", lambda: ths.market_data_block("URFI881121")))
                completed_code = _first_completed_code(checks) or _guess_a_share_thscode(symbol)
                checks.append(_run_check("klines", lambda: ths.klines(completed_code, count=5)))
                checks.append(_run_check("intraday_data", lambda: ths.intraday_data(completed_code)))
        except Exception as exc:
            return ThsdkProbeResult(
                provider=self.provider_name,
                status="failed",
                reason=f"{exc.__class__.__name__}: {exc}",
                next_step="确认 thsdk 动态库、网络、THS_USERNAME/THS_PASSWORD/THS_MAC 或游客权限。",
                started_at=started_at,
                account=_account_state(),
                checks=checks,
            )

        successful_checks = [item for item in checks if item["status"] == "success"]
        summary = {
            "success_count": len(successful_checks),
            "total_count": len(checks),
            "recommended_for_report": _recommended_for_report(successful_checks),
        }
        if not successful_checks:
            return ThsdkProbeResult(
                provider=self.provider_name,
                status="failed",
                reason="所有 thsdk 探测项均未返回可用数据",
                next_step="优先配置正式同花顺账号环境变量，或先在宿主机验证 thsdk 示例。",
                started_at=started_at,
                account=_account_state(),
                checks=checks,
                summary=summary,
            )

        return ThsdkProbeResult(
            provider=self.provider_name,
            status="success",
            started_at=started_at,
            account=_account_state(),
            checks=checks,
            summary=summary,
        )

    def __call__(self, trade_date: str) -> ReviewSourceResult:
        return self.collect_review_evidence(trade_date)

    def collect_review_evidence(self, trade_date: str) -> ReviewSourceResult:
        if self.client_factory is None:
            return ReviewSourceResult(
                source=self.source_name,
                source_url=self.source_url,
                status="disabled",
                reason="THSDK 未安装",
                trade_date=trade_date,
            )

        try:
            with self.client_factory() as ths:
                limit_up = _run_check("limit_up", lambda: ths.wencai_nlp("今日涨停，连续涨停天数，所属概念"))
                time.sleep(0.3)
                consecutive = _run_check("consecutive_limit_up", lambda: ths.wencai_nlp("今日连板股，所属概念"))
        except Exception as exc:
            return ReviewSourceResult(
                source=self.source_name,
                source_url=self.source_url,
                status="failed",
                reason=f"{exc.__class__.__name__}: {exc}",
                trade_date=trade_date,
            )

        rows = [*_sample_rows(limit_up.get("sample")), *_sample_rows(consecutive.get("sample"))]
        themes = _theme_evidence_from_wencai_rows(rows)
        hot_stocks = _stock_evidence_from_wencai_rows(rows)
        notes = _review_notes(limit_up, consecutive)
        has_content = bool(themes or hot_stocks or notes)
        return ReviewSourceResult(
            source=self.source_name,
            source_url=self.source_url,
            status="success" if has_content else "failed",
            reason=None if has_content else "THSDK 未返回可用问财/概念证据",
            trade_date=trade_date,
            themes=themes,
            hot_stocks=hot_stocks,
            market_notes=notes,
        )


def _run_check(name: str, call: Callable[[], Any]) -> dict[str, Any]:
    try:
        response = call()
    except Exception as exc:
        return {
            "name": name,
            "status": "failed",
            "reason": f"{exc.__class__.__name__}: {exc}",
        }

    success = bool(getattr(response, "success", False))
    data = getattr(response, "data", None)
    extra = getattr(response, "extra", None)
    error = getattr(response, "error", "")
    sample = _sample(data)
    return {
        "name": name,
        "status": "success" if success and sample is not None else "empty",
        "reason": None if success else str(error or "THSDK 返回失败"),
        "sample": sample,
        "extra_keys": sorted(extra.keys()) if isinstance(extra, dict) else [],
    }


def _sample(data: Any) -> Any:
    if data is None:
        return None
    if isinstance(data, list):
        return data[:120]
    if isinstance(data, dict):
        return {key: data[key] for key in list(data)[:8]}
    return str(data)[:500]


def _first_completed_code(checks: list[dict[str, Any]]) -> str | None:
    for check in checks:
        if check.get("name") != "complete_ths_code" or check.get("status") != "success":
            continue
        sample = check.get("sample")
        if isinstance(sample, list) and sample:
            first = sample[0]
            if isinstance(first, dict):
                code = first.get("THSCODE") or first.get("thscode") or first.get("code")
                if isinstance(code, str) and code:
                    return code
        if isinstance(sample, dict):
            code = sample.get("THSCODE") or sample.get("thscode") or sample.get("code")
            if isinstance(code, str) and code:
                return code
    return None


def _guess_a_share_thscode(symbol: str) -> str:
    normalized = symbol.strip()
    if normalized.startswith(("USHA", "USZA", "USTM")):
        return normalized
    if normalized.startswith(("6", "9")):
        return f"USHA{normalized}"
    if normalized.startswith(("8", "4")):
        return f"USTM{normalized}"
    return f"USZA{normalized}"


def _recommended_for_report(successful_checks: list[dict[str, Any]]) -> bool:
    names = {item["name"] for item in successful_checks}
    return bool(names & {"wencai_nlp", "ths_concept", "market_data_block"})


def _account_state() -> dict[str, bool]:
    return {
        "has_username": bool(os.getenv("THS_USERNAME")),
        "has_password": bool(os.getenv("THS_PASSWORD")),
        "has_mac": bool(os.getenv("THS_MAC")),
    }


def _theme_evidence_from_wencai_rows(rows: list[dict[str, Any]]) -> list[ReviewThemeEvidence]:
    by_name: dict[str, list[ReviewStockEvidence]] = {}
    for item in rows:
        stock = _stock_evidence_from_item(item)
        for concept in _concepts_from_item(item):
            if _ignore_concept(concept):
                continue
            by_name.setdefault(concept, [])
            if stock is not None:
                by_name[concept].append(stock)
    ranked = sorted(by_name.items(), key=lambda pair: (-len(pair[1]), pair[0]))
    return [
        ReviewThemeEvidence(name=name, stocks=_dedupe_review_stocks(stocks)[:5], source="THSDK")
        for name, stocks in ranked[:20]
    ]


def _stock_evidence_from_wencai_rows(rows: list[dict[str, Any]]) -> list[ReviewStockEvidence]:
    stocks = [_stock_evidence_from_item(item) for item in rows]
    return _dedupe_review_stocks([stock for stock in stocks if stock is not None])[:30]


def _stock_evidence_from_item(item: dict[str, Any]) -> ReviewStockEvidence | None:
    name = _text_value(item, "股票简称", "名称", "name")
    if not name or _ignore_stock(name):
        return None
    return ReviewStockEvidence(
        name=name,
        code=_text_value(item, "股票代码", "代码", "code"),
        pct_change=_float_value(item, "最新涨跌幅", "涨跌幅", "pct_change"),
        note=_limit_up_note(item),
        source="THSDK",
    )


def _review_notes(limit_up: dict[str, Any], consecutive: dict[str, Any]) -> list[str]:
    notes: list[str] = []
    if limit_up.get("status") == "success":
        notes.append(f"THSDK问财今日涨停返回{len(_sample_rows(limit_up.get('sample')))}条前排样例")
    if consecutive.get("status") == "success":
        notes.append(f"THSDK问财今日连板返回{len(_sample_rows(consecutive.get('sample')))}条高度样例")
    return notes


def _sample_rows(sample: object) -> list[dict[str, Any]]:
    if isinstance(sample, list):
        return [item for item in sample if isinstance(item, dict)]
    if isinstance(sample, dict):
        return [sample]
    return []


def _text_value(item: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = item.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _float_value(item: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = item.get(key)
        if value is None:
            continue
        try:
            return float(str(value).replace("%", "").replace("+", "").strip())
        except ValueError:
            continue
    return None


def _limit_up_note(item: dict[str, Any]) -> str:
    limit_days = _limit_days(item)
    if limit_days is not None and limit_days >= 2:
        return f"{limit_days}连板"
    for key, value in item.items():
        if "涨停" in str(key) and value:
            return str(value)
    return ""


def _limit_days(item: dict[str, Any]) -> int | None:
    for key, value in item.items():
        if "连续涨停天数" not in str(key):
            continue
        try:
            return int(float(str(value)))
        except ValueError:
            return None
    return None


def _concepts_from_item(item: dict[str, Any]) -> list[str]:
    raw = _text_value(item, "所属概念")
    if not raw:
        return []
    return [part.strip() for part in raw.split(";") if part.strip()]


def _ignore_concept(name: str) -> bool:
    noise = {
        "融资融券",
        "深股通",
        "沪股通",
        "ST板块",
        "专精特新",
        "2025年报预增",
        "国企改革",
        "股权转让(并购重组)",
    }
    return name in noise


def _ignore_stock(name: str) -> bool:
    return "ST" in name.upper()


def _dedupe_review_stocks(stocks: list[ReviewStockEvidence]) -> list[ReviewStockEvidence]:
    seen: set[tuple[str | None, str]] = set()
    output: list[ReviewStockEvidence] = []
    for stock in stocks:
        key = (stock.code, stock.name)
        if key in seen:
            continue
        seen.add(key)
        output.append(stock)
    return output
