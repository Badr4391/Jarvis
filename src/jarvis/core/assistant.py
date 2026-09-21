"""Der Agent: Gespraech + Werkzeugschleife. Das Herz von Jarvis."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from jarvis.core.context import JarvisContext
from jarvis.core.persona import build_system_prompt
from jarvis.llm.base import LLMResponse, Message, ToolResult
from jarvis.skills.base import load_all, result_to_text, run_skill, tool_specs

MAX_TOOL_ROUNDS = 6


@dataclass
class Turn:
    """Ergebnis eines Gespraechszugs - inklusive dem, was Jarvis dabei getan hat."""

    text: str
    tool_log: list[dict[str, Any]] = field(default_factory=list)
    provider: str = ""
    model: str = ""

    def actions(self) -> list[str]:
        return [entry["name"] for entry in self.tool_log]


@dataclass
class Assistant:
    ctx: JarvisContext
    session: str = "default"
    categories: list[str] | None = None
    on_tool: Callable[[str, dict[str, Any]], None] | None = None

    def __post_init__(self) -> None:
        load_all()

    # -------------------------------------------------------------- prompting
    def system_prompt(self, extra: str = "") -> str:
        return build_system_prompt(
            self.ctx.config, memory_block=self.ctx.memory.context_block(), extra=extra
        )

    def _history(self, limit: int = 16) -> list[Message]:
        return [
            Message(role=row["role"], content=row["content"])
            for row in self.ctx.memory.history(session=self.session, limit=limit)
            if row["role"] in ("user", "assistant") and row["content"]
        ]

    # ------------------------------------------------------------------- chat
    def ask(self, user_input: str, *, remember: bool = True, extra_system: str = "") -> Turn:
        """Eine Nutzeranfrage vollstaendig beantworten, inklusive Werkzeugeinsatz."""
        provider = self.ctx.llm
        messages = self._history()
        messages.append(Message(role="user", content=user_input))
        if remember:
            self.ctx.memory.log_message("user", user_input, session=self.session)

        specs = tool_specs(self.categories)
        tool_log: list[dict[str, Any]] = []
        response: LLMResponse | None = None

        for _ in range(MAX_TOOL_ROUNDS):
            response = provider.chat(
                messages,
                system=self.system_prompt(extra_system),
                tools=specs,
                max_tokens=self.ctx.config.llm.max_tokens,
                temperature=self.ctx.config.llm.temperature,
            )
            if not response.wants_tools:
                break

            messages.append(
                Message(role="assistant", content=response.text, tool_calls=response.tool_calls)
            )
            results: list[ToolResult] = []
            for call in response.tool_calls:
                payload = run_skill(self.ctx, call.name, call.arguments)
                tool_log.append(
                    {"name": call.name, "arguments": call.arguments, "ok": payload.get("ok", False)}
                )
                if self.on_tool:
                    self.on_tool(call.name, call.arguments)
                results.append(
                    ToolResult(
                        call_id=call.id,
                        name=call.name,
                        content=result_to_text(payload),
                        is_error=not payload.get("ok", False),
                    )
                )
            messages.append(Message(role="tool", tool_results=results))
        else:
            # Schleife ausgereizt: letzte Antwort ohne Werkzeuge erzwingen.
            response = provider.chat(
                messages,
                system=self.system_prompt(
                    "Fasse jetzt ohne weitere Werkzeuge zusammen, was du herausgefunden hast."
                ),
                max_tokens=self.ctx.config.llm.max_tokens,
                temperature=self.ctx.config.llm.temperature,
            )

        text = (response.text if response else "").strip()
        if not text:
            text = (
                "Erledigt: " + ", ".join(e["name"] for e in tool_log)
                if tool_log else "Ich habe keine Antwort bekommen."
            )
        if remember:
            self.ctx.memory.log_message("assistant", text, session=self.session)

        return Turn(
            text=text,
            tool_log=tool_log,
            provider=getattr(response, "provider", ""),
            model=getattr(response, "model", ""),
        )

    # ------------------------------------------------------------- hilfsmittel
    def run_tool(self, name: str, **arguments: Any) -> dict[str, Any]:
        """Werkzeug direkt aufrufen - ohne Modell, fuer CLI und Scheduler."""
        return run_skill(self.ctx, name, arguments)

    def reset(self) -> None:
        self.ctx.memory.clear_history(session=self.session)
