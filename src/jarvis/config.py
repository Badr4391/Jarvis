"""Konfiguration: .env + YAML + Umgebungsvariablen, ohne Fremdpakete."""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_dotenv(path: Path) -> None:
    """Minimaler .env Loader. Bestehende Umgebungsvariablen gewinnen."""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        import yaml  # type: ignore
    except ImportError:
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


@dataclass
class LLMConfig:
    provider: str = "anthropic"
    model: str = "claude-opus-5"
    api_key: str = ""
    ollama_host: str = "http://localhost:11434"
    max_tokens: int = 2048
    temperature: float = 0.6
    timeout: int = 120

    @property
    def available(self) -> bool:
        if self.provider == "anthropic":
            return bool(self.api_key)
        if self.provider == "ollama":
            return True
        return self.provider == "echo"


@dataclass
class VoiceConfig:
    tts: str = "auto"
    stt: str = "auto"
    piper_model: str = ""
    piper_bin: str = "piper"
    whisper_cpp_bin: str = ""
    whisper_cpp_model: str = ""
    whisper_model_size: str = "base"
    language: str = "de"
    record_seconds: float = 8.0
    sample_rate: int = 16000


@dataclass
class MarketConfig:
    fmp_api_key: str = ""
    base_url: str = "https://financialmodelingprep.com"
    watchlist: list[str] = field(
        default_factory=lambda: ["EURUSD", "GBPUSD", "XAUUSD", "^GSPC", "BTCUSD"]
    )
    news_limit: int = 8
    cache_ttl_seconds: int = 300


@dataclass
class TradingConfig:
    default_account: str = ""
    default_risk_pct: float = 0.5
    max_trades_per_day: int = 3
    max_risk_per_day_pct: float = 1.5
    journal_reminder_hour: int = 21


@dataclass
class BriefingConfig:
    hour: int = 7
    minute: int = 0
    weekdays_only: bool = False
    speak: bool = False
    sections: list[str] = field(
        default_factory=lambda: [
            "greeting",
            "agenda",
            "tasks",
            "habits",
            "trading",
            "markets",
            "economics",
            "news",
            "focus",
        ]
    )


@dataclass
class UserConfig:
    name: str = "Badr"
    language: str = "de"
    timezone: str = "Europe/Berlin"
    tone: str = "freundschaftlich, direkt, motivierend"


@dataclass
class Config:
    data_dir: Path = field(default_factory=lambda: REPO_ROOT / "data")
    user: UserConfig = field(default_factory=UserConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    voice: VoiceConfig = field(default_factory=VoiceConfig)
    market: MarketConfig = field(default_factory=MarketConfig)
    trading: TradingConfig = field(default_factory=TradingConfig)
    briefing: BriefingConfig = field(default_factory=BriefingConfig)

    @property
    def db_path(self) -> Path:
        return self.data_dir / "jarvis.db"

    @property
    def briefing_dir(self) -> Path:
        return self.data_dir / "briefings"

    @property
    def audio_dir(self) -> Path:
        return self.data_dir / "audio"

    def ensure_dirs(self) -> None:
        for path in (self.data_dir, self.briefing_dir, self.audio_dir):
            path.mkdir(parents=True, exist_ok=True)

    def to_dict(self) -> dict[str, Any]:
        raw = asdict(self)
        raw["data_dir"] = str(self.data_dir)
        raw["llm"]["api_key"] = "***" if self.llm.api_key else ""
        raw["market"]["fmp_api_key"] = "***" if self.market.fmp_api_key else ""
        return raw


def _apply(section: Any, values: dict[str, Any]) -> None:
    for key, value in (values or {}).items():
        if hasattr(section, key) and value is not None:
            setattr(section, key, value)


def load_config(config_path: Path | str | None = None, *, env_file: Path | str | None = None) -> Config:
    """Laedt Konfiguration. Reihenfolge: Defaults < YAML < .env/Umgebung."""
    _load_dotenv(Path(env_file) if env_file else REPO_ROOT / ".env")

    cfg = Config()

    yaml_path = Path(config_path) if config_path else REPO_ROOT / "config" / "jarvis.yaml"
    raw = _load_yaml(yaml_path)
    if "data_dir" in raw:
        cfg.data_dir = Path(str(raw["data_dir"])).expanduser()
    _apply(cfg.user, raw.get("user", {}))
    _apply(cfg.llm, raw.get("llm", {}))
    _apply(cfg.voice, raw.get("voice", {}))
    _apply(cfg.market, raw.get("market", {}))
    _apply(cfg.trading, raw.get("trading", {}))
    _apply(cfg.briefing, raw.get("briefing", {}))

    env = os.environ
    if env.get("JARVIS_DATA_DIR"):
        cfg.data_dir = Path(env["JARVIS_DATA_DIR"]).expanduser()
    if env.get("JARVIS_USER_NAME"):
        cfg.user.name = env["JARVIS_USER_NAME"]
    if env.get("JARVIS_LANG"):
        cfg.user.language = env["JARVIS_LANG"]
        cfg.voice.language = env["JARVIS_LANG"]
    if env.get("JARVIS_TIMEZONE"):
        cfg.user.timezone = env["JARVIS_TIMEZONE"]

    if env.get("JARVIS_LLM_PROVIDER"):
        cfg.llm.provider = env["JARVIS_LLM_PROVIDER"]
    if env.get("JARVIS_LLM_MODEL"):
        cfg.llm.model = env["JARVIS_LLM_MODEL"]
    cfg.llm.api_key = env.get("ANTHROPIC_API_KEY", cfg.llm.api_key)
    cfg.llm.ollama_host = env.get("OLLAMA_HOST", cfg.llm.ollama_host)

    if env.get("JARVIS_TTS"):
        cfg.voice.tts = env["JARVIS_TTS"]
    if env.get("JARVIS_STT"):
        cfg.voice.stt = env["JARVIS_STT"]
    cfg.voice.piper_model = env.get("PIPER_MODEL", cfg.voice.piper_model)
    cfg.voice.whisper_cpp_bin = env.get("WHISPER_CPP_BIN", cfg.voice.whisper_cpp_bin)
    cfg.voice.whisper_cpp_model = env.get("WHISPER_CPP_MODEL", cfg.voice.whisper_cpp_model)

    cfg.market.fmp_api_key = env.get("FMP_API_KEY", cfg.market.fmp_api_key)

    cfg.data_dir = cfg.data_dir.expanduser()
    if not cfg.data_dir.is_absolute():
        cfg.data_dir = (REPO_ROOT / cfg.data_dir).resolve()
    return cfg


_CACHED: Config | None = None


def get_config(refresh: bool = False) -> Config:
    global _CACHED
    if _CACHED is None or refresh:
        _CACHED = load_config()
    return _CACHED
