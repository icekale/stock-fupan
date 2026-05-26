from app.watchlist.parser import parse_watchlist_text


def test_parse_watchlist_text_normalizes_common_a_share_codes() -> None:
    result = parse_watchlist_text(
        "600000\n000001\n300750\n688001\n430001\n",
        source_name="manual.txt",
    )

    assert [item.symbol for item in result.items] == [
        "600000.SH",
        "000001.SZ",
        "300750.SZ",
        "688001.SH",
        "430001.BJ",
    ]
    assert result.warnings == []


def test_parse_watchlist_text_accepts_suffixes_and_removes_duplicates() -> None:
    result = parse_watchlist_text(
        "SH600000, 600000.SH, sz000001, 000001.SZ, BJ430001",
        source_name="paste.txt",
    )

    assert [item.symbol for item in result.items] == ["600000.SH", "000001.SZ", "430001.BJ"]


def test_parse_watchlist_text_reads_csv_names() -> None:
    result = parse_watchlist_text(
        "代码,名称\n600000,浦发银行\n000001,平安银行\n",
        source_name="ths.csv",
    )

    assert [(item.symbol, item.name) for item in result.items] == [
        ("600000.SH", "浦发银行"),
        ("000001.SZ", "平安银行"),
    ]


def test_parse_watchlist_text_returns_warnings_for_invalid_tokens() -> None:
    result = parse_watchlist_text("600000\nabc123\n12345\n", source_name="manual.txt")

    assert [item.symbol for item in result.items] == ["600000.SH"]
    assert "abc123" in result.warnings[0]
    assert "12345" in result.warnings[1]
