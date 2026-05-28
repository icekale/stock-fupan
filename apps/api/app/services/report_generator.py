from dataclasses import dataclass
from pathlib import Path

from app.providers.llm import LLMProvider
from app.providers.market import MarketDataProvider, ProviderStatus
from app.providers.news import NewsProvider, SectorNewsResult
from app.providers.review_sources import ReviewSourceResult
from app.providers.tickflow import TickFlowQuoteProvider
from app.renderers.html_renderer import render_mobile_report_html
from app.renderers.png_exporter import export_png
from app.rules.scoring import score_sectors
from app.rules.validation import ValidationResult, validate_narrative_facts
from app.schemas.report import CapitalEvidence, ReportDTO, ReportKind, SectorCandidate, StockCandidate
from app.services.assets import AssetPaths, create_named_report_copies, create_report_asset_dir, report_kind_label, write_json
from app.services.next_day_prediction import build_next_day_predictions
from app.services.structured_review_generator import generate_structured_review
from app.services.theme_history import load_previous_strong_themes
from app.services.watchlist_observation import build_watchlist_observation


DEFAULT_LLM_METADATA_VALUE = "unknown"


@dataclass(frozen=True)
class GeneratedReport:
    report: ReportDTO
    validation: ValidationResult
    assets: AssetPaths
    provider_status: dict[str, object]
    structured_review_status: dict[str, object]


def _provider_metadata(provider: object, attribute_name: str) -> str:
    value = getattr(provider, attribute_name, DEFAULT_LLM_METADATA_VALUE)
    if isinstance(value, str) and value:
        return value
    return DEFAULT_LLM_METADATA_VALUE


class ReportGenerator:
    def __init__(
        self,
        reports_root: Path,
        market_provider: MarketDataProvider,
        news_provider: NewsProvider,
        llm_provider: LLMProvider,
        structured_review_provider: str = "rule",
        structured_review_fallback_enabled: bool = True,
        watchlist_service: object | None = None,
        tickflow_provider: TickFlowQuoteProvider | None = None,
        watchlist_enabled: bool = False,
        review_source_provider: object | None = None,
        previous_review_html_path: Path | None = None,
    ) -> None:
        self.reports_root = reports_root
        self.market_provider = market_provider
        self.news_provider = news_provider
        self.llm_provider = llm_provider
        self.structured_review_provider = structured_review_provider
        self.structured_review_fallback_enabled = structured_review_fallback_enabled
        self.watchlist_service = watchlist_service
        self.tickflow_provider = tickflow_provider
        self.watchlist_enabled = watchlist_enabled
        self.review_source_provider = review_source_provider
        self.previous_review_html_path = previous_review_html_path

    def generate_close_report(self, trade_date: str) -> GeneratedReport:
        return self._generate_report(trade_date, ReportKind.CLOSE)

    def generate_midday_report(self, trade_date: str) -> GeneratedReport:
        return self._generate_report(trade_date, ReportKind.MIDDAY)

    def _generate_report(self, trade_date: str, kind: ReportKind) -> GeneratedReport:
        assets = create_report_asset_dir(self.reports_root, trade_date, kind.value)
        if hasattr(self.market_provider, "get_close_snapshot_with_status"):
            market_snapshot, market_status = self.market_provider.get_close_snapshot_with_status(trade_date)
        else:
            market_snapshot = self.market_provider.get_close_snapshot(trade_date)
            market_status = ProviderStatus(
                provider=getattr(self.market_provider, "provider_name", "fake"),
                status="success",
                fallback_used=False,
                reason=None,
            )
        scored_sectors = score_sectors(market_snapshot.raw_sectors, top_n=5)
        review_source_results: list[ReviewSourceResult] = []
        if self.review_source_provider is not None:
            review_source_results = self.review_source_provider.collect(trade_date)

        news_items = []
        news_statuses = []
        for sector in scored_sectors:
            try:
                if hasattr(self.news_provider, "search_sector_news_with_status"):
                    sector_news = self.news_provider.search_sector_news_with_status(sector.name, trade_date)
                else:
                    sector_news = SectorNewsResult(
                        sector=sector.name,
                        items=self.news_provider.search_sector_news(sector.name, trade_date),
                        status=ProviderStatus(
                            provider=getattr(self.news_provider, "provider_name", "fake"),
                            status="success",
                            fallback_used=False,
                            reason=None,
                        ),
                    )
            except Exception as exc:
                sector_news = SectorNewsResult(
                    sector=sector.name,
                    items=[],
                    status=ProviderStatus(
                        provider=getattr(self.news_provider, "provider_name", "news"),
                        status="failed",
                        fallback_used=False,
                        reason=str(exc) or exc.__class__.__name__,
                    ),
                )
            news_items.extend(sector_news.items)
            news_statuses.append(
                {
                    "sector": sector_news.sector,
                    **sector_news.status.model_dump(mode="json"),
                }
            )

        seed = market_snapshot.to_report_seed(news_items)
        seed["report_kind"] = kind.value
        seed["review_window"] = "下午" if kind == ReportKind.MIDDAY else "明日"
        seed["raw_sectors"] = [
            {
                "name": scored.name,
                "pct_change": scored.pct_change,
                "limit_up_count": 0,
                "stock_up_ratio": 0.0,
                "turnover_change": 0.0,
                "news_weight": scored.factor_scores.get("news", 0) / 100,
            }
            for scored in scored_sectors
        ]
        narrative = self.llm_provider.generate_narrative(seed)

        sector_candidates = [
            self._build_sector_candidate(
                scored,
                news_items,
                review_source_results,
                self._get_sector_frontline_stocks(scored.name),
            )
            for scored in scored_sectors
        ]

        report = ReportDTO(
            trade_date=trade_date,
            kind=kind,
            title=f"{trade_date}-{report_kind_label(kind.value)}",
            indices=market_snapshot.indices,
            breadth=market_snapshot.breadth,
            turnover_cny=market_snapshot.turnover_cny,
            market_state_tags=market_snapshot.market_state_tags,
            sectors=sector_candidates,
            narrative=narrative,
            news=news_items,
        )
        report.next_day_predictions = build_next_day_predictions(
            report=report,
            review_source_results=review_source_results,
        )
        report.previous_strong_themes = load_previous_strong_themes(
            reports_root=self.reports_root,
            trade_date=trade_date,
            current_sectors=report.sectors,
            previous_review_html_path=self.previous_review_html_path,
            tickflow_provider=self.tickflow_provider,
        )
        structured_review, structured_review_status = generate_structured_review(
            report=report,
            llm_provider=self.llm_provider,
            provider_mode=self.structured_review_provider,
            fallback_enabled=self.structured_review_fallback_enabled,
        )
        report.structured_review = structured_review
        watchlist_tickflow_status = ProviderStatus(
            provider="tickflow",
            status="disabled",
            fallback_used=False,
            reason="自选股模块未开启",
        )
        if self.watchlist_enabled and self.watchlist_service is not None:
            latest_watchlist = self.watchlist_service.get_latest()
            symbols = [item.symbol for item in latest_watchlist.items]
            quotes = []
            if self.tickflow_provider is not None and symbols:
                if hasattr(self.tickflow_provider, "get_quotes_with_status"):
                    quotes, watchlist_tickflow_status = self.tickflow_provider.get_quotes_with_status(symbols)
                else:
                    quotes = self.tickflow_provider.get_quotes(symbols)
                    watchlist_tickflow_status = ProviderStatus(
                        provider=getattr(self.tickflow_provider, "provider_name", "tickflow"),
                        status="success",
                        fallback_used=False,
                        reason=None,
                    )
            report.watchlist_observation = build_watchlist_observation(
                import_id=latest_watchlist.import_id,
                items=latest_watchlist.items,
                quotes=quotes,
                sectors=report.sectors,
            )
        validation = validate_narrative_facts(report)
        provider_status = {
            "market": market_status.model_dump(mode="json"),
            "market_tickflow": market_status.model_dump(mode="json"),
            "news": news_statuses,
            "tickflow": watchlist_tickflow_status.model_dump(mode="json"),
            "watchlist_tickflow": watchlist_tickflow_status.model_dump(mode="json"),
            "review_sources": [_review_source_status(result) for result in review_source_results],
        }
        structured_review_status_payload = structured_review_status.model_dump(mode="json")

        write_json(assets.facts, market_snapshot.to_report_seed(news=[]))
        write_json(assets.news_raw, [item.model_dump() for item in news_items])
        write_json(
            assets.llm_calls,
            [
                {
                    "provider": _provider_metadata(self.llm_provider, "provider_name"),
                    "model": _provider_metadata(self.llm_provider, "model_name"),
                    "prompt": "seed-json",
                    "parameters": {},
                    "output": narrative.model_dump(),
                    "validation_errors": validation.errors,
                },
                {
                    "provider": _provider_metadata(self.llm_provider, "provider_name"),
                    "model": _provider_metadata(self.llm_provider, "model_name"),
                    "prompt": "structured-review-json",
                    "parameters": {"provider_mode": self.structured_review_provider},
                    "output": report.structured_review.model_dump(mode="json") if report.structured_review else {},
                    "validation_errors": [],
                }
            ],
        )
        write_json(assets.report_dto, report.model_dump(mode="json"))
        write_json(
            assets.snapshot,
            {
                "report": report.model_dump(mode="json"),
                "validation": {"is_valid": validation.is_valid, "errors": validation.errors},
                "provider_status": provider_status,
                "structured_review_status": structured_review_status_payload,
            },
        )
        assets.report_html.write_text(render_mobile_report_html(report), encoding="utf-8")
        export_png(assets.report_html, assets.report_png)
        create_named_report_copies(assets, trade_date=trade_date, kind=kind.value)
        write_json(assets.notes, {"overrides": []})

        return GeneratedReport(
            report=report,
            validation=validation,
            assets=assets,
            provider_status=provider_status,
            structured_review_status=structured_review_status_payload,
        )

    def _build_sector_candidate(
        self,
        scored: object,
        news_items: list[object],
        review_source_results: list[ReviewSourceResult],
        frontline_stocks: list[object] | None = None,
    ) -> SectorCandidate:
        review_sources: list[str] = []
        review_notes: list[str] = []
        top_stocks: list[StockCandidate] = [
            _tickflow_quote_to_candidate(stock)
            for stock in (frontline_stocks or [])
        ]
        sector_name = getattr(scored, "name")
        for result in review_source_results:
            if result.status != "success":
                continue
            result_matches_sector = any(
                _theme_matches(sector_name, theme.name) for theme in result.themes
            )
            matching_notes = [
                note for note in result.market_notes if _note_matches_sector(sector_name, note, result)
            ]
            for theme in result.themes:
                if not _theme_matches(sector_name, theme.name):
                    continue
                if _theme_is_positive(theme) or matching_notes:
                    review_sources.append(result.source)
                    if theme.reason:
                        review_notes.append(theme.reason)
                    for stock in theme.stocks:
                        top_stocks.append(_review_stock_to_candidate(stock, result.source))
            for note in matching_notes:
                review_notes.append(note)
                review_sources.append(result.source)
            if result_matches_sector or matching_notes:
                for stock in result.hot_stocks:
                    if _stock_matches_sector_note(stock.name, matching_notes):
                        top_stocks.append(_review_stock_to_candidate(stock, result.source))
        return SectorCandidate(
            name=sector_name,
            score=getattr(scored, "score"),
            rank=getattr(scored, "rank"),
            pct_change=getattr(scored, "pct_change"),
            reason="强度与复盘源共同确认" if review_sources else "综合评分靠前",
            top_stocks=_dedupe_stock_candidates(top_stocks),
            news_summaries=[item.summary for item in news_items if item.matched_sector == sector_name],
            factor_scores=getattr(scored, "factor_scores"),
            review_sources=_dedupe_strings(review_sources),
            review_notes=_dedupe_strings(review_notes),
            capital_evidence=_build_capital_evidence(_dedupe_stock_candidates(top_stocks)),
        )

    def _get_sector_frontline_stocks(self, sector_name: str) -> list[object]:
        get_frontline = getattr(self.market_provider, "get_sector_frontline_stocks", None)
        if not callable(get_frontline):
            return []
        return list(get_frontline(sector_name))


def _theme_matches(sector_name: str, theme_name: str) -> bool:
    sector_key = sector_name.lower()
    theme_key = theme_name.lower()
    aliases = {
        "pcb": ["pcb"],
        "有色金属": ["有色", "贵金属", "工业金属", "小金属", "黄金", "金属"],
        "半导体": ["半导体", "芯片", "先进封装", "封测"],
        "新材料": ["新材料", "材料", "培育钻石"],
    }
    candidates = aliases.get(sector_key, [sector_key])
    return any(candidate in theme_key or theme_key in candidate for candidate in candidates)


def _note_matches_sector(sector_name: str, note: str, result: ReviewSourceResult) -> bool:
    if sector_name in note:
        return True
    return any(_theme_matches(sector_name, theme.name) and theme.name in note for theme in result.themes)


def _theme_is_positive(theme: object) -> bool:
    pct_change = getattr(theme, "pct_change", None)
    return pct_change is not None and pct_change > 0


def _stock_matches_sector_note(stock_name: str, notes: list[str]) -> bool:
    return any(stock_name and stock_name in note for note in notes)


def _review_stock_to_candidate(stock: object, source: str) -> StockCandidate:
    return StockCandidate(
        code=getattr(stock, "code") or "",
        name=getattr(stock, "name"),
        pct_change=getattr(stock, "pct_change") or 0.0,
        tags=[getattr(stock, "source") or source],
    )


def _tickflow_quote_to_candidate(quote: object) -> StockCandidate:
    turnover_cny = getattr(quote, "turnover_cny") or None
    turnover_rate = getattr(quote, "turnover_rate") or None
    pct_change = getattr(quote, "pct_change") or 0.0
    return StockCandidate(
        code=getattr(quote, "symbol") or "",
        name=getattr(quote, "name") or getattr(quote, "symbol") or "",
        pct_change=pct_change,
        turnover_cny=turnover_cny,
        turnover_rate=turnover_rate,
        capital_strength=getattr(quote, "capital_strength") or _stock_capital_strength(
            turnover_cny,
            turnover_rate,
            pct_change,
        ),
        tags=["TickFlow前排"],
    )


def _build_capital_evidence(stocks: list[StockCandidate]) -> CapitalEvidence | None:
    tickflow_stocks = [stock for stock in stocks if "TickFlow前排" in stock.tags]
    if not tickflow_stocks:
        return None
    turnover_values = [stock.turnover_cny for stock in tickflow_stocks if stock.turnover_cny is not None]
    turnover_rate_values = [stock.turnover_rate for stock in tickflow_stocks if stock.turnover_rate is not None]
    front_row_turnover = sum(turnover_values) if turnover_values else None
    avg_turnover_rate = (
        round(sum(turnover_rate_values) / len(turnover_rate_values), 2)
        if turnover_rate_values
        else None
    )
    active_count = sum(
        1
        for stock in tickflow_stocks
        if (stock.turnover_cny or 0) >= 1_000_000_000 or (stock.turnover_rate or 0) >= 5
    )
    strength = _sector_capital_strength(front_row_turnover, avg_turnover_rate, active_count)
    summary_parts = []
    if front_row_turnover is not None:
        summary_parts.append(f"前排成交额合计{front_row_turnover / 100_000_000:.2f}亿")
    if avg_turnover_rate is not None:
        summary_parts.append(f"平均换手{avg_turnover_rate:.2f}%")
    summary_parts.append(f"活跃前排{active_count}只")
    return CapitalEvidence(
        front_row_turnover_cny=front_row_turnover,
        avg_turnover_rate=avg_turnover_rate,
        active_stock_count=active_count,
        strength=strength,
        summary="、".join(summary_parts),
    )


def _sector_capital_strength(
    front_row_turnover: float | None,
    avg_turnover_rate: float | None,
    active_count: int,
) -> str:
    turnover_yi = (front_row_turnover or 0) / 100_000_000
    rate = avg_turnover_rate or 0
    if turnover_yi >= 80 and active_count >= 2 and rate >= 8:
        return "强"
    if turnover_yi >= 30 or active_count >= 2 or rate >= 6:
        return "中"
    return "弱"


def _stock_capital_strength(
    turnover_cny: float | None,
    turnover_rate: float | None,
    pct_change: float,
) -> str | None:
    if turnover_cny is None and turnover_rate is None:
        return None
    turnover_yi = (turnover_cny or 0) / 100_000_000
    rate = turnover_rate or 0
    if turnover_yi >= 30 and rate >= 20 and pct_change >= 5:
        return "高换手强承接"
    if turnover_yi >= 10 or (rate >= 8 and pct_change >= 5):
        return "强"
    if turnover_yi >= 3 or rate >= 5:
        return "温和放量"
    if rate >= 25 and pct_change < 5:
        return "高换手分歧"
    return "一般"


def _dedupe_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        normalized = value.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        output.append(normalized)
    return output


def _dedupe_stock_candidates(stocks: list[StockCandidate]) -> list[StockCandidate]:
    seen: set[tuple[str, str]] = set()
    output: list[StockCandidate] = []
    for stock in stocks:
        key = (stock.code, stock.name)
        if key in seen:
            continue
        seen.add(key)
        output.append(stock)
    return output[:8]


def _review_source_status(result: ReviewSourceResult) -> dict[str, object]:
    return {
        "source": result.source,
        "source_url": result.source_url,
        "status": result.status,
        "reason": result.reason,
        "theme_count": len(result.themes),
        "hot_stock_count": len(result.hot_stocks),
    }
