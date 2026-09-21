"""Einfacher Zeitplaner ohne Fremdpakete: taegliche Jobs zur festen Uhrzeit."""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

Job = Callable[[], None]


@dataclass
class DailyJob:
    name: str
    hour: int
    minute: int
    action: Job
    weekdays_only: bool = False
    last_run: str = ""            # ISO-Datum des letzten Laufs

    def due(self, now: datetime) -> bool:
        if self.weekdays_only and now.weekday() >= 5:
            return False
        if self.last_run == now.date().isoformat():
            return False
        return (now.hour, now.minute) >= (self.hour, self.minute)

    def next_run(self, now: datetime | None = None) -> datetime:
        now = now or datetime.now()
        candidate = now.replace(hour=self.hour, minute=self.minute, second=0, microsecond=0)
        if candidate <= now or self.last_run == now.date().isoformat():
            candidate += timedelta(days=1)
        while self.weekdays_only and candidate.weekday() >= 5:
            candidate += timedelta(days=1)
        return candidate


@dataclass
class Scheduler:
    """Prueft jede Minute, ob ein Job faellig ist. Verpasste Jobs laufen nach."""

    jobs: list[DailyJob] = field(default_factory=list)
    interval_seconds: int = 30
    logger: Callable[[str], None] = print
    _stop: threading.Event = field(default_factory=threading.Event)

    def add(self, name: str, hour: int, minute: int, action: Job,
            *, weekdays_only: bool = False) -> DailyJob:
        job = DailyJob(name=name, hour=hour, minute=minute, action=action,
                       weekdays_only=weekdays_only)
        self.jobs.append(job)
        return job

    def tick(self, now: datetime | None = None) -> list[str]:
        now = now or datetime.now()
        fired = []
        for job in self.jobs:
            if not job.due(now):
                continue
            job.last_run = now.date().isoformat()
            try:
                job.action()
                fired.append(job.name)
                self.logger(f"[{now:%H:%M}] Job ausgefuehrt: {job.name}")
            except Exception as exc:                                    # noqa: BLE001
                self.logger(f"[{now:%H:%M}] Job {job.name} fehlgeschlagen: {exc}")
        return fired

    def plan(self) -> list[dict[str, str]]:
        now = datetime.now()
        return [
            {"job": job.name, "naechster_lauf": job.next_run(now).strftime("%d.%m.%Y %H:%M"),
             "zuletzt": job.last_run or "nie"}
            for job in self.jobs
        ]

    def run_forever(self) -> None:
        self.logger("Jarvis-Scheduler laeuft. Beenden mit Strg+C.")
        for entry in self.plan():
            self.logger(f"  - {entry['job']}: naechster Lauf {entry['naechster_lauf']}")
        try:
            while not self._stop.is_set():
                self.tick()
                self._stop.wait(self.interval_seconds)
        except KeyboardInterrupt:
            self.logger("Scheduler beendet.")

    def stop(self) -> None:
        self._stop.set()


def build_default_scheduler(ctx, *, logger: Callable[[str], None] = print) -> Scheduler:
    """Die Standard-Routinen: Morgen-Briefing, Abend-Rueckblick, Journal-Erinnerung."""
    from jarvis.briefing import builder, render

    cfg = ctx.config
    scheduler = Scheduler(logger=logger)

    def morning() -> None:
        brief = builder.build(ctx, include_market=True, with_llm=True)
        cfg.ensure_dirs()
        md_path = cfg.briefing_dir / f"{brief.day}.md"
        md_path.write_text(brief.markdown, encoding="utf-8")
        (cfg.briefing_dir / f"{brief.day}.html").write_text(
            render.to_html(brief.markdown, title=f"Briefing {brief.day}"), encoding="utf-8"
        )
        logger(f"Briefing geschrieben: {md_path}")
        if cfg.briefing.speak:
            from jarvis.voice.tts import TTS

            TTS(cfg.voice).speak(builder.to_speech_text(brief.data))

    def evening() -> None:
        from jarvis.skills.base import run_skill

        run_skill(ctx, "evening_review", {})
        logger("Abend-Rueckblick erzeugt.")

    def journal_reminder() -> None:
        open_trades = ctx.journal.list_trades(open_only=True, limit=10)
        today = date.today().isoformat()
        closed_today = [
            t for t in ctx.journal.list_trades(limit=50)
            if str(t.get("closed_at") or "").startswith(today)
        ]
        missing = [t for t in closed_today if not (t.get("notes") or t.get("rating"))]
        if missing or open_trades:
            ctx.life.add_task(
                f"Trading-Journal nachtragen ({len(missing)} Trades ohne Notiz)",
                due=today, priority=1, project="Trading",
            )
            logger(f"Journal-Erinnerung angelegt ({len(missing)} offene Eintraege).")

    scheduler.add("morgen-briefing", cfg.briefing.hour, cfg.briefing.minute, morning,
                  weekdays_only=cfg.briefing.weekdays_only)
    scheduler.add("abend-rueckblick", 20, 30, evening)
    scheduler.add("journal-erinnerung", cfg.trading.journal_reminder_hour, 0, journal_reminder)
    return scheduler
