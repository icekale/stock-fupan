from app.services.notification import (
    NotificationMessage,
    NotificationResult,
    WeComNotifier,
    build_notifiers_from_settings,
)


class FakeHttpClient:
    def __init__(self) -> None:
        self.requests: list[dict[str, object]] = []

    def post(self, url: str, **kwargs: object) -> object:
        self.requests.append({"url": url, **kwargs})
        return FakeResponse()


class FakeResponse:
    def raise_for_status(self) -> None:
        pass


class FakeSettings:
    wecom_webhook_url = "https://wecom.example.test/webhook"
    feishu_webhook_url = ""
    telegram_bot_token = ""
    telegram_chat_id = ""
    smtp_host = ""
    smtp_port = 587
    smtp_username = ""
    smtp_password = ""
    smtp_from = ""
    smtp_to = ""


def test_wecom_notifier_sends_markdown_payload() -> None:
    http_client = FakeHttpClient()
    notifier = WeComNotifier(
        webhook_url="https://wecom.example.test/webhook",
        http_client=http_client,
    )

    result = notifier.send(NotificationMessage(title="午盘提醒", body="机会分 82"))

    assert result == NotificationResult(channel="wecom", status="sent", detail="sent")
    assert http_client.requests == [
        {
            "url": "https://wecom.example.test/webhook",
            "json": {"msgtype": "markdown", "markdown": {"content": "## 午盘提醒\n\n机会分 82"}},
            "timeout": 12,
        }
    ]


def test_build_notifiers_from_settings_only_configures_enabled_channels() -> None:
    notifiers = build_notifiers_from_settings(FakeSettings())

    assert [notifier.channel for notifier in notifiers] == ["wecom"]
