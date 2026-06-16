from dataclasses import dataclass
from email.message import EmailMessage
import smtplib
from typing import Protocol

import httpx


@dataclass(frozen=True)
class NotificationMessage:
    title: str
    body: str


@dataclass(frozen=True)
class NotificationResult:
    channel: str
    status: str
    detail: str


class Notifier(Protocol):
    channel: str

    def send(self, message: NotificationMessage) -> NotificationResult:
        raise NotImplementedError


class NotificationService:
    def __init__(self, notifiers: list[Notifier]) -> None:
        self.notifiers = notifiers

    def send(self, message: NotificationMessage) -> list[NotificationResult]:
        return [notifier.send(message) for notifier in self.notifiers]


class WebhookNotifier:
    channel = "webhook"

    def __init__(
        self,
        webhook_url: str,
        http_client: object | None = None,
        timeout_seconds: float = 12,
    ) -> None:
        self.webhook_url = webhook_url
        self.http_client = http_client or httpx.Client()
        self.timeout_seconds = timeout_seconds

    def send(self, message: NotificationMessage) -> NotificationResult:
        payload = self.build_payload(message)
        response = self.http_client.post(
            self.webhook_url,
            json=payload,
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        return NotificationResult(channel=self.channel, status="sent", detail="sent")

    def build_payload(self, message: NotificationMessage) -> dict[str, object]:
        return {"text": _message_text(message)}


class WeComNotifier(WebhookNotifier):
    channel = "wecom"

    def build_payload(self, message: NotificationMessage) -> dict[str, object]:
        return {
            "msgtype": "markdown",
            "markdown": {"content": _markdown_content(message)},
        }


class FeishuNotifier(WebhookNotifier):
    channel = "feishu"

    def build_payload(self, message: NotificationMessage) -> dict[str, object]:
        return {
            "msg_type": "interactive",
            "card": {
                "header": {"title": {"tag": "plain_text", "content": message.title}},
                "elements": [{"tag": "div", "text": {"tag": "lark_md", "content": message.body}}],
            },
        }


class TelegramNotifier:
    channel = "telegram"

    def __init__(
        self,
        bot_token: str,
        chat_id: str,
        http_client: object | None = None,
        timeout_seconds: float = 12,
    ) -> None:
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.http_client = http_client or httpx.Client()
        self.timeout_seconds = timeout_seconds

    def send(self, message: NotificationMessage) -> NotificationResult:
        response = self.http_client.post(
            f"https://api.telegram.org/bot{self.bot_token}/sendMessage",
            json={
                "chat_id": self.chat_id,
                "text": _message_text(message),
                "parse_mode": "Markdown",
            },
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        return NotificationResult(channel=self.channel, status="sent", detail="sent")


class EmailNotifier:
    channel = "email"

    def __init__(
        self,
        host: str,
        port: int,
        username: str,
        password: str,
        sender: str,
        recipient: str,
    ) -> None:
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.sender = sender
        self.recipient = recipient

    def send(self, message: NotificationMessage) -> NotificationResult:
        email = EmailMessage()
        email["Subject"] = message.title
        email["From"] = self.sender
        email["To"] = self.recipient
        email.set_content(message.body)
        with smtplib.SMTP(self.host, self.port) as smtp:
            smtp.starttls()
            if self.username:
                smtp.login(self.username, self.password)
            smtp.send_message(email)
        return NotificationResult(channel=self.channel, status="sent", detail="sent")


def build_notifiers_from_settings(settings: object) -> list[Notifier]:
    notifiers: list[Notifier] = []
    if getattr(settings, "wecom_webhook_url", ""):
        notifiers.append(WeComNotifier(webhook_url=settings.wecom_webhook_url))
    if getattr(settings, "feishu_webhook_url", ""):
        notifiers.append(FeishuNotifier(webhook_url=settings.feishu_webhook_url))
    if getattr(settings, "telegram_bot_token", "") and getattr(settings, "telegram_chat_id", ""):
        notifiers.append(
            TelegramNotifier(
                bot_token=settings.telegram_bot_token,
                chat_id=settings.telegram_chat_id,
            )
        )
    if getattr(settings, "smtp_host", "") and getattr(settings, "smtp_from", "") and getattr(settings, "smtp_to", ""):
        notifiers.append(
            EmailNotifier(
                host=settings.smtp_host,
                port=settings.smtp_port,
                username=settings.smtp_username,
                password=settings.smtp_password,
                sender=settings.smtp_from,
                recipient=settings.smtp_to,
            )
        )
    return notifiers


def _markdown_content(message: NotificationMessage) -> str:
    return f"## {message.title}\n\n{message.body}"


def _message_text(message: NotificationMessage) -> str:
    return f"{message.title}\n\n{message.body}"
