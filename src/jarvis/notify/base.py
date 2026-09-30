"""Benachrichtigungen: eine Form, mehrere Wege aufs Handy."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class Notification:
    kind: str                       # brief | risiko | ziel | erinnerung | markt
    title: str
    body: str = ""
    url: str = ""
    priority: int = 2               # 1 hoch (Ton), 2 normal, 3 leise
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind, "title": self.title, "body": self.body,
            "url": self.url, "priority": self.priority, "tags": self.tags,
        }


class Notifier(Protocol):
    name: str

    def enabled(self) -> bool: ...

    def send(self, notification: Notification) -> bool: ...
