from __future__ import annotations

import csv
import io
import json
import re
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import Engine, func, select

from app.db.models import EvidenceRecord
from app.db.session import session_scope
from app.schemas.evidence import (
    EvidenceCategory,
    EvidenceConfidence,
    EvidenceInput,
    EvidenceItem,
    EvidenceParsePreview,
    EvidencePreviewItem,
    EvidenceStatus,
)
from app.schemas.report import NewsItem


TRUSTED_EVIDENCE_SOURCES = (
    "财联社",
    "东方财富",
    "证券时报",
    "上海证券报",
    "上证报",
    "新浪财经",
    "36氪",
    "搜狐财经",
    "快科技",
    "金融界",
    "交易所",
)


ANISPIRE_TASK_QUERIES = {
    "stcn_capital_flow": "证券时报 行业资金 净流入 净流出 A股",
    "jrj_continuous_outflow": "金融界 主力资金 连续 净流出",
    "catalysts": "搜狐财经 36氪 快科技 新浪财经 催化 A股",
}


def parse_evidence_preview(content: str) -> EvidenceParsePreview:
    rows = _parse_rows(content)
    preview_items = [_preview_row(row) for row in rows]
    return EvidenceParsePreview(
        items=preview_items,
        valid_count=sum(1 for item in preview_items if item.item is not None and not item.errors),
        invalid_count=sum(1 for item in preview_items if item.errors),
    )


def validate_evidence_item(item: EvidenceInput) -> list[str]:
    errors: list[str] = []
    for field_name in (
        "trade_date",
        "source",
        "title",
        "url",
        "published_at",
        "category",
        "claim",
        "confidence",
    ):
        value = getattr(item, field_name)
        if isinstance(value, str) and not value.strip():
            errors.append(f"{field_name} is required")

    if item.confidence == EvidenceConfidence.HIGH:
        if not _date_matches_trade_window(item.trade_date, item.published_at):
            errors.append("high evidence requires trade date or previous-day date match")
        if not item.manual_confirmed and not _is_trusted_source(item.source):
            errors.append("high evidence requires trusted source or manual confirmation")

    if item.category == EvidenceCategory.CAPITAL_FLOW and item.confidence == EvidenceConfidence.HIGH:
        if not item.numbers:
            errors.append("capital_flow high evidence requires numbers")
        elif not _has_numeric_value(item.numbers):
            errors.append("capital_flow high evidence requires numeric numbers")

    return errors


def candidate_from_news_item(news_item: NewsItem, trade_date: str, query: str) -> EvidenceInput:
    source = news_item.source or _infer_source_from_title(news_item.title) or "Anspire"
    return EvidenceInput(
        trade_date=trade_date,
        source=source,
        title=news_item.title,
        url=news_item.url,
        published_at=news_item.published_at or f"{trade_date}T00:00:00+08:00",
        category=_infer_category(query, news_item.title),
        claim=news_item.summary or news_item.title,
        numbers=_extract_numbers(f"{news_item.title} {news_item.summary}"),
        related_sectors=[news_item.matched_sector] if news_item.matched_sector else [],
        confidence=EvidenceConfidence.MEDIUM,
        status=EvidenceStatus.CANDIDATE,
    )


def query_for_candidate_task(task: str, custom_query: str) -> str:
    if custom_query.strip():
        return custom_query.strip()
    return ANISPIRE_TASK_QUERIES.get(task, task)


def build_candidate_preview_from_news(
    trade_date: str,
    query: str,
    items: list[NewsItem],
) -> EvidenceParsePreview:
    preview_items: list[EvidencePreviewItem] = []
    for news_item in items:
        item = candidate_from_news_item(news_item, trade_date=trade_date, query=query)
        preview_items.append(
            EvidencePreviewItem(
                raw=news_item.model_dump(mode="json"),
                item=item,
                errors=validate_evidence_item(item),
            )
        )
    return EvidenceParsePreview(
        items=preview_items,
        valid_count=sum(1 for item in preview_items if not item.errors),
        invalid_count=sum(1 for item in preview_items if item.errors),
    )


class EvidenceStore:
    def __init__(self, engine: Engine):
        self.engine = engine

    def save_items(self, items: list[EvidenceInput]) -> list[EvidenceItem]:
        _reject_duplicate_explicit_ids(items)
        with session_scope(self.engine) as session:
            saved: list[EvidenceItem] = []
            for item in items:
                errors = validate_evidence_item(item)
                if errors:
                    raise ValueError("; ".join(errors))
                evidence_id = item.id or self._next_evidence_id(item.trade_date, len(saved) + 1)
                record = session.scalar(
                    select(EvidenceRecord).where(EvidenceRecord.evidence_id == evidence_id)
                )
                if record is None:
                    record = EvidenceRecord(evidence_id=evidence_id)
                    session.add(record)
                _apply_item_to_record(record, item)
                saved.append(_record_to_item(record))
            return saved

    def list_items(
        self,
        trade_date: str,
        *,
        status: EvidenceStatus | None = None,
        category: EvidenceCategory | None = None,
    ) -> list[EvidenceItem]:
        statement = select(EvidenceRecord).where(EvidenceRecord.trade_date == trade_date)
        if status is not None:
            statement = statement.where(EvidenceRecord.status == status.value)
        if category is not None:
            statement = statement.where(EvidenceRecord.category == category.value)
        statement = statement.order_by(EvidenceRecord.id)
        with session_scope(self.engine) as session:
            return [_record_to_item(record) for record in session.scalars(statement).all()]

    def list_verified(
        self,
        trade_date: str,
        *,
        category: EvidenceCategory | None = None,
    ) -> list[EvidenceItem]:
        return self.list_items(trade_date, status=EvidenceStatus.VERIFIED, category=category)

    def _next_evidence_id(self, trade_date: str, sequence: int) -> str:
        prefix = f"ev_{trade_date.replace('-', '')}_"
        statement = select(func.count()).select_from(EvidenceRecord).where(
            EvidenceRecord.evidence_id.like(f"{prefix}%")
        )
        with session_scope(self.engine) as session:
            count = session.execute(statement).scalar_one()
        return f"{prefix}{count + sequence:03d}"


def _parse_rows(content: str) -> list[dict[str, Any] | str]:
    stripped = content.strip()
    if not stripped:
        return []
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        return _parse_table_rows(stripped)
    if isinstance(payload, list):
        return [row if isinstance(row, dict) else str(row) for row in payload]
    if isinstance(payload, dict):
        return [payload]
    return [stripped]


def _parse_table_rows(content: str) -> list[dict[str, Any] | str]:
    first_line = content.splitlines()[0]
    delimiter = "\t" if "\t" in first_line else "|" if "|" in first_line else ","
    reader = csv.DictReader(io.StringIO(content), delimiter=delimiter)
    rows: list[dict[str, Any] | str] = []
    for row in reader:
        cleaned = {str(key).strip(): _clean_table_value(value) for key, value in row.items() if key}
        extras = row.get(None)
        if extras and isinstance(cleaned.get("related_sectors"), str):
            cleaned["related_sectors"] = ",".join(
                [cleaned["related_sectors"], *(str(extra).strip() for extra in extras)]
            )
        if "related_sectors" in cleaned and isinstance(cleaned["related_sectors"], str):
            cleaned["related_sectors"] = _split_related_sectors(cleaned["related_sectors"])
        rows.append(cleaned)
    return rows


def _preview_row(row: dict[str, Any] | str) -> EvidencePreviewItem:
    if not isinstance(row, dict):
        return EvidencePreviewItem(raw=row, item=None, errors=["row must be an object"])
    row = _normalize_row(row)
    try:
        item = EvidenceInput.model_validate(row)
    except Exception as exc:
        return EvidencePreviewItem(raw=row, item=None, errors=[str(exc)])
    errors = validate_evidence_item(item)
    return EvidencePreviewItem(raw=row, item=item if not errors else item, errors=errors)


def _clean_table_value(value: object) -> object:
    if value is None:
        return ""
    text = str(value).strip()
    if text.startswith("{") and text.endswith("}"):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text
    return text


def _normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(row)
    if isinstance(normalized.get("related_sectors"), str):
        normalized["related_sectors"] = _split_related_sectors(normalized["related_sectors"])
    return normalized


def _split_related_sectors(value: str) -> list[str]:
    return [part.strip() for part in value.replace("，", ",").split(",") if part.strip()]


def _has_numeric_value(value: object) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, int | float):
        return True
    if isinstance(value, dict):
        return any(_has_numeric_value(child) for child in value.values())
    if isinstance(value, list):
        return any(_has_numeric_value(child) for child in value)
    return False


def _date_matches_trade_window(trade_date: str, published_at: str) -> bool:
    try:
        trade_day = date.fromisoformat(trade_date)
        published_day = datetime.fromisoformat(published_at).date()
    except ValueError:
        return False
    return published_day in {trade_day, trade_day - timedelta(days=1)}


def _is_trusted_source(source: str) -> bool:
    return any(trusted in source for trusted in TRUSTED_EVIDENCE_SOURCES)


def _infer_source_from_title(title: str) -> str | None:
    for source in TRUSTED_EVIDENCE_SOURCES:
        if source in title:
            return source
    return None


def _infer_category(query: str, title: str) -> EvidenceCategory:
    text = f"{query} {title}"
    if any(keyword in text for keyword in ("资金", "净流入", "净流出", "主力")):
        return EvidenceCategory.CAPITAL_FLOW
    if any(keyword in text for keyword in ("涨停", "连板")):
        return EvidenceCategory.LIMIT_UP
    if any(keyword in text for keyword in ("风险", "退市", "减持", "净流出")):
        return EvidenceCategory.RISK
    if any(keyword in text for keyword in ("政策", "会议", "监管")):
        return EvidenceCategory.POLICY
    if any(keyword in text for keyword in ("业绩", "盈利", "财报")):
        return EvidenceCategory.EARNINGS
    return EvidenceCategory.CATALYST


def _extract_numbers(text: str) -> dict[str, float]:
    numbers: dict[str, float] = {}
    continuous_outflow = re.search(r"连续\s*(\d+)\s*天\s*净流出", text)
    if continuous_outflow:
        numbers["continuous_outflow_days"] = float(continuous_outflow.group(1))
    for index, match in enumerate(re.finditer(r"-?\d+(?:\.\d+)?", text), start=1):
        numbers[f"value_{index}"] = float(match.group(0))
    return numbers


def _record_to_item(record: EvidenceRecord) -> EvidenceItem:
    return EvidenceItem(
        id=record.evidence_id,
        trade_date=record.trade_date,
        source=record.source,
        title=record.title,
        url=record.url,
        published_at=record.published_at,
        category=EvidenceCategory(record.category),
        claim=record.claim,
        numbers=record.numbers or {},
        related_sectors=record.related_sectors or [],
        confidence=EvidenceConfidence(record.confidence),
        status=EvidenceStatus(record.status),
        manual_confirmed=record.manual_confirmed,
    )


def _apply_item_to_record(record: EvidenceRecord, item: EvidenceInput) -> None:
    record.trade_date = item.trade_date
    record.source = item.source
    record.title = item.title
    record.url = item.url
    record.published_at = item.published_at
    record.category = item.category.value
    record.claim = item.claim
    record.numbers = item.numbers
    record.related_sectors = item.related_sectors
    record.confidence = item.confidence.value
    record.status = item.status.value
    record.manual_confirmed = item.manual_confirmed


def _reject_duplicate_explicit_ids(items: list[EvidenceInput]) -> None:
    seen: set[str] = set()
    for item in items:
        if item.id is None:
            continue
        if item.id in seen:
            raise ValueError(f"duplicate evidence id in batch: {item.id}")
        seen.add(item.id)
