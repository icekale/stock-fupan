from typing import Any

from app.rules.validation import ValidationResult
from app.schemas.report import QualityGateIssue, QualityGateResult, ReportDTO, ReportKind


PUBLISHABLE_THRESHOLD = 85
BLOCKED_THRESHOLD = 70


def evaluate_quality_gate(
    report: ReportDTO,
    validation: ValidationResult,
    provider_status: dict[str, object],
    structured_review_status: dict[str, object],
) -> QualityGateResult:
    if report.kind != ReportKind.CLOSE:
        return QualityGateResult(
            score=None,
            publish_status="not_applicable",
            label="暂不评分",
            summary="该报告类型暂不接入质量门禁",
            provider_summary={},
        )

    hard_failures: list[QualityGateIssue] = []
    warnings: list[QualityGateIssue] = []
    provider_summary = _provider_summary(provider_status, structured_review_status)

    market_summary = provider_summary["market"]
    if (
        market_summary["status"] != "success"
        or market_summary["fallback_used"]
        or market_summary["provider"] == "fake"
    ):
        hard_failures.append(
            _issue(
                "market_source_untrusted",
                "hard",
                "行情数据源失败或使用 fake fallback",
                market_summary,
            )
        )

    if not validation.is_valid:
        hard_failures.append(
            _issue(
                "fact_validation_failed",
                "hard",
                "报告事实校验失败",
                {"errors": validation.errors},
            )
        )

    for index, sector in enumerate(report.sectors[:2], start=1):
        if not sector.top_stocks:
            hard_failures.append(
                _issue(
                    "top_sector_missing_front_row",
                    "hard",
                    f"Top{index} 板块缺少前排股",
                    {"sector": sector.name, "rank": sector.rank},
                )
            )

    if not provider_status or "market" not in provider_status:
        hard_failures.append(
            _issue(
                "provider_status_missing",
                "hard",
                "关键 provider 状态缺失，无法判断数据来源",
                {},
            )
        )

    structured_status = provider_summary["structured_review"]
    if structured_status["status"] in {"failed", "empty", "missing"}:
        hard_failures.append(
            _issue(
                "structured_review_missing",
                "hard",
                "结构化复盘为空或生成失败",
                structured_status,
            )
        )

    score = 100
    news_summary = provider_summary["news"]
    failed_news_count = int(news_summary["failed_count"])
    if failed_news_count:
        penalty = min(failed_news_count * 5, 20)
        score -= penalty
        warnings.append(
            _issue(
                "news_partial_failed",
                "warning",
                f"新闻源有 {failed_news_count} 个板块失败",
                {"failed_count": failed_news_count, "penalty": penalty},
            )
        )
    if not report.news:
        score -= 20
        warnings.append(
            _issue("news_empty", "warning", "新闻结果为空", {"penalty": 20})
        )

    review_summary = provider_summary["review_sources"]
    review_success_count = int(review_summary["success_count"])
    review_failed_count = int(review_summary["failed_count"])
    if review_success_count == 0:
        score -= 15
        warnings.append(
            _issue(
                "review_sources_empty",
                "warning",
                "复盘辅助源全部失败或为空",
                {"penalty": 15},
            )
        )
    elif review_failed_count:
        score -= 5
        warnings.append(
            _issue(
                "review_sources_partial_failed",
                "warning",
                f"复盘辅助源有 {review_failed_count} 个失败",
                {"failed_count": review_failed_count, "penalty": 5},
            )
        )

    catalyst_missing_count = sum(1 for sector in report.sectors[:3] if not sector.news_summaries)
    if catalyst_missing_count:
        penalty = min(catalyst_missing_count * 5, 15)
        score -= penalty
        warnings.append(
            _issue(
                "top_sector_catalyst_missing",
                "warning",
                f"Top 板块有 {catalyst_missing_count} 个缺少催化新闻",
                {"missing_count": catalyst_missing_count, "penalty": penalty},
            )
        )

    if not report.previous_strong_themes:
        score -= 5
        warnings.append(
            _issue("history_replay_missing", "warning", "历史主线回放缺失", {"penalty": 5})
        )

    if structured_status.get("fallback_used"):
        score -= 10
        warnings.append(
            _issue(
                "structured_review_fallback",
                "warning",
                "结构化复盘使用 fallback",
                {"penalty": 10},
            )
        )

    if hard_failures:
        score = min(score, BLOCKED_THRESHOLD - 1)
    score = max(score, 0)
    publish_status = _publish_status(score, hard_failures)
    label = _status_label(publish_status)
    summary = _summary(publish_status, score, hard_failures, warnings)

    return QualityGateResult(
        score=score,
        publish_status=publish_status,
        label=label,
        summary=summary,
        hard_failures=hard_failures,
        warnings=warnings,
        provider_summary=provider_summary,
    )


def _publish_status(score: int, hard_failures: list[QualityGateIssue]) -> str:
    if hard_failures or score < BLOCKED_THRESHOLD:
        return "blocked"
    if score < PUBLISHABLE_THRESHOLD:
        return "degraded"
    return "publishable"


def _status_label(publish_status: str) -> str:
    if publish_status == "publishable":
        return "可发布"
    if publish_status == "degraded":
        return "可发布但有降级"
    if publish_status == "blocked":
        return "不可发布草稿"
    if publish_status == "not_scored":
        return "未评分"
    return "暂不评分"


def _summary(
    publish_status: str,
    score: int,
    hard_failures: list[QualityGateIssue],
    warnings: list[QualityGateIssue],
) -> str:
    label = _status_label(publish_status)
    if hard_failures:
        return f"{label} · 质量分 {score} · {hard_failures[0].message}"
    if warnings:
        return f"{label} · 质量分 {score} · {warnings[0].message}"
    return f"{label} · 质量分 {score}"


def _provider_summary(
    provider_status: dict[str, object],
    structured_review_status: dict[str, object],
) -> dict[str, Any]:
    market = _as_dict(provider_status.get("market"))
    news_items = [_as_dict(item) for item in _as_list(provider_status.get("news"))]
    review_items = [_as_dict(item) for item in _as_list(provider_status.get("review_sources"))]
    structured = _as_dict(structured_review_status)

    fake_fallback_used = bool(market.get("fallback_used")) or any(
        bool(item.get("fallback_used")) for item in news_items
    )
    return {
        "market": {
            "status": str(market.get("status", "missing")),
            "provider": str(market.get("provider", "missing")),
            "fallback_used": bool(market.get("fallback_used")),
        },
        "news": _group_status_summary(news_items),
        "review_sources": _group_status_summary(review_items),
        "structured_review": {
            "status": str(structured.get("status", "missing")),
            "provider": str(structured.get("provider", "missing")),
            "fallback_used": bool(structured.get("fallback_used")),
        },
        "fake_fallback_used": fake_fallback_used,
    }


def _group_status_summary(items: list[dict[str, object]]) -> dict[str, object]:
    success_count = sum(1 for item in items if item.get("status") == "success")
    failed_count = sum(1 for item in items if item.get("status") not in {"success", "disabled"})
    fallback_count = sum(1 for item in items if item.get("status") == "fallback" or item.get("fallback_used"))
    if not items:
        status = "missing"
    elif failed_count == 0:
        status = "success"
    elif success_count:
        status = "partial_failed"
    else:
        status = "failed"
    return {
        "status": status,
        "success_count": success_count,
        "failed_count": failed_count,
        "fallback_count": fallback_count,
    }


def _issue(
    code: str,
    severity: str,
    message: str,
    details: dict[str, object],
) -> QualityGateIssue:
    return QualityGateIssue(code=code, severity=severity, message=message, details=details)


def _as_dict(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


def _as_list(value: object) -> list[object]:
    return value if isinstance(value, list) else []
