from __future__ import annotations

import re


def summarize_catalysts(
    values: list[str],
    max_items: int = 2,
    max_length: int = 36,
    sector_name: str = "",
    trade_date: str | None = None,
    llm_provider: object | None = None,
) -> list[str]:
    fallback = "消息面仅作观察，缺少明确催化"
    filtered_values = _filter_effective_window(values, trade_date)
    ai_result = _ai_summary(
        values=filtered_values,
        max_items=max_items,
        max_length=max_length,
        sector_name=sector_name,
        llm_provider=llm_provider,
    )
    if ai_result:
        return ai_result
    summaries: list[str] = []
    for text in _candidate_summaries(filtered_values, max_length=max_length):
        if text and text not in summaries:
            summaries.append(text)
        if len(summaries) >= max_items:
            break
    return summaries or ([fallback] if values else [])


def _filter_effective_window(values: list[str], trade_date: str | None) -> list[str]:
    if not trade_date:
        return values
    trade_marker = int(trade_date.replace("-", ""))
    previous_marker = _previous_day_marker(trade_date)
    output: list[str] = []
    for value in values:
        text = str(value)
        dates = _date_markers(text)
        if not dates:
            if _looks_like_realtime_review(text):
                output.append(value)
            continue
        if any(marker > trade_marker for marker in dates):
            continue
        if any(marker in {trade_marker, previous_marker} for marker in dates):
            output.append(value)
    return output


def _previous_day_marker(trade_date: str) -> int:
    match = re.match(r"(\d{4})-(\d{2})-(\d{2})$", trade_date)
    if not match:
        return 0
    from datetime import date, timedelta

    year, month, day = (int(part) for part in match.groups())
    return int((date(year, month, day) - timedelta(days=1)).strftime("%Y%m%d"))


def _date_markers(text: str) -> set[int]:
    markers: set[int] = set()
    for year, month, day in re.findall(r"(20\d{2})[-/年](\d{1,2})[-/月](\d{1,2})", text):
        markers.add(int(f"{int(year):04d}{int(month):02d}{int(day):02d}"))
    return markers


def _looks_like_realtime_review(text: str) -> bool:
    return "THSDK问财" in text or "复盘确认" in text or "今日" in text


def _evidence_priority(value: str) -> int:
    text = str(value)
    if "THSDK问财" in text:
        return 0
    if "复盘" in text or "确认" in text:
        return 1
    if "涨停" in text or "连板" in text:
        return 2
    return 3


def _ai_summary(
    values: list[str],
    max_items: int,
    max_length: int,
    sector_name: str,
    llm_provider: object | None,
) -> list[str]:
    summarize = getattr(llm_provider, "summarize_catalysts", None)
    if not callable(summarize):
        return []
    try:
        result = summarize(sector_name, values)
    except Exception:
        return []
    if not isinstance(result, list):
        return []
    output: list[str] = []
    for item in result:
        text = _truncate(" ".join(str(item).split()).strip(), max_length)
        if not _is_complete_summary(text):
            continue
        if text and text not in output:
            output.append(text)
        if len(output) >= max_items:
            break
    return output


def _is_complete_summary(text: str) -> bool:
    if not text:
        return False
    if text.count("'") % 2 or text.count('"') % 2:
        return False
    incomplete_suffixes = ("资金支", "的全", "形成", "提供", "带动", "受益于", "+")
    if text.endswith(incomplete_suffixes):
        return False
    if len(text) < 8:
        return False
    return True


def _candidate_summaries(values: list[str], max_length: int) -> list[str]:
    output: list[str] = []
    for value in sorted(values, key=_evidence_priority):
        text = " ".join(str(value).split()).strip()
        if "THSDK问财" in text:
            output.append(_summarize_thsdk_note(text))
            continue
        text = _prepare_news_text(text)
        if not text or _is_weak_headline(text):
            continue
        output.extend(_extract_logic_points(text, max_length=max_length))
    return output


def _summarize_one(value: str, max_length: int) -> str:
    text = " ".join(str(value).split()).strip()
    if not text:
        return ""
    if "THSDK问财" in text:
        return _summarize_thsdk_note(text)
    text = _prepare_news_text(text)
    if _is_weak_headline(text):
        return ""
    points = _extract_logic_points(text, max_length=max_length)
    if points:
        return points[0]
    return _truncate(text, max_length)


def _prepare_news_text(text: str) -> str:
    text = _strip_source_prefix(text)
    text = _strip_news_noise(text)
    text = _keep_first_clause(text)
    return _compress_stock_chain(text)


def _extract_logic_points(text: str, max_length: int) -> list[str]:
    cleaned = _remove_headline_noise(text)
    points: list[str] = []
    for point in _extract_composite_logic_points(cleaned):
        if point not in points:
            points.append(_truncate(point, min(max_length, 24)))
    for pattern in (
        r"(AI服务器升级打开产业空间)",
        r"(算电协同[^，,。；;]{0,10})",
        r"(用电负荷[^，,。；;]{0,12})",
        r"(政策[^，,。；;]{0,12})",
        r"(订单[^，,。；;]{0,12})",
        r"(业绩[^，,。；;]{0,12})",
        r"(多股涨停[，,]资金回流)",
        r"(多股涨停[^，,。；;]{0,8})",
        r"(资金[^，,。；;]{0,10})",
        r"(\d+只[^，,。；;]{0,12}创新高)",
        r"((?:先进封装|存储芯片|PCB|电力|半导体|环保|新材料)[^，,。；;]{0,12}活跃)",
    ):
        match = re.search(pattern, cleaned)
        if not match:
            continue
        point = _normalize_logic_point(match.group(1))
        if _is_weaker_duplicate_point(point, points):
            continue
        point = _truncate(point, min(max_length, 24))
        if not _is_complete_summary(point):
            continue
        if point and point not in points:
            points.append(point)
    fallback = _truncate(cleaned, max_length) if cleaned else ""
    return points or ([fallback] if _is_complete_summary(fallback) else [])


def _extract_composite_logic_points(text: str) -> list[str]:
    points: list[str] = []
    if "政策" in text and any(term in text for term in ("顶层设计", "税收优惠", "全方位支撑")):
        if "国产替代" in text and ("AI" in text or "算力" in text):
            points.append("政策全方位支撑，国产替代与AI需求共振")
        else:
            points.append("政策全方位支撑，观察产业兑现")
    return points


def _is_weaker_duplicate_point(point: str, existing_points: list[str]) -> bool:
    if point == "多股涨停，观察前排承接":
        return any("多股涨停" in item and "资金回流" in item for item in existing_points)
    if point.startswith("资金回流"):
        return any("资金回流" in item for item in existing_points)
    return False


def _remove_headline_noise(text: str) -> str:
    text = re.sub(r"^A股[：:，, ]*", "", text)
    text = re.sub(r"^[^，,。；;]{0,18}概念股强势\s*", "", text)
    text = text.replace("资金持续回流", "资金回流")
    return text.strip(" ，,。")


def _normalize_logic_point(text: str) -> str:
    text = text.strip(" ，,。")
    text = text.replace("资金持续回流", "资金回流")
    text = text.replace("等多股涨停，资金回流", "多股涨停，资金回流")
    if "多股涨停" in text and "资金回流" in text:
        return "多股涨停，资金回流，前排强度明确"
    if "多股涨停" in text and "资金回流" not in text:
        return "多股涨停，观察前排承接"
    if text == "AI服务器升级打开产业空间":
        return "AI服务器升级打开产业空间，PCB获资金确认"
    return text


def _is_weak_headline(text: str) -> bool:
    return _is_generic_listicle(text) or _is_market_noise_headline(text)


def _is_generic_listicle(text: str) -> bool:
    generic_terms = (
        "龙头股名单",
        "股票名录",
        "概念上市公司",
        "上市公司股票",
        "有哪些",
        "一览",
        "请收藏",
        "有望翻倍",
    )
    return any(term in text for term in generic_terms) and not any(
        term in text for term in ("涨停", "连板", "资金", "放量", "政策", "订单", "业绩")
    )


def _is_market_noise_headline(text: str) -> bool:
    noise_terms = ("行业周报", "收评：", "风格突变", "涨涨涨", "跌幅居前", "垂直涨停")
    if any(term in text for term in noise_terms):
        return True
    if ("有望翻倍" in text or "一览" in text) and "龙头" in text:
        return True
    return False


def _summarize_thsdk_note(text: str) -> str:
    match = re.search(r"今日(涨停|连板)返回(\d+)条", text)
    if not match:
        return "THSDK问财确认前排活跃"
    label, count = match.groups()
    if label == "连板":
        return f"问财确认{count}条连板高度，留意前排承接"
    return f"问财确认{count}条涨停前排，板块扩散强"


def _strip_source_prefix(text: str) -> str:
    for prefix in ("同花顺复盘确认", "东方财富涨停复盘确认", "Anspire新闻："):
        if text.startswith(prefix):
            return text.removeprefix(prefix).strip("：:，,。 ")
    return text


def _strip_news_noise(text: str) -> str:
    text = re.sub(r"20\d{2}年\d{1,2}月\d{1,2}日\s*\d{1,2}:\d{2}.*?[，,]", "", text)
    text = re.sub(r"20\d{2}年\d{1,2}月\d{1,2}日\s*\d{0,2}:?\d{0,2}", "", text)
    text = re.sub(r"20\d{2}[-/]\d{1,2}[-/]\d{1,2}\s*\d{0,2}:?\d{0,2}", "", text)
    text = re.sub(r"\s+", " ", text).strip(" ，,。")
    return text


def _keep_first_clause(text: str) -> str:
    parts = re.split(r"[。；;]", text, maxsplit=1)
    return parts[0].strip() if parts else text


def _compress_stock_chain(text: str) -> str:
    if "多股涨停" not in text:
        return text
    match = re.match(r"(?P<prefix>.*?)(?P<stocks>[\u4e00-\u9fa5A-Za-z0-9*]+(?:、[\u4e00-\u9fa5A-Za-z0-9*]+){2,})等多股涨停(?P<suffix>.*)", text)
    if not match:
        return text
    prefix = match.group("prefix")
    stocks = match.group("stocks").split("、")
    suffix = match.group("suffix")
    front = "、".join(stocks[:2])
    return f"{prefix}{front}等多股涨停{suffix}"


def _truncate(text: str, max_length: int) -> str:
    if len(text) <= max_length:
        return text
    return f"{text[: max_length - 1].rstrip()}…"
