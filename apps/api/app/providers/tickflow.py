from typing import Any, Protocol

import httpx
from pydantic import BaseModel

from app.providers.market import MarketBreadth, MarketCloseSnapshot, ProviderFallbackError, ProviderStatus
from app.providers.ths_concepts import ThsConceptBoardProvider
from app.rules.scoring import RawSectorInput
from app.schemas.report import IndexSnapshot


DEFAULT_MARKET_SYMBOLS = ["600000.SH", "000001.SZ", "300750.SZ", "002594.SZ", "601318.SH"]
INDEX_SYMBOLS = ["000001.SH", "399006.SZ"]
FULL_MARKET_UNIVERSE = "CN_Equity_A"
TOP_STRONG_QUOTES = 80
MIN_STRONG_QUOTE_PCT = 5.0
THEME_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("存储芯片", ("存储", "佰维", "德明利", "兆易", "江波龙", "普冉", "东芯")),
    ("先进封装", ("先进封装", "封装", "封测", "长电", "通富", "华天", "甬矽", "晶方")),
    ("PCB", ("生益", "沪电", "胜宏", "景旺", "深南", "鹏鼎", "东山", "世运", "方正科技")),
    ("半导体", ("芯", "半导体", "晶", "微", "中芯")),
    ("新材料", ("新材", "材料", "纳米", "复材", "碳", "膜")),
    ("环保", ("环保", "复洁", "清源", "水务", "节能", "固废")),
    ("机器人", ("机器人", "智能", "自动化", "精工", "机电", "伺服")),
    ("有色金属", ("黄金", "铜", "铝", "钴", "锂", "钼", "稀土", "有色", "贵金属")),
    ("电力设备", ("输变电", "电网", "特锐德", "思源电气", "中国西电", "金盘科技", "三变科技")),
    ("电力", ("电力", "电网", "能源", "发电", "核电", "风电")),
)


class WatchlistQuote(BaseModel):
    symbol: str
    name: str | None = None
    last_price: float | None = None
    pct_change: float | None = None
    turnover_cny: float | None = None
    turnover_rate: float | None = None
    capital_strength: str | None = None
    volume: float | None = None
    quote_time: str | None = None


class TickFlowQuoteProvider(Protocol):
    def get_quotes(self, symbols: list[str]) -> list[WatchlistQuote]:
        raise NotImplementedError


class FakeTickFlowProvider:
    provider_name = "fake_tickflow"

    def get_quotes(self, symbols: list[str]) -> list[WatchlistQuote]:
        fake_names = {"600000.SH": "浦发银行", "000001.SZ": "平安银行", "300750.SZ": "宁德时代"}
        return [
            WatchlistQuote(
                symbol=symbol,
                name=fake_names.get(symbol),
                last_price=10.0 + index,
                pct_change=2.5 - index,
                turnover_cny=100000000 + index * 1000000,
                volume=10000 + index,
                quote_time="2026-05-26T15:00:00+08:00",
            )
            for index, symbol in enumerate(symbols)
        ]


class TickFlowProvider:
    provider_name = "tickflow"

    def __init__(
        self,
        api_key: str,
        base_url: str,
        timeout_seconds: float = 12,
        http_client: object | None = None,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self._owns_client = http_client is None
        self.http_client = http_client or httpx.Client()

    def close(self) -> None:
        if self._owns_client:
            self.http_client.close()

    def get_quotes(self, symbols: list[str]) -> list[WatchlistQuote]:
        if not symbols:
            return []
        if not self.api_key:
            raise ProviderFallbackError("TICKFLOW_API_KEY 未配置")
        try:
            response = self.http_client.post(
                f"{self.base_url}/v1/quotes",
                headers={"x-api-key": self.api_key},
                json={"symbols": symbols},
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
        except httpx.TimeoutException as exc:
            raise ProviderFallbackError("TickFlow 请求超时") from exc
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code if exc.response is not None else None
            raise ProviderFallbackError(_safe_status_error(status_code)) from exc
        except Exception as exc:
            raise ProviderFallbackError(f"TickFlow 请求失败: {exc.__class__.__name__}") from exc
        return [_quote_from_item(item) for item in _extract_items(payload)]

    def get_universe_quotes(self, universe_id: str) -> list[WatchlistQuote]:
        if not self.api_key:
            raise ProviderFallbackError("TICKFLOW_API_KEY 未配置")
        try:
            response = self.http_client.get(
                f"{self.base_url}/v1/quotes",
                headers={"x-api-key": self.api_key},
                params={"universes": universe_id},
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
        except httpx.TimeoutException as exc:
            raise ProviderFallbackError("TickFlow 请求超时") from exc
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code if exc.response is not None else None
            raise ProviderFallbackError(_safe_status_error(status_code)) from exc
        except Exception as exc:
            raise ProviderFallbackError(f"TickFlow 请求失败: {exc.__class__.__name__}") from exc
        return [_quote_from_item(item) for item in _extract_items(payload)]

class TickFlowMarketDataProvider:
    provider_name = "tickflow"

    def __init__(
        self,
        api_key: str,
        base_url: str,
        symbols: list[str] | None = None,
        timeout_seconds: float = 12,
        http_client: object | None = None,
        concept_provider: ThsConceptBoardProvider | None = None,
    ) -> None:
        self.quote_provider = TickFlowProvider(
            api_key=api_key,
            base_url=base_url,
            timeout_seconds=timeout_seconds,
            http_client=http_client,
        )
        self.symbols = symbols or DEFAULT_MARKET_SYMBOLS
        self._sector_frontline_stocks: dict[str, list[WatchlistQuote]] = {}
        self.concept_provider = concept_provider or ThsConceptBoardProvider()

    def close(self) -> None:
        self.quote_provider.close()
        self.concept_provider.close()

    def get_close_snapshot(self, trade_date: str) -> MarketCloseSnapshot:
        market_quotes = self.quote_provider.get_universe_quotes(FULL_MARKET_UNIVERSE)
        indices = _indices_from_quotes(market_quotes)
        if len(indices) < len(INDEX_SYMBOLS):
            indices = _indices_from_quotes([*market_quotes, *self.quote_provider.get_quotes(INDEX_SYMBOLS)])
        equity_quotes = _tradable_equity_quotes(market_quotes)
        quoted_changes = [quote.pct_change for quote in equity_quotes if quote.pct_change is not None]
        if not indices or not quoted_changes:
            raise ProviderFallbackError("TickFlow 行情数据不足")
        turnover_cny = round(
            sum(quote.turnover_cny or 0 for quote in equity_quotes) / 100_000_000,
            2,
        )
        raw_sectors = self._strong_sectors_from_market(equity_quotes, trade_date=trade_date)
        if not raw_sectors:
            raise ProviderFallbackError("TickFlow 未返回可排序标的")
        return MarketCloseSnapshot(
            trade_date=trade_date,
            indices=indices,
            breadth=MarketBreadth(
                up_count=sum(1 for change in quoted_changes if change > 0),
                down_count=sum(1 for change in quoted_changes if change < 0),
                limit_up_count=sum(1 for change in quoted_changes if change >= 9.8),
                limit_down_count=sum(1 for change in quoted_changes if change <= -9.8),
            ),
            turnover_cny=turnover_cny,
            market_state_tags=_market_tags(quoted_changes, turnover_cny),
            raw_sectors=raw_sectors,
        )

    def get_sector_frontline_stocks(self, sector_name: str) -> list[WatchlistQuote]:
        return list(self._sector_frontline_stocks.get(sector_name, []))

    def _strong_sectors_from_market(
        self,
        equity_quotes: list[WatchlistQuote],
        trade_date: str | None = None,
    ) -> list[RawSectorInput]:
        self._sector_frontline_stocks = {}
        strong_quotes = _strong_quotes(equity_quotes, top_n=TOP_STRONG_QUOTES)
        themed = _sectors_from_theme_quotes(strong_quotes)
        self._sector_frontline_stocks = _frontline_stocks_from_theme_quotes(strong_quotes)
        concept_sectors = self._refine_theme_frontline_stocks_with_concepts(
            equity_quotes,
            strong_quotes,
            trade_date=trade_date,
        )
        if themed and concept_sectors:
            themed = _replace_theme_sectors_with_concepts(themed, concept_sectors)
        return themed or _sectors_from_quotes(strong_quotes)

    def _refine_theme_frontline_stocks_with_concepts(
        self,
        equity_quotes: list[WatchlistQuote],
        strong_quotes: list[WatchlistQuote],
        trade_date: str | None = None,
    ) -> dict[str, RawSectorInput]:
        concept_sectors: dict[str, RawSectorInput] = {}
        for theme, theme_quotes in _group_quotes_by_theme(strong_quotes).items():
            sector_quotes = [quote for quote in equity_quotes if _quote_matches_theme(quote, theme)]
            if not sector_quotes:
                sector_quotes = theme_quotes
            concept_sector = self.concept_provider.build_sector_input(
                theme,
                sector_quotes,
                trade_date=trade_date,
            )
            if concept_sector is not None:
                concept_sectors[theme] = concept_sector
                self._sector_frontline_stocks[concept_sector.name] = _rank_frontline_stocks(sector_quotes)
        return concept_sectors


class FallbackTickFlowProvider:
    def __init__(
        self,
        primary: TickFlowQuoteProvider,
        fallback: TickFlowQuoteProvider,
        fallback_enabled: bool = True,
    ) -> None:
        self.primary = primary
        self.fallback = fallback
        self.fallback_enabled = fallback_enabled

    def get_quotes(self, symbols: list[str]) -> list[WatchlistQuote]:
        quotes, _status = self.get_quotes_with_status(symbols)
        return quotes

    def get_quotes_with_status(self, symbols: list[str]) -> tuple[list[WatchlistQuote], ProviderStatus]:
        try:
            quotes = self.primary.get_quotes(symbols)
        except Exception as exc:
            reason = str(exc) or exc.__class__.__name__
            if not self.fallback_enabled:
                raise
            return self.fallback.get_quotes(symbols), ProviderStatus(
                provider="tickflow",
                status="fallback",
                fallback_used=True,
                reason=reason,
            )
        return quotes, ProviderStatus(
            provider="tickflow",
            status="success",
            fallback_used=False,
            reason=None,
        )


def _extract_items(payload: object) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        if "data" in payload:
            data = payload["data"]
        elif "items" in payload:
            data = payload["items"]
        else:
            data = payload.get("results")
    else:
        data = payload
    if not isinstance(data, list):
        raise ProviderFallbackError("TickFlow 响应结构异常")
    return [item for item in data if isinstance(item, dict)]


def _extract_single_item(payload: object) -> dict[str, Any]:
    if isinstance(payload, dict):
        if "data" in payload:
            data = payload["data"]
        elif "item" in payload:
            data = payload["item"]
        else:
            data = payload
    else:
        data = payload
    if not isinstance(data, dict):
        raise ProviderFallbackError("TickFlow 响应结构异常")
    return data


def _quote_from_item(item: dict[str, Any]) -> WatchlistQuote:
    symbol = str(item.get("symbol") or item.get("ticker") or item.get("code") or "")
    if not symbol:
        raise ProviderFallbackError("TickFlow 响应缺少 symbol")
    ext = item.get("ext")
    ext_item = ext if isinstance(ext, dict) else {}
    change_pct = (
        item.get("pct_change")
        or item.get("change_percent")
        or item.get("percent")
        or ext_item.get("change_pct")
    )
    pct_change = _optional_float(change_pct)
    if pct_change is not None and abs(pct_change) <= 1:
        pct_change = pct_change * 100
    turnover_rate = _optional_float(item.get("turnover_rate") or ext_item.get("turnover_rate"))
    if turnover_rate is not None and abs(turnover_rate) <= 1:
        turnover_rate = turnover_rate * 100
    turnover_cny = _optional_float(item.get("turnover_cny") or item.get("turnover") or item.get("amount"))
    return WatchlistQuote(
        symbol=symbol,
        name=_optional_str(item.get("name") or ext_item.get("name")),
        last_price=_optional_float(item.get("last_price") or item.get("price") or item.get("last")),
        pct_change=pct_change,
        turnover_cny=turnover_cny,
        turnover_rate=turnover_rate,
        capital_strength=_capital_strength_label(turnover_cny, turnover_rate, pct_change),
        volume=_optional_float(item.get("volume")),
        quote_time=_optional_str(item.get("quote_time") or item.get("time") or item.get("timestamp")),
    )


def _indices_from_quotes(quotes: list[WatchlistQuote]) -> list[IndexSnapshot]:
    index_names = {"000001.SH": "上证指数", "399006.SZ": "创业板指"}
    results: list[IndexSnapshot] = []
    for quote in quotes:
        if quote.symbol not in index_names or quote.last_price is None or quote.pct_change is None:
            continue
        results.append(
            IndexSnapshot(
                name=quote.name or index_names[quote.symbol],
                code=quote.symbol.split(".")[0],
                close=quote.last_price,
                pct_change=quote.pct_change,
            )
        )
    return results


def _tradable_equity_quotes(quotes: list[WatchlistQuote]) -> list[WatchlistQuote]:
    return [
        quote
        for quote in quotes
        if quote.symbol not in set(INDEX_SYMBOLS)
        and quote.pct_change is not None
        and quote.turnover_cny is not None
        and _is_mainland_regular_equity(quote)
    ]


def _is_mainland_regular_equity(quote: WatchlistQuote) -> bool:
    if quote.symbol.endswith(".BJ"):
        return False
    name = quote.name or ""
    return "ST" not in name.upper()


def _strong_quotes(quotes: list[WatchlistQuote], top_n: int) -> list[WatchlistQuote]:
    candidates = [quote for quote in quotes if (quote.pct_change or 0) >= MIN_STRONG_QUOTE_PCT]
    if not candidates:
        candidates = quotes
    ranked = sorted(
        candidates,
        key=lambda quote: ((quote.pct_change or 0), (quote.turnover_cny or 0)),
        reverse=True,
    )
    return ranked[:top_n]


def _sectors_from_quotes(quotes: list[WatchlistQuote]) -> list[RawSectorInput]:
    ranked = sorted(
        [quote for quote in quotes if quote.pct_change is not None],
        key=lambda quote: quote.pct_change or 0,
        reverse=True,
    )
    return [
        RawSectorInput(
            name=quote.name or quote.symbol,
            pct_change=quote.pct_change or 0,
            limit_up_count=1 if (quote.pct_change or 0) >= 9.8 else 0,
            stock_up_ratio=1.0 if (quote.pct_change or 0) > 0 else 0.0,
            turnover_change=0.0,
            news_weight=min(max(abs(quote.pct_change or 0) / 8, 0.0), 1.0),
        )
        for quote in ranked[:10]
    ]


def _sectors_from_theme_quotes(quotes: list[WatchlistQuote]) -> list[RawSectorInput]:
    grouped: dict[str, list[WatchlistQuote]] = {}
    for quote in quotes:
        theme = _theme_for_quote(quote)
        if theme is not None:
            grouped.setdefault(theme, []).append(quote)

    sectors = [_sector_from_group(theme, theme_quotes) for theme, theme_quotes in grouped.items()]
    return sorted(
        [sector for sector in sectors if sector is not None],
        key=lambda sector: (sector.limit_up_count, sector.pct_change, sector.stock_up_ratio),
        reverse=True,
    )[:10]


def _group_quotes_by_theme(quotes: list[WatchlistQuote]) -> dict[str, list[WatchlistQuote]]:
    grouped: dict[str, list[WatchlistQuote]] = {}
    for quote in quotes:
        theme = _theme_for_quote(quote)
        if theme is not None:
            grouped.setdefault(theme, []).append(quote)
    return grouped


def _quote_matches_theme(quote: WatchlistQuote, theme: str) -> bool:
    name = quote.name or quote.symbol
    return any(alias in name for alias in _theme_aliases(theme))


def _frontline_stocks_from_theme_quotes(quotes: list[WatchlistQuote]) -> dict[str, list[WatchlistQuote]]:
    grouped: dict[str, list[WatchlistQuote]] = {}
    for quote in quotes:
        theme = _theme_for_quote(quote)
        if theme is not None:
            grouped.setdefault(theme, []).append(quote)
    return {
        theme: _rank_frontline_stocks(theme_quotes)
        for theme, theme_quotes in grouped.items()
    }


def _rank_frontline_stocks(quotes: list[WatchlistQuote]) -> list[WatchlistQuote]:
    candidates = [
        quote
        for quote in quotes
        if quote.pct_change is not None and _is_mainland_regular_equity(quote)
    ]
    ranked = sorted(
        candidates,
        key=lambda quote: ((quote.pct_change or 0), (quote.turnover_cny or 0)),
        reverse=True,
    )
    return [_with_capital_strength(quote) for quote in ranked[:8]]


def _with_capital_strength(quote: WatchlistQuote) -> WatchlistQuote:
    return quote.model_copy(
        update={
            "capital_strength": quote.capital_strength
            or _capital_strength_label(quote.turnover_cny, quote.turnover_rate, quote.pct_change)
        }
    )


def _theme_for_quote(quote: WatchlistQuote) -> str | None:
    name = quote.name or quote.symbol
    for theme, keywords in THEME_KEYWORDS:
        if any(keyword in name for keyword in keywords):
            return theme
    return None


def _theme_aliases(theme: str) -> tuple[str, ...]:
    aliases = {
        "存储芯片": ("存储芯片", "存储", "半导体存储"),
        "先进封装": ("先进封装", "封装", "封测"),
        "PCB": ("PCB", "印制电路板"),
        "半导体": ("半导体", "芯片", "封装", "封测", "集成电路"),
        "新材料": ("新材料", "材料", "培育钻石", "复合材料"),
        "环保": ("环保", "节能环保", "水务", "固废", "污水"),
        "机器人": ("机器人", "人形机器人", "自动化", "伺服", "工业母机"),
        "有色金属": ("有色金属", "贵金属", "黄金", "铜", "铝", "锂", "稀土", "小金属"),
        "电力设备": ("电力设备", "智能电网", "输变电", "电网设备", "特高压"),
        "电力": ("电力", "风电", "光伏", "核电", "发电", "火电"),
    }
    return aliases.get(theme, (theme,))


def _sector_from_group(theme: str, quotes: list[WatchlistQuote]) -> RawSectorInput | None:
    if not quotes:
        return None
    changes = [quote.pct_change or 0 for quote in quotes if quote.pct_change is not None]
    if not changes:
        return None
    turnover_values = [quote.turnover_cny or 0 for quote in quotes]
    avg_change = sum(changes) / len(changes)
    limit_up_count = sum(1 for change in changes if change >= 9.8)
    up_ratio = sum(1 for change in changes if change > 0) / len(changes)
    return RawSectorInput(
        name=theme,
        pct_change=avg_change,
        limit_up_count=limit_up_count,
        stock_up_ratio=up_ratio,
        turnover_change=min(sum(turnover_values) / 10_000_000_000, 1.0),
        news_weight=min(max((limit_up_count * 0.25) + (avg_change / 20), 0.0), 1.0),
    )


def _replace_theme_sectors_with_concepts(
    sectors: list[RawSectorInput],
    concept_sectors: dict[str, RawSectorInput],
) -> list[RawSectorInput]:
    output: list[RawSectorInput] = []
    for sector in sectors:
        output.append(concept_sectors.get(sector.name, sector))
    return sorted(
        output,
        key=lambda sector: (sector.limit_up_count, sector.pct_change, sector.stock_up_ratio),
        reverse=True,
    )[:10]


def _market_tags(changes: list[float], turnover_cny: float) -> list[str]:
    up_count = sum(1 for change in changes if change > 0)
    down_count = sum(1 for change in changes if change < 0)
    if up_count > down_count * 1.5:
        breadth = "普涨"
    elif down_count > up_count * 1.5:
        breadth = "普跌"
    else:
        breadth = "分化"
    return [breadth, "放量" if turnover_cny >= 10000 else "缩量"]


def _optional_str(value: object) -> str | None:
    return str(value) if value is not None and str(value) else None


def _optional_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _capital_strength_label(
    turnover_cny: float | None,
    turnover_rate: float | None,
    pct_change: float | None,
) -> str | None:
    if turnover_cny is None and turnover_rate is None:
        return None
    turnover_yi = (turnover_cny or 0) / 100_000_000
    rate = turnover_rate or 0
    change = pct_change or 0
    if turnover_yi >= 30 and rate >= 20 and change >= 5:
        return "高换手强承接"
    if turnover_yi >= 10 or (rate >= 8 and change >= 5):
        return "强"
    if turnover_yi >= 3 or rate >= 5:
        return "温和放量"
    if rate >= 25 and change < 5:
        return "高换手分歧"
    return "一般"


def _safe_status_error(status_code: object) -> str:
    return "TickFlow HTTP 请求失败" if status_code is None else f"TickFlow HTTP {status_code}"
