"""Provider-Auswahl mit automatischem Fallback."""

from __future__ import annotations

from jarvis.config import Config, LLMConfig
from jarvis.llm.anthropic_provider import AnthropicProvider
from jarvis.llm.base import LLMProvider
from jarvis.llm.echo_provider import EchoProvider
from jarvis.llm.ollama_provider import OllamaProvider


def build_provider(cfg: LLMConfig | Config) -> LLMProvider:
    """Baut den konfigurierten Provider; faellt auf Echo zurueck, wenn nichts geht."""
    llm = cfg.llm if isinstance(cfg, Config) else cfg

    if llm.provider == "anthropic" and llm.api_key:
        return AnthropicProvider(llm.api_key, llm.model, timeout=llm.timeout)
    if llm.provider == "ollama":
        provider = OllamaProvider(llm.ollama_host, llm.model, timeout=llm.timeout)
        if provider.available():
            return provider
    if llm.provider == "echo":
        return EchoProvider()

    # Automatik: was auch immer erreichbar ist.
    if llm.api_key:
        return AnthropicProvider(llm.api_key, llm.model, timeout=llm.timeout)
    fallback = OllamaProvider(llm.ollama_host, llm.model or "qwen2.5:7b-instruct")
    return fallback if fallback.available() else EchoProvider()
