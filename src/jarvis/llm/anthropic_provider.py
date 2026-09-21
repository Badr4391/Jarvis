"""Anthropic Messages API - direkt via HTTPS, ohne SDK-Abhaengigkeit."""

from __future__ import annotations

import uuid
from typing import Any

from jarvis.llm.base import LLMResponse, Message, ToolCall, ToolSpec
from jarvis.util.http import request_json

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, api_key: str, model: str = "claude-opus-5", *, timeout: int = 120) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    def available(self) -> bool:
        return bool(self.api_key)

    # ------------------------------------------------------------ konvertieren
    @staticmethod
    def _to_api_messages(messages: list[Message]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for msg in messages:
            if msg.role == "tool":
                out.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": result.call_id,
                                "content": result.content,
                                **({"is_error": True} if result.is_error else {}),
                            }
                            for result in msg.tool_results
                        ],
                    }
                )
                continue

            blocks: list[dict[str, Any]] = []
            if msg.content:
                blocks.append({"type": "text", "text": msg.content})
            for call in msg.tool_calls:
                blocks.append(
                    {"type": "tool_use", "id": call.id, "name": call.name, "input": call.arguments}
                )
            if blocks:
                out.append({"role": msg.role, "content": blocks})
        return out

    # ------------------------------------------------------------------- chat
    def chat(
        self,
        messages: list[Message],
        *,
        system: str = "",
        tools: list[ToolSpec] | None = None,
        max_tokens: int = 2048,
        temperature: float = 0.6,
    ) -> LLMResponse:
        payload: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": self._to_api_messages(messages),
        }
        if system:
            payload["system"] = system
        if tools:
            payload["tools"] = [
                {"name": t.name, "description": t.description, "input_schema": t.parameters}
                for t in tools
            ]

        data = request_json(
            API_URL,
            method="POST",
            headers={"x-api-key": self.api_key, "anthropic-version": API_VERSION},
            body=payload,
            timeout=self.timeout,
        )

        text_parts: list[str] = []
        calls: list[ToolCall] = []
        for block in data.get("content", []):
            if block.get("type") == "text":
                text_parts.append(block.get("text", ""))
            elif block.get("type") == "tool_use":
                calls.append(
                    ToolCall(
                        id=block.get("id") or str(uuid.uuid4()),
                        name=block.get("name", ""),
                        arguments=block.get("input") or {},
                    )
                )
        return LLMResponse(
            text="\n".join(p for p in text_parts if p).strip(),
            tool_calls=calls,
            raw=data,
            provider=self.name,
            model=self.model,
        )
