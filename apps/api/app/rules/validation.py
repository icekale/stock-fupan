import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from app.schemas.report import ReportDTO


FACT_NUMBER_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])"
    r"(?P<number>[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?)"
    r"(?P<unit>万亿|亿元|％|%|只|家|亿|点)"
)
SECTOR_CANDIDATES = [
    "低空经济",
    "电力设备",
    "新能源",
    "半导体",
    "机器人",
    "PCB",
    "电力",
]
INDEX_PATTERN = re.compile(
    r"(?P<name>[\u4e00-\u9fffA-Za-z0-9]{1,12}?(?:指数|指))"
    r"(?=上涨|下跌|走强|回落|冲高|震荡|，|。|；|、|\s|$)"
)
STOCK_PATTERN = re.compile(
    r"(?P<name>[\u4e00-\u9fffA-Za-z0-9]{2,12}?"
    r"(?:股份|科技|电子|电力|能源|集团|证券|银行|药业|智能))"
    r"(?=涨停|涨幅|上涨|下跌|走强|回落|冲高|继续|承接|，|。|；|、|\s|$)"
)
ENTITY_PREFIXES = ("关注", "观察", "看好", "看", "对应", "代码", "以及", "和", "与")


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


def _to_decimal(value: int | float) -> Decimal:
    return Decimal(str(value))


def _parse_number(number: str) -> Decimal | None:
    try:
        return Decimal(number.replace(",", ""))
    except InvalidOperation:
        return None


def _number_for_error(number: str) -> str:
    normalized = number.replace(",", "")
    if normalized.startswith("+"):
        normalized = normalized[1:]
    if "." in normalized:
        normalized = normalized.rstrip("0").rstrip(".")
    return "0" if normalized in {"", "-0"} else normalized


def _add_money_values(values: set[Decimal], wan_yi_values: set[Decimal], value: float) -> None:
    yi_value = _to_decimal(value)
    values.add(yi_value)
    wan_yi_value = yi_value / Decimal("10000")
    wan_yi_values.add(wan_yi_value)
    wan_yi_values.add(wan_yi_value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _allowed_numbers_by_unit(report: ReportDTO) -> dict[str, set[Decimal]]:
    percent_values: set[Decimal] = set()
    count_values = {
        _to_decimal(report.breadth.up_count),
        _to_decimal(report.breadth.down_count),
        _to_decimal(report.breadth.limit_up_count),
        _to_decimal(report.breadth.limit_down_count),
    }
    point_values: set[Decimal] = set()
    money_yi_values: set[Decimal] = set()
    money_wan_yi_values: set[Decimal] = set()

    _add_money_values(money_yi_values, money_wan_yi_values, report.turnover_cny)
    for index in report.indices:
        point_values.add(_to_decimal(index.close))
        percent_values.add(_to_decimal(index.pct_change))
    for sector in report.sectors:
        percent_values.add(_to_decimal(sector.pct_change))
        for stock in sector.top_stocks:
            percent_values.add(_to_decimal(stock.pct_change))
            if stock.turnover_cny is not None:
                _add_money_values(money_yi_values, money_wan_yi_values, stock.turnover_cny)

    return {
        "%": percent_values,
        "％": percent_values,
        "只": count_values,
        "家": count_values,
        "亿元": money_yi_values,
        "亿": money_yi_values,
        "万亿": money_wan_yi_values,
        "点": point_values,
    }


def _add_error(errors: list[str], seen_errors: set[str], error: str) -> None:
    if error not in seen_errors:
        errors.append(error)
        seen_errors.add(error)


def _overlaps_existing(span: tuple[int, int], occupied_spans: list[tuple[int, int]]) -> bool:
    start, end = span
    return any(start < occupied_end and end > occupied_start for occupied_start, occupied_end in occupied_spans)


def _validate_sector_mentions(
    text: str,
    known_sector_names: set[str],
    errors: list[str],
    seen_errors: set[str],
) -> None:
    occupied_spans: list[tuple[int, int]] = []
    for sector_name in sorted(SECTOR_CANDIDATES, key=len, reverse=True):
        for match in re.finditer(re.escape(sector_name), text):
            if _overlaps_existing(match.span(), occupied_spans):
                continue
            occupied_spans.append(match.span())
            if sector_name not in known_sector_names:
                _add_error(errors, seen_errors, f"unknown sector: {sector_name}")


def _trim_entity_prefix(name: str) -> str:
    for prefix in ENTITY_PREFIXES:
        if name.startswith(prefix) and len(name) > len(prefix):
            return name[len(prefix) :]
    return name


def _known_stock_values(report: ReportDTO) -> set[str]:
    values: set[str] = set()
    for sector in report.sectors:
        for stock in sector.top_stocks:
            values.add(stock.name)
            values.add(stock.code)
    return values


def _validate_index_mentions(
    text: str,
    report: ReportDTO,
    errors: list[str],
    seen_errors: set[str],
) -> None:
    known_index_values = {value for index in report.indices for value in (index.name, index.code)}
    for match in INDEX_PATTERN.finditer(text):
        index_name = _trim_entity_prefix(match.group("name"))
        if index_name not in known_index_values:
            _add_error(errors, seen_errors, f"unknown index: {index_name}")


def _validate_stock_mentions(
    text: str,
    report: ReportDTO,
    known_sector_names: set[str],
    errors: list[str],
    seen_errors: set[str],
) -> None:
    known_stock_values = _known_stock_values(report)
    sector_vocabulary = set(SECTOR_CANDIDATES) | known_sector_names
    for match in STOCK_PATTERN.finditer(text):
        stock_name = _trim_entity_prefix(match.group("name"))
        if stock_name in sector_vocabulary or stock_name in known_stock_values:
            continue
        _add_error(errors, seen_errors, f"unknown stock: {stock_name}")


def _validate_fact_numbers(text: str, report: ReportDTO, errors: list[str], seen_errors: set[str]) -> None:
    allowed_numbers = _allowed_numbers_by_unit(report)
    for match in FACT_NUMBER_PATTERN.finditer(text):
        value = _parse_number(match.group("number"))
        if value is None:
            continue
        unit = match.group("unit")
        if value not in allowed_numbers[unit]:
            _add_error(errors, seen_errors, f"unknown number: {_number_for_error(match.group('number'))}")


def validate_narrative_facts(report: ReportDTO) -> ValidationResult:
    text = _narrative_text(report)
    errors: list[str] = []
    seen_errors: set[str] = set()
    known_sector_names = {sector.name for sector in report.sectors}

    _validate_sector_mentions(text, known_sector_names, errors, seen_errors)
    _validate_fact_numbers(text, report, errors, seen_errors)
    _validate_index_mentions(text, report, errors, seen_errors)
    _validate_stock_mentions(text, report, known_sector_names, errors, seen_errors)

    return ValidationResult(is_valid=not errors, errors=errors)
