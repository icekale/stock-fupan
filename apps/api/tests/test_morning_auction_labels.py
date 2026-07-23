from app.services.morning_auction.filters import evaluate_candidate_filters
from app.services.morning_auction.schemas import DailyBar, MorningAuctionSample


def test_sample_labels_use_open_to_close_return() -> None:
    sample = MorningAuctionSample(
        trade_date="2026-07-03",
        symbol="600001.SH",
        name="测试股份",
        features={"prev_return": 1.2},
        open_price=10.0,
        close_price=10.31,
    )

    assert sample.open_to_close_return == 0.031
    assert sample.main_label is True
    assert sample.strong_label is False
    assert sample.safe_label is True
    assert sample.risk_label is False


def test_sample_strong_and_risk_labels() -> None:
    strong = MorningAuctionSample(
        trade_date="2026-07-03",
        symbol="600002.SH",
        name="强势股份",
        features={},
        open_price=10.0,
        close_price=10.55,
    )
    risk = MorningAuctionSample(
        trade_date="2026-07-03",
        symbol="600003.SH",
        name="风险股份",
        features={},
        open_price=10.0,
        close_price=9.69,
    )

    assert strong.main_label is True
    assert strong.strong_label is True
    assert risk.safe_label is False
    assert risk.risk_label is True


def test_sample_labels_compare_raw_return_not_rounded_display_value() -> None:
    below_main = MorningAuctionSample(
        trade_date="2026-07-03",
        symbol="600004.SH",
        name="边界股份",
        features={},
        open_price=10.0,
        close_price=10.299996,
    )
    above_risk = MorningAuctionSample(
        trade_date="2026-07-03",
        symbol="600005.SH",
        name="风险边界",
        features={},
        open_price=10.0,
        close_price=9.700004,
    )

    assert below_main.open_to_close_return == 0.03
    assert below_main.main_label is False
    assert above_risk.open_to_close_return == -0.03
    assert above_risk.risk_label is False


def test_filters_reject_untradable_and_overheated_candidates() -> None:
    latest = DailyBar(
        trade_date="2026-07-02",
        open=10.0,
        high=10.3,
        low=9.8,
        close=10.2,
        volume=1_000_000,
        amount=20_000_000,
        turnover_rate=3.0,
    )

    accepted = evaluate_candidate_filters(
        symbol="600001.SH",
        name="正常股份",
        listed_days=300,
        is_st=False,
        is_suspended=False,
        auction_return=3.0,
        auction_amount=15_000_000,
        daily_bars=[latest],
    )
    rejected = evaluate_candidate_filters(
        symbol="600002.SH",
        name="过热股份",
        listed_days=300,
        is_st=False,
        is_suspended=False,
        auction_return=8.5,
        auction_amount=15_000_000,
        daily_bars=[latest],
    )

    assert accepted.passed is True
    assert accepted.risk_flags == []
    assert rejected.passed is False
    assert "竞价涨幅过高" in rejected.risk_flags


def test_filters_allow_missing_auction_for_cold_start_training() -> None:
    latest = DailyBar(
        trade_date="2026-07-02",
        open=10.0,
        high=10.3,
        low=9.8,
        close=10.2,
        volume=1_000_000,
        amount=20_000_000,
        turnover_rate=3.0,
    )

    result = evaluate_candidate_filters(
        symbol="600001.SH",
        name="冷启动股份",
        listed_days=300,
        is_st=False,
        is_suspended=False,
        auction_return=None,
        auction_amount=None,
        daily_bars=[latest],
        require_auction_data=False,
    )

    assert result.passed is True
    assert result.risk_flags == []
