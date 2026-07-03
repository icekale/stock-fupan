from __future__ import annotations

from copy import deepcopy
from typing import Protocol

from app.services.morning_auction.schemas import AuctionSnapshot, DailyBar


class MorningAuctionDataSource(Protocol):
    def candidate_universe(self, trade_date: str) -> list[dict[str, object]]:
        ...

    def daily_bars(self, symbol: str, *, end_date: str, lookback: int) -> list[DailyBar]:
        ...

    def auction_snapshot(self, symbol: str, *, trade_date: str) -> AuctionSnapshot | None:
        ...

    def sector_strength(self, symbol: str, *, trade_date: str) -> float | None:
        ...

    def capital_strength(self, symbol: str, *, trade_date: str) -> float | None:
        ...


class InMemoryMorningAuctionDataSource:
    def __init__(
        self,
        *,
        universe: list[dict[str, object]],
        bars_by_symbol: dict[str, list[DailyBar]],
        auctions_by_key: dict[tuple[str, str], AuctionSnapshot],
        sector_by_key: dict[tuple[str, str], float] | None = None,
        capital_by_key: dict[tuple[str, str], float] | None = None,
    ) -> None:
        self._universe = deepcopy(universe)
        self._bars_by_symbol = deepcopy(bars_by_symbol)
        self._auctions_by_key = deepcopy(auctions_by_key)
        self._sector_by_key = dict(sector_by_key or {})
        self._capital_by_key = dict(capital_by_key or {})

    @classmethod
    def with_fixture(cls) -> InMemoryMorningAuctionDataSource:
        symbol = "600001.SH"
        trade_date = "2026-07-03"

        return cls(
            universe=[{"symbol": symbol, "name": "Fixture Stock"}],
            bars_by_symbol={
                symbol: [
                    DailyBar(
                        trade_date="2026-07-01",
                        open=9.8,
                        high=10.0,
                        low=9.7,
                        close=9.9,
                        volume=900_000,
                        amount=8_910_000,
                    ),
                    DailyBar(
                        trade_date="2026-07-02",
                        open=9.9,
                        high=10.1,
                        low=9.8,
                        close=10.0,
                        volume=950_000,
                        amount=9_500_000,
                    ),
                    DailyBar(
                        trade_date=trade_date,
                        open=10.1,
                        high=10.3,
                        low=9.9,
                        close=10.5,
                        volume=1_100_000,
                        amount=11_220_000,
                    ),
                ]
            },
            auctions_by_key={
                (symbol, trade_date): AuctionSnapshot(
                    trade_date=trade_date,
                    symbol=symbol,
                    name="Fixture Stock",
                    snapshot_time="09:25:00",
                    indicative_price=10.1,
                    prev_close=10.0,
                    auction_volume=1_000_000,
                    auction_amount=10_100_000,
                )
            },
            sector_by_key={(symbol, trade_date): 78.0},
            capital_by_key={(symbol, trade_date): 62.0},
        )

    def candidate_universe(self, trade_date: str) -> list[dict[str, object]]:
        return deepcopy(self._universe)

    def daily_bars(self, symbol: str, *, end_date: str, lookback: int) -> list[DailyBar]:
        if lookback <= 0:
            raise ValueError("lookback must be positive")

        bars = [bar for bar in self._bars_by_symbol.get(symbol, []) if bar.trade_date <= end_date]
        return deepcopy(bars[-lookback:])

    def auction_snapshot(self, symbol: str, *, trade_date: str) -> AuctionSnapshot | None:
        return deepcopy(self._auctions_by_key.get((symbol, trade_date)))

    def sector_strength(self, symbol: str, *, trade_date: str) -> float | None:
        return self._sector_by_key.get((symbol, trade_date))

    def capital_strength(self, symbol: str, *, trade_date: str) -> float | None:
        return self._capital_by_key.get((symbol, trade_date))
