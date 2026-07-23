from app.services.notification import (
    NotificationService,
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


class FailingNotifier:
    channel = "wecom"

    def send(self, message: NotificationMessage) -> NotificationResult:
        raise RuntimeError("timeout")


class RecordingNotifier:
    channel = "feishu"

    def __init__(self) -> None:
        self.messages: list[NotificationMessage] = []

    def send(self, message: NotificationMessage) -> NotificationResult:
        self.messages.append(message)
        return NotificationResult(channel=self.channel, status="sent", detail="sent")


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

    result = NotificationService([notifier]).send_all(
        NotificationMessage(title="午盘提醒", body="机会分 82")
    )

    assert result == [NotificationResult(channel="wecom", status="sent", detail="sent")]
    assert http_client.requests == [
        {
            "url": "https://wecom.example.test/webhook",
            "json": {"msgtype": "markdown", "markdown": {"content": "## 午盘提醒\n\n机会分 82"}},
            "timeout": 12,
        }
    ]


def test_notification_service_continues_after_channel_failure() -> None:
    successful = RecordingNotifier()
    message = NotificationMessage(title="风险提醒", body="跌破MA5")

    result = NotificationService([FailingNotifier(), successful]).send_all(message)

    assert result[0] == NotificationResult(channel="wecom", status="failed", detail="timeout")
    assert result[1] == NotificationResult(channel="feishu", status="sent", detail="sent")
    assert successful.messages == [message]


def test_build_notifiers_from_settings_only_configures_enabled_channels() -> None:
    notifiers = build_notifiers_from_settings(FakeSettings())

    assert [notifier.channel for notifier in notifiers] == ["wecom"]
