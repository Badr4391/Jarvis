"""Zentraler Kontext: haelt alle Dienste zusammen, baut sie bei Bedarf."""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import cached_property

from jarvis.config import Config, get_config
from jarvis.connectors.sync import AccountSync
from jarvis.core.memory import Memory
from jarvis.life.goals import GoalManager
from jarvis.life.manager import LifeManager
from jarvis.market.fmp import FMPClient
from jarvis.market.service import MarketService
from jarvis.notify.center import NotificationCenter
from jarvis.storage.db import Database, get_db
from jarvis.trading.journal import TradingJournal


@dataclass
class JarvisContext:
    """Ein Objekt, das jede Skill-Funktion bekommt."""

    config: Config = field(default_factory=get_config)
    _db: Database | None = None

    @property
    def db(self) -> Database:
        if self._db is None:
            self.config.ensure_dirs()
            self._db = get_db(self.config.db_path)
        return self._db

    @cached_property
    def memory(self) -> Memory:
        return Memory(self.db)

    @cached_property
    def life(self) -> LifeManager:
        return LifeManager(self.db)

    @cached_property
    def goals(self) -> GoalManager:
        return GoalManager(self.db)

    @cached_property
    def journal(self) -> TradingJournal:
        return TradingJournal(self.db)

    @cached_property
    def sync(self) -> AccountSync:
        return AccountSync(db=self.db, journal=self.journal)

    @cached_property
    def notify(self) -> NotificationCenter:
        return NotificationCenter(db=self.db)

    @cached_property
    def market(self) -> MarketService:
        client = FMPClient(
            self.config.market.fmp_api_key,
            base_url=self.config.market.base_url,
            cache_ttl=self.config.market.cache_ttl_seconds,
        )
        service = MarketService(self.db, client)
        service.seed_watchlist(self.config.market.watchlist)
        return service

    @cached_property
    def llm(self):
        from jarvis.llm.registry import build_provider

        return build_provider(self.config)


def build_context(config: Config | None = None) -> JarvisContext:
    return JarvisContext(config=config or get_config())
