"""Sprachausgabe. Erkennt automatisch, was auf dem Rechner vorhanden ist."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from jarvis.config import VoiceConfig

PLAYERS = ("aplay", "afplay", "paplay", "ffplay", "mpv")


def _which(name: str) -> str | None:
    return shutil.which(name)


def available_engines(cfg: VoiceConfig) -> list[str]:
    engines = []
    if _which(cfg.piper_bin) and cfg.piper_model and Path(cfg.piper_model).is_file():
        engines.append("piper")
    if _which("espeak-ng") or _which("espeak"):
        engines.append("espeak")
    if _which("say"):
        engines.append("say")
    try:
        import pyttsx3  # type: ignore # noqa: F401

        engines.append("pyttsx3")
    except ImportError:
        pass
    return engines


def play(path: Path) -> bool:
    for player in PLAYERS:
        binary = _which(player)
        if not binary:
            continue
        args = [binary, str(path)]
        if player == "ffplay":
            args = [binary, "-nodisp", "-autoexit", "-loglevel", "quiet", str(path)]
        try:
            subprocess.run(args, check=True, capture_output=True, timeout=300)
            return True
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            continue
    return False


@dataclass
class TTS:
    """Text zu Sprache - schreibt eine WAV-Datei und spielt sie optional ab."""

    cfg: VoiceConfig

    def engine(self) -> str:
        if self.cfg.tts not in ("auto", "", None):
            return self.cfg.tts
        engines = available_engines(self.cfg)
        return engines[0] if engines else "none"

    def synthesize(self, text: str, out_path: Path | str | None = None) -> Path | None:
        """Gibt den Pfad zur Audiodatei zurueck, oder None wenn keine Engine da ist."""
        engine = self.engine()
        if engine == "none" or not text.strip():
            return None

        out = Path(out_path) if out_path else Path(tempfile.mktemp(suffix=".wav"))
        out.parent.mkdir(parents=True, exist_ok=True)

        try:
            if engine == "piper":
                binary = _which(self.cfg.piper_bin) or self.cfg.piper_bin
                subprocess.run(
                    [binary, "--model", self.cfg.piper_model, "--output_file", str(out)],
                    input=text.encode("utf-8"), check=True, capture_output=True, timeout=300,
                )
                return out
            if engine == "espeak":
                binary = _which("espeak-ng") or _which("espeak")
                subprocess.run(
                    [binary, "-v", self.cfg.language, "-s", "165", "-w", str(out), text],
                    check=True, capture_output=True, timeout=300,
                )
                return out
            if engine == "say":
                aiff = out.with_suffix(".aiff")
                subprocess.run(["say", "-o", str(aiff), text], check=True,
                               capture_output=True, timeout=300)
                return aiff
            if engine == "pyttsx3":
                import pyttsx3  # type: ignore

                motor = pyttsx3.init()
                motor.save_to_file(text, str(out))
                motor.runAndWait()
                return out if out.is_file() else None
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
            return None
        return None

    def speak(self, text: str, *, keep: Path | str | None = None) -> bool:
        """Text direkt vorlesen. True, wenn wirklich Ton rauskam."""
        path = self.synthesize(text, keep)
        if not path:
            return False
        played = play(path)
        if keep is None:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
        return played
