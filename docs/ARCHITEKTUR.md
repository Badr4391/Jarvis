# Architektur

## Leitgedanken

1. **Local-first.** Der Kern läuft mit der Standardbibliothek. Keine Cloud nötig,
   keine Datenbank-Server, kein Framework. Alles liegt in einer SQLite-Datei.
2. **Alles darf fehlen.** Kein API-Key, kein Mikrofon, kein Sprachmodell — Jarvis
   bleibt bedienbar und sagt, was fehlt, statt abzustürzen.
3. **Ein Skill, drei Oberflächen.** Jede Funktion, die als Skill registriert ist,
   ist automatisch im Chat, im Dashboard und in der Kommandozeile verfügbar.
4. **Keine erfundenen Zahlen.** Werte kommen aus der Datenbank oder von einer API.
   Fehlt etwas, steht das da.

## Schichten

```
      CLI            Web-Dashboard          Sprachmodus
       |                   |                     |
       +---------+---------+----------+----------+
                 |                    |
            Assistant             Skills (38)
        (Agentenschleife)     task_* trade_* risk_*
                 |            market_* memory_* brief_*
              LLM-Provider             |
   Anthropic | Ollama | Offline        |
                                  JarvisContext
                                       |
        +--------+--------+--------+---+----+--------+
        |        |        |        |        |        |
      Life    Trading   Market   Memory  Briefing  Voice
        |        |        |        |        |
        +--------+--------+--------+--------+
                          |
                    SQLite (Database)
```

### `JarvisContext`

Ein Objekt, das jede Skill-Funktion als erstes Argument bekommt. Es baut Dienste
faul (`cached_property`), damit ein einfaches `jarvis task list` weder Netz noch
Sprachmodell anfasst.

### Agentenschleife (`core/assistant.py`)

1. Verlauf laden, Nutzertext anhängen
2. Modell aufrufen, mit allen Skills als Werkzeuge
3. Fordert das Modell Werkzeuge an: ausführen, Ergebnisse zurückgeben, zurück zu 2
4. Maximal 6 Runden, dann Zusammenfassung ohne Werkzeuge erzwingen
5. Frage und Antwort im Verlauf speichern

Werkzeugfehler werden zu lesbaren Ergebnissen (`FEHLER: ...`), nicht zu Abbrüchen —
das Modell kann nachfragen oder korrigieren.

### Skill-Registry (`skills/base.py`)

Der `@skill`-Dekorator erzeugt aus einer Funktion ein JSON-Schema-Werkzeug.
`run_skill` prüft Pflichtfelder, korrigiert Typen (Modelle schicken Zahlen gern als
Strings, `"1,0820"` wird zu `1.0820`) und fängt jede Ausnahme ab.

### Datenmodell

`tasks`, `habits` + `habit_log`, `notes`, `events`, `journal`, `memory`, `messages`,
`accounts`, `trades`, `watchlist`, `briefings`, `meta`.

`trades` hat `UNIQUE(account_id, external_id)` — deshalb ist der CSV-Import
wiederholbar, ohne Duplikate zu erzeugen.

### Risiko-Rechnung

Pip-Größe und Kontraktgröße hängen an der Instrumentenklasse (FX, JPY-Paare,
Metalle, Indizes, Krypto). Ist die Notierungswährung nicht die Kontowährung,
braucht die Rechnung einen Umrechnungskurs — fehlt der, rechnet Jarvis weiter,
schreibt aber eine Warnung in `note`, statt still falsch zu liegen.

Der `PropGuard` kennt zwei Grenzen: Tagesverlust (relativ zum Kontostand bei
Handelsbeginn) und Gesamtverlust (relativ zum Startkapital). Der engere Wert gilt.

### Briefing

`collect()` sammelt Bausteine (jeder darf leer sein) → `render_markdown()` baut den
Text → `render.to_html()` macht eine eigenständige HTML-Seite → `to_speech_text()`
eine gekürzte Fassung ohne Sonderzeichen fürs Vorlesen. Die LLM-Einleitung ist
optional und scheitert leise.

### Zeitplaner

Kein Cron, kein APScheduler: eine Schleife, die jede halbe Minute prüft, ob ein
Tagesjob fällig ist. Verpasste Jobs laufen nach (Rechner war aus), aber höchstens
einmal pro Tag.

## Was bewusst fehlt

- Keine Multi-User-Verwaltung — das ist *dein* Assistent.
- Keine Orderausführung. Jarvis schreibt mit und rechnet, er handelt nicht.
- Kein ORM, keine Migrationsbibliothek. Ein Schema, `CREATE TABLE IF NOT EXISTS`.
