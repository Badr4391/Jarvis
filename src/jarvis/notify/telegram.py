"""Telegram: Briefing und Warnungen direkt in den Messenger.

Bot bei @BotFather anlegen, Token als TELEGRAM_BOT_TOKEN in die .env,
dem Bot einmal schreiben, dann `jarvis notify --chat-id` aufrufen.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from jarvis.notify.base import Notification
from jarvis.util.http import request_json


@dataclass
class TelegramNotifier:
    name: str = "telegram"
    token: str = ""
    chat_id: str = ""
    timeout: int = 20

    @classmethod
    def from_env(cls) -> TelegramNotifier:
        return cls(
            token=os.environ.get("TELEGRAM_BOT_TOKEN", ""),
            chat_id=os.environ.get("TELEGRAM_CHAT_ID", ""),
        )

    def enabled(self) -> bool:
        return bool(self.token and self.chat_id)

    def _api(self, method: str, **payload: Any) -> Any:
        return request_json(
            f"https://api.telegram.org/bot{self.token}/{method}",
            method="POST", body=payload, timeout=self.timeout, retries=1,
        )

    def discover_chat_id(self) -> str | None:
        """Die Chat-ID aus der letzten Nachricht an den Bot lesen."""
        if not self.token:
            return None
        try:
            data = request_json(f"https://api.telegram.org/bot{self.token}/getUpdates",
                                timeout=self.timeout, retries=1)
        except Exception:                                          # noqa: BLE001
            return None
        for update in reversed(data.get("result", []) or []):
            chat = (update.get("message") or update.get("channel_post") or {}).get("chat") or {}
            if chat.get("id"):
                return str(chat["id"])
        return None

    def send(self, notification: Notification) -> bool:
        if not self.enabled():
            return False
        text = f"*{_escape(notification.title)}*"
        if notification.body:
            text += "\n\n" + _escape(notification.body)
        if notification.url:
            text += f"\n\n{notification.url}"
        try:
            result = self._api(
                "sendMessage", chat_id=self.chat_id, text=text[:4000],
                parse_mode="Markdown", disable_notification=notification.priority == 3,
            )
        except Exception:                                          # noqa: BLE001
            return False
        return bool(result.get("ok"))


def _escape(text: str) -> str:
    for char in ("_", "*", "`", "["):
        text = text.replace(char, "\\" + char)
    return text
