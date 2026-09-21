"""Mikrofonaufnahme ueber das, was das System mitbringt."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from jarvis.config import VoiceConfig


def _which(name: str) -> str | None:
    return shutil.which(name)


def available_recorders() -> list[str]:
    return [name for name in ("arecord", "rec", "ffmpeg", "sox") if _which(name)]


def record(cfg: VoiceConfig, *, seconds: float | None = None,
           out_path: Path | str | None = None) -> Path | None:
    """Nimmt Mono-WAV in der konfigurierten Abtastrate auf."""
    seconds = seconds or cfg.record_seconds
    out = Path(out_path) if out_path else Path(tempfile.mktemp(suffix=".wav"))
    rate = str(cfg.sample_rate)

    commands: list[list[str]] = []
    if _which("arecord"):
        commands.append(["arecord", "-q", "-f", "S16_LE", "-r", rate, "-c", "1",
                         "-d", str(int(seconds)), str(out)])
    if _which("rec"):
        commands.append(["rec", "-q", "-r", rate, "-c", "1", "-b", "16", str(out),
                         "trim", "0", str(seconds)])
    if _which("ffmpeg"):
        commands.append(["ffmpeg", "-loglevel", "quiet", "-y", "-f", "avfoundation",
                         "-i", ":0", "-t", str(seconds), "-ar", rate, "-ac", "1", str(out)])

    for command in commands:
        try:
            subprocess.run(command, check=True, capture_output=True, timeout=seconds + 30)
            if out.is_file() and out.stat().st_size > 1000:
                return out
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
            continue
    return None
