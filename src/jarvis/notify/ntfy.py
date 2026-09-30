"""ntfy.sh: der schnellste Weg zu echten Push-Meldungen aufs Handy.

App installieren, ein Thema abonnieren (z.B. jarvis-badr-7f3k), denselben Namen
als NTFY_TOPIC in die .env. Kein Konto, kein Schluessel. Wichtig: wer das Thema
kennt, sieht die Meldungen - also einen langen, zufaelligen Namen waehlen.
"""

from __future__ import annotations

import os
import urllib.request
from dataclasses import dataclass

from jarvis.notify.base import Notification
from jarvis.util.http import _ssl_context

PRIORITY_MAP = {1: "high", 2: "default", 3: "low"}


@dataclass
class NtfyNotifier:
    name: str = "ntfy"
    topic: str = ""
    server: str = "https://ntfy.sh"
    token: str = ""
    timeout: int = 15

    @classmethod
    def from_env(cls) -> NtfyNotifier:
        return cls(
            topic=os.environ.get("NTFY_TOPIC", ""),
            server=os.environ.get("NTFY_SERVER", "https://ntfy.sh").rstrip("/"),
            token=os.environ.get("NTFY_TOKEN", ""),
        )

    def enabled(self) -> bool:
        return bool(self.topic)

    def send(self, notification: Notification) -> bool:
        if not self.enabled():
            return False
        headers = {
            "Title": notification.title.encode("utf-8").decode("latin-1", "replace"),
            "Priority": PRIORITY_MAP.get(notification.priority, "default"),
            "Content-Type": "text/plain; charset=utf-8",
        }
        if notification.tags:
            headers["Tags"] = ",".join(notification.tags)
        if notification.url:
            headers["Click"] = notification.url
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        request = urllib.request.Request(
            f"{self.server}/{self.topic}",
            data=(notification.body or notification.title).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout,
                                        context=_ssl_context()) as response:
                return 200 <= response.status < 300
        except Exception:                                          # noqa: BLE001
            return False
