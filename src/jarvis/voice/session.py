"""Sprachmodus: zuhoeren, antworten, vorlesen - in einer Schleife."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from jarvis.core.assistant import Assistant
from jarvis.voice.recorder import available_recorders, record
from jarvis.voice.stt import STT
from jarvis.voice.tts import TTS

STOP_WORDS = ("stopp", "stop", "ende", "tschüss", "tschuess", "beenden", "schluss")


@dataclass
class VoiceSession:
    assistant: Assistant
    printer: Callable[[str], None] = print

    def __post_init__(self) -> None:
        cfg = self.assistant.ctx.config.voice
        self.tts = TTS(cfg)
        self.stt = STT(cfg)
        self.cfg = cfg

    def diagnose(self) -> dict[str, object]:
        return {
            "tts_engine": self.tts.engine(),
            "stt_engine": self.stt.engine(),
            "recorder": available_recorders(),
            "bereit": self.tts.engine() != "none" and self.stt.engine() != "none"
            and bool(available_recorders()),
        }

    def say(self, text: str, *, save_to: Path | str | None = None) -> bool:
        return self.tts.speak(text, keep=save_to)

    def listen_once(self, *, seconds: float | None = None) -> str:
        audio = record(self.cfg, seconds=seconds)
        if not audio:
            return ""
        try:
            return self.stt.transcribe(audio)
        finally:
            try:
                Path(audio).unlink(missing_ok=True)
            except OSError:
                pass

    def loop(self, *, max_turns: int = 100) -> None:
        """Push-to-talk Schleife: Enter druecken, sprechen, Antwort hoeren."""
        status = self.diagnose()
        if not status["bereit"]:
            self.printer(
                "Sprachmodus nicht vollstaendig einsatzbereit:\n"
                f"  TTS: {status['tts_engine']}\n"
                f"  STT: {status['stt_engine']}\n"
                f"  Aufnahme: {status['recorder'] or 'keine'}\n"
                "Siehe README, Abschnitt 'Stimme einrichten'."
            )
            return

        self.printer("Sprachmodus aktiv. Enter = aufnehmen, 'q' + Enter = beenden.\n")
        for _ in range(max_turns):
            try:
                command = input("[Enter zum Sprechen] ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                break
            if command in ("q", "quit", "exit"):
                break

            self.printer(f"... hoere zu ({self.cfg.record_seconds:.0f}s)")
            text = self.listen_once()
            if not text:
                self.printer("Nichts verstanden.")
                continue
            self.printer(f"Du: {text}")
            if any(word in text.lower() for word in STOP_WORDS):
                self.say("Alles klar, bis spaeter.")
                break

            turn = self.assistant.ask(text)
            self.printer(f"Jarvis: {turn.text}\n")
            self.say(turn.text)
