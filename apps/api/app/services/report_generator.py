from dataclasses import dataclass
from pathlib import Path

from app.providers.llm import LLMProvider
from app.providers.market import MarketDataProvider
from app.providers.news import NewsProvider
from app.renderers.html_renderer import render_mobile_report_html
from app.rules.scoring import score_sectors
from app.rules.validation import ValidationResult, validate_narrative_facts
from app.schemas.report import ReportDTO, ReportKind, SectorCandidate
from app.services.assets import AssetPaths, create_report_asset_dir, write_json


DEFAULT_LLM_METADATA_VALUE = "unknown"


@dataclass(frozen=True)
class GeneratedReport:
    report: ReportDTO
    validation: ValidationResult
    assets: AssetPaths


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
    ) -> None:
        self.reports_root = reports_root
        self.market_provider = market_provider
        self.news_provider = news_provider
        self.llm_provider = llm_provider

    def generate_close_report(self, trade_date: str) -> GeneratedReport:
        assets = create_report_asset_dir(self.reports_root, trade_date, ReportKind.CLOSE.value)
        market_snapshot = self.market_provider.get_close_snapshot(trade_date)
        scored_sectors = score_sectors(market_snapshot.raw_sectors, top_n=5)

        news_items = []
        for sector in scored_sectors:
            news_items.extend(self.news_provider.search_sector_news(sector.name, trade_date))

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
        validation = validate_narrative_facts(report)

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
                }
            ],
        )
        write_json(assets.report_dto, report.model_dump(mode="json"))
        write_json(
            assets.snapshot,
            {
                "report": report.model_dump(mode="json"),
                "validation": {"is_valid": validation.is_valid, "errors": validation.errors},
            },
        )
        assets.report_html.write_text(render_mobile_report_html(report), encoding="utf-8")
        write_json(assets.notes, {"overrides": []})

        return GeneratedReport(report=report, validation=validation, assets=assets)
