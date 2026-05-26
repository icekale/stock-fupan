from dataclasses import dataclass
from pathlib import Path

from app.providers.llm import LLMProvider
from app.providers.market import MarketDataProvider, ProviderStatus
from app.providers.news import NewsProvider, SectorNewsResult
from app.providers.tickflow import TickFlowQuoteProvider
from app.renderers.html_renderer import render_mobile_report_html
from app.renderers.png_exporter import export_png
from app.rules.scoring import score_sectors
from app.rules.validation import ValidationResult, validate_narrative_facts
from app.schemas.report import ReportDTO, ReportKind, SectorCandidate
from app.services.assets import AssetPaths, create_report_asset_dir, write_json
from app.services.structured_review_generator import generate_structured_review
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

    def generate_close_report(self, trade_date: str) -> GeneratedReport:
        assets = create_report_asset_dir(self.reports_root, trade_date, ReportKind.CLOSE.value)
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

        news_items = []
        news_statuses = []
        for sector in scored_sectors:
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
            news_items.extend(sector_news.items)
            news_statuses.append(
                {
                    "sector": sector_news.sector,
                    **sector_news.status.model_dump(mode="json"),
                }
            )

        seed = market_snapshot.to_report_seed(news_items)
        narrative = self.llm_provider.generate_narrative(seed)

        sector_candidates = [
            SectorCandidate(
                name=scored.name,
                score=scored.score,
                rank=scored.rank,
                pct_change=scored.pct_change,
                reason="综合评分靠前",
                top_stocks=[],
                news_summaries=[
                    item.summary for item in news_items if item.matched_sector == scored.name
                ],
                factor_scores=scored.factor_scores,
            )
            for scored in scored_sectors
        ]

        report = ReportDTO(
            trade_date=trade_date,
            kind=ReportKind.CLOSE,
            title=f"{trade_date} A股复盘",
            indices=market_snapshot.indices,
            breadth=market_snapshot.breadth,
            turnover_cny=market_snapshot.turnover_cny,
            market_state_tags=market_snapshot.market_state_tags,
            sectors=sector_candidates,
            narrative=narrative,
            news=news_items,
        )
        structured_review, structured_review_status = generate_structured_review(
            report=report,
            llm_provider=self.llm_provider,
            provider_mode=self.structured_review_provider,
            fallback_enabled=self.structured_review_fallback_enabled,
        )
        report.structured_review = structured_review
        tickflow_status = ProviderStatus(
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
                    quotes, tickflow_status = self.tickflow_provider.get_quotes_with_status(symbols)
                else:
                    quotes = self.tickflow_provider.get_quotes(symbols)
                    tickflow_status = ProviderStatus(
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
            "news": news_statuses,
            "tickflow": tickflow_status.model_dump(mode="json"),
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
        write_json(assets.notes, {"overrides": []})

        return GeneratedReport(
            report=report,
            validation=validation,
            assets=assets,
            provider_status=provider_status,
            structured_review_status=structured_review_status_payload,
        )
