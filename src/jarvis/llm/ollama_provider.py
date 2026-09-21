"""Lokales Modell via Ollama - local-first, keine Daten verlassen den Rechner."""

from __future__ import annotations

import uuid
from typing import Any

from jarvis.llm.base import LLMResponse, Message, ToolCall, ToolSpec
from jarvis.util.http import request_json


class OllamaProvider:
    name = "ollama"

    def __init__(self, host: str = "http://localhost:11434",
                 model: str = "qwen2.5:14b-instruct", *, timeout: int = 180) -> None:
        self.host = host.rstrip("/")
        self.model = model
        self.timeout = timeout

    def available(self) -> bool:
        try:
            data = request_json(f"{self.host}/api/tags", timeout=5, retries=0)
        except Exception:
            return False
        return bool(data)

    @staticmethod
    def _to_api_messages(messages: list[Message]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for msg in messages:
            if msg.role == "tool":
                for result in msg.tool_results:
                    out.append({"role": "tool", "content": result.content})
                continue
            entry: dict[str, Any] = {"role": msg.role, "content": msg.content}
            if msg.tool_calls:
                entry["tool_calls"] = [
                    {"function": {"name": c.name, "arguments": c.arguments}} for c in msg.tool_calls
                ]
            out.append(entry)
        return out

    def chat(
        self,
        messages: list[Message],
        *,
        system: str = "",
        tools: list[ToolSpec] | None = None,
        max_tokens: int = 2048,
        temperature: float = 0.6,
    ) -> LLMResponse:
        api_messages = self._to_api_messages(messages)
        if system:
            api_messages.insert(0, {"role": "system", "content": system})

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": api_messages,
            "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        if tools:
            payload["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name, "description": t.description, "parameters": t.parameters
                    },
                }
                for t in tools
            ]

        data = request_json(f"{self.host}/api/chat", method="POST", body=payload,
                            timeout=self.timeout)
        message = data.get("message", {}) or {}
        calls = [
            ToolCall(
                id=str(uuid.uuid4()),
                name=(call.get("function") or {}).get("name", ""),
                arguments=(call.get("function") or {}).get("arguments") or {},
            )
            for call in message.get("tool_calls", []) or []
        ]
        return LLMResponse(
            text=(message.get("content") or "").strip(),
            tool_calls=calls, raw=data, provider=self.name, model=self.model,
        )
