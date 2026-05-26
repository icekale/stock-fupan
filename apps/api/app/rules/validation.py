import re
from dataclasses import dataclass

from app.schemas.report import ReportDTO


@dataclass(frozen=True)
class ValidationResult:
    is_valid: bool
    errors: list[str]


def _narrative_text(report: ReportDTO) -> str:
    narrative = report.narrative
    parts = [
        narrative.conclusion,
        narrative.overview,
        *narrative.sector_commentary,
        *narrative.watchlist,
        narrative.tomorrow,
        *narrative.risks,
    ]
    return "\n".join(parts)


def _allowed_numbers(report: ReportDTO) -> set[str]:
    values = {
        str(report.breadth.up_count),
        str(report.breadth.down_count),
        str(report.breadth.limit_up_count),
        str(report.breadth.limit_down_count),
        f"{report.turnover_cny:g}",
        f"{report.turnover_cny:.2f}",
    }
    for index in report.indices:
        values.add(f"{index.close:g}")
        values.add(f"{index.close:.2f}")
        values.add(f"{index.pct_change:g}")
        values.add(f"{index.pct_change:.2f}")
    for sector in report.sectors:
        values.add(f"{sector.pct_change:g}")
        values.add(f"{sector.pct_change:.2f}")
        values.add(f"{sector.score:g}")
        values.add(f"{sector.score:.2f}")
        values.add(str(sector.rank))
        for stock in sector.top_stocks:
            values.add(f"{stock.pct_change:g}")
            values.add(f"{stock.pct_change:.2f}")
            if stock.turnover_cny is not None:
                values.add(f"{stock.turnover_cny:g}")
                values.add(f"{stock.turnover_cny:.2f}")
    return values


def validate_narrative_facts(report: ReportDTO) -> ValidationResult:
    text = _narrative_text(report)
    errors: list[str] = []
    known_sector_names = {sector.name for sector in report.sectors}

    for sector_name in ["机器人", "PCB", "电力", "新能源", "半导体", "低空经济"]:
        if sector_name in text and sector_name not in known_sector_names:
            errors.append(f"unknown sector: {sector_name}")

    allowed_numbers = _allowed_numbers(report)
    numbers = re.findall(r"(?<![A-Za-z0-9])\d+(?:\.\d+)?(?![A-Za-z0-9])", text)
    for number in numbers:
        normalized = number.rstrip("0").rstrip(".") if "." in number else number
        if number not in allowed_numbers and normalized not in allowed_numbers:
            errors.append(f"unknown number: {number}")

    return ValidationResult(is_valid=not errors, errors=errors)
