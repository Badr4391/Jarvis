"""Fallback ohne Modell: Jarvis bleibt bedienbar, nur ohne freie Sprache."""

from __future__ import annotations

from jarvis.llm.base import LLMResponse, Message, ToolSpec

OFFLINE_HINT = (
    "Ich laufe gerade ohne Sprachmodell (kein ANTHROPIC_API_KEY und kein Ollama). "
    "Befehle funktionieren trotzdem: `jarvis task add ...`, `jarvis trade log ...`, "
    "`jarvis brief`, `jarvis market analyse EURUSD`."
)


class EchoProvider:
    name = "echo"

    def __init__(self, model: str = "offline") -> None:
        self.model = model

    def available(self) -> bool:
        return True

    def chat(
        self,
        messages: list[Message],
        *,
        system: str = "",
        tools: list[ToolSpec] | None = None,
        max_tokens: int = 2048,
        temperature: float = 0.6,
    ) -> LLMResponse:
        last_user = next((m.content for m in reversed(messages) if m.role == "user"), "")
        text = OFFLINE_HINT
        if last_user:
            text = f'Verstanden: "{last_user.strip()}"\n\n{OFFLINE_HINT}'
        return LLMResponse(text=text, provider=self.name, model=self.model)
