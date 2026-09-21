"""Spracherkennung: whisper.cpp, faster-whisper oder openai-whisper."""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from jarvis.config import VoiceConfig


def _which(name: str) -> str | None:
    return shutil.which(name) if name else None


def available_engines(cfg: VoiceConfig) -> list[str]:
    engines: list[str] = []
    if _which(cfg.whisper_cpp_bin) and cfg.whisper_cpp_model and Path(cfg.whisper_cpp_model).is_file():
        engines.append("whisper-cpp")
    for module, label in (("faster_whisper", "faster-whisper"), ("whisper", "whisper")):
        try:
            __import__(module)
            engines.append(label)
        except ImportError:
            continue
    return engines


@dataclass
class STT:
    cfg: VoiceConfig
    _model: object | None = None

    def engine(self) -> str:
        if self.cfg.stt not in ("auto", "", None):
            return self.cfg.stt
        engines = available_engines(self.cfg)
        return engines[0] if engines else "none"

    def transcribe(self, audio_path: Path | str) -> str:
        """Audio zu Text. Leerer String, wenn nichts erkannt wurde."""
        engine = self.engine()
        path = Path(audio_path)
        if engine == "none" or not path.is_file():
            return ""

        try:
            if engine == "whisper-cpp":
                binary = _which(self.cfg.whisper_cpp_bin) or self.cfg.whisper_cpp_bin
                result = subprocess.run(
                    [binary, "-m", self.cfg.whisper_cpp_model, "-f", str(path),
                     "-l", self.cfg.language, "-oj", "-of", str(path.with_suffix("")), "-nt"],
                    check=True, capture_output=True, timeout=600,
                )
                json_path = path.with_suffix(".json")
                if json_path.is_file():
                    data = json.loads(json_path.read_text(encoding="utf-8"))
                    segments = data.get("transcription", [])
                    return " ".join(s.get("text", "").strip() for s in segments).strip()
                return result.stdout.decode("utf-8", errors="replace").strip()

            if engine == "faster-whisper":
                from faster_whisper import WhisperModel  # type: ignore

                if self._model is None:
                    self._model = WhisperModel(self.cfg.whisper_model_size, compute_type="int8")
                segments, _ = self._model.transcribe(str(path), language=self.cfg.language)
                return " ".join(segment.text.strip() for segment in segments).strip()

            if engine == "whisper":
                import whisper  # type: ignore

                if self._model is None:
                    self._model = whisper.load_model(self.cfg.whisper_model_size)
                result = self._model.transcribe(str(path), language=self.cfg.language)
                return str(result.get("text", "")).strip()
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired,
                OSError, ImportError, json.JSONDecodeError):
            return ""
        return ""
