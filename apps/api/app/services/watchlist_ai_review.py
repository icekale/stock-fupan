from pydantic import BaseModel


class WatchlistAIReview(BaseModel):
    summary: str
    comments: dict[str, str]


class RuleWatchlistAIReviewProvider:
    provider_name = "rule"
    model_name = "watchlist-alert-rule-v1"

    def generate_alert_commentary(self, seed: dict[str, object]) -> dict[str, object]:
        raw_events = seed.get("events")
        events = raw_events if isinstance(raw_events, list) else []
        comments: dict[str, str] = {}
        for event in events:
            if not isinstance(event, dict):
                continue
            symbol = str(event.get("symbol") or "")
            if not symbol:
                continue
            name = str(event.get("name") or symbol)
            event_type = str(event.get("event_type") or "alert")
            reason = str(event.get("trigger_reason") or "规则触发")
            comments[symbol] = f"{name}触发{event_type}提醒：{reason}。"
        return WatchlistAIReview(
            summary=f"本次触发 {len(comments)} 条自选股提醒。",
            comments=comments,
        ).model_dump(mode="json")
