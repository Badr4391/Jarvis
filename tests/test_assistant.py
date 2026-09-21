"""Agentenschleife mit einem Fake-Provider - ohne Netz."""

from dataclasses import dataclass, field

from jarvis.core.assistant import Assistant
from jarvis.llm.base import LLMResponse, ToolCall


@dataclass
class FakeProvider:
    """Spielt eine feste Folge von Antworten ab und merkt sich die Aufrufe."""

    responses: list[LLMResponse]
    name: str = "fake"
    model: str = "fake-1"
    calls: list[dict] = field(default_factory=list)

    def available(self) -> bool:
        return True

    def chat(self, messages, *, system="", tools=None, max_tokens=2048, temperature=0.6):
        self.calls.append({"messages": list(messages), "system": system,
                           "tools": [t.name for t in (tools or [])]})
        return self.responses.pop(0) if self.responses else LLMResponse(text="fertig")


def _assistant(ctx, responses):
    provider = FakeProvider(responses=responses)
    ctx.__dict__["llm"] = provider                 # cached_property ueberschreiben
    return Assistant(ctx=ctx), provider


def test_plain_answer(ctx):
    assistant, provider = _assistant(ctx, [LLMResponse(text="Moin!")])
    turn = assistant.ask("Hallo")
    assert turn.text == "Moin!"
    assert turn.tool_log == []
    assert "Jarvis" in provider.calls[0]["system"]


def test_tool_call_is_executed(ctx):
    responses = [
        LLMResponse(text="", tool_calls=[
            ToolCall(id="1", name="task_add", arguments={"title": "Chart Review", "due": "heute"})
        ]),
        LLMResponse(text="Steht im Kalender."),
    ]
    assistant, _ = _assistant(ctx, responses)
    turn = assistant.ask("Trag mir Chart Review fuer heute ein")
    assert turn.actions() == ["task_add"]
    assert ctx.life.list_tasks()[0]["title"] == "Chart Review"
    assert turn.text == "Steht im Kalender."


def test_failing_tool_is_reported_back(ctx):
    responses = [
        LLMResponse(text="", tool_calls=[ToolCall(id="1", name="task_add", arguments={})]),
        LLMResponse(text="Titel fehlt mir noch."),
    ]
    assistant, provider = _assistant(ctx, responses)
    turn = assistant.ask("Aufgabe anlegen")
    assert turn.tool_log[0]["ok"] is False
    assert turn.text == "Titel fehlt mir noch."


def test_history_is_persisted(ctx):
    assistant, _ = _assistant(ctx, [LLMResponse(text="Alles klar.")])
    assistant.ask("Merk dir das")
    history = ctx.memory.history()
    assert [m["role"] for m in history] == ["user", "assistant"]


def test_history_is_replayed(ctx):
    assistant, provider = _assistant(ctx, [LLMResponse(text="eins"), LLMResponse(text="zwei")])
    assistant.ask("erste Frage")
    assistant.ask("zweite Frage")
    replayed = [m.content for m in provider.calls[1]["messages"]]
    assert "erste Frage" in replayed and "eins" in replayed


def test_tools_are_offered(ctx):
    assistant, provider = _assistant(ctx, [LLMResponse(text="ok")])
    assistant.ask("was geht")
    assert "task_add" in provider.calls[0]["tools"]


def test_empty_answer_falls_back_to_action_summary(ctx):
    responses = [
        LLMResponse(text="", tool_calls=[
            ToolCall(id="1", name="task_add", arguments={"title": "X"})]),
        LLMResponse(text=""),
    ]
    assistant, _ = _assistant(ctx, responses)
    assert "task_add" in assistant.ask("mach was").text


def test_run_tool_without_model(ctx):
    assistant, _ = _assistant(ctx, [])
    assert assistant.run_tool("task_add", title="Direkt")["ok"]
