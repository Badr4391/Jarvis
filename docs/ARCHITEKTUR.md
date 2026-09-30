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
      CLI          App (PWA, Handy)        Sprachmodus       Zeitplaner
       |                   |                     |                |
       |          HTTP + Ereignisstrom           |                |
       +---------+---------+----------+----------+----------------+
                 |                    |
            Assistant             Skills (47)
        (Agentenschleife)     task_* goal_* trade_* risk_*
                 |            market_* memory_* notify_* brief_*
              LLM-Provider             |
   Anthropic | Ollama | Offline        |
                                  JarvisContext
                                       |
   +--------+--------+--------+--------+--------+---------+--------+
   |        |        |        |        |        |         |        |
 Life     Goals   Trading  Connect.  Market  Memory   Briefing   Notify
   |        |        |        |        |        |         |        |
   +--------+--------+--------+--------+--------+---------+--------+
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
`accounts`, `trades`, `watchlist`, `briefings`, `goals` + `goal_log`,
`balance_history`, `notifications`, `meta`.

`trades` hat `UNIQUE(account_id, external_id)` — deshalb ist der CSV-Import
wiederholbar, ohne Duplikate zu erzeugen. `balance_history` hat
`UNIQUE(account_id, day)`, damit ein Abgleich alle 30 Minuten trotzdem genau
einen Punkt pro Tag ergibt.

Migrationen sind additiv: neue Tabellen über `CREATE TABLE IF NOT EXISTS`, neue
Spalten über die Liste `ADDED_COLUMNS` in `storage/db.py`, die beim Start
nachgezogen wird. Eine alte Datenbank öffnet sich also ohne Zutun.

### Die App

Eine PWA ohne Framework: `index.html` + `app.css` + `app.js` + `sw.js` + Manifest,
zusammen unter 40 KB. Der Startbildschirm holt seine Daten in **einem** Aufruf
(`/api/heute`) — ein Roundtrip zählt auf dem Handy mehr als sauber getrennte
Endpunkte.

Aktualisiert wird auf drei Wegen, absichtlich mehrfach abgesichert:

1. **Ereignisstrom** (`/api/stream`, Server-Sent Events) — der Server meldet sich,
   wenn sich etwas ändert. Bricht die Verbindung, verbindet die App neu.
2. **Sichtbarkeitswechsel** — App wieder im Vordergrund, also neu laden.
3. **Alle zwei Minuten**, solange die App sichtbar ist.

Der Service Worker hält die Hülle im Cache (erst Cache, dann Netz) und Daten nach
dem Muster „erst Netz, sonst letzter Stand". Deshalb zeigt die App unterwegs die
zuletzt bekannten Zahlen statt einer Fehlerseite — sichtbar als Hinweis, nicht als
stille Lüge.

**Farben** folgen einer validierten Palette: eine Serienfarbe (Blau) für alle
Verlaufskurven und Fortschrittsbalken, dazu die reservierten Statusfarben. Weil
Rot und Grün für Rot-Grün-Blinde kaum trennbar sind, trägt **jeder** Status
zusätzlich ein Zeichen und ein Wort (`● OK`, `▲ VORSICHT`, `■ STOP`) und jede Zahl
ihr Vorzeichen. Die Farbe verstärkt, sie trägt nie allein.

### Kontostände von außen

`connectors/` trennt Transport und Bedeutung. Ein Connector liefert
`AccountSnapshot`-Objekte; `AccountSync` entscheidet, ob das ein neues Konto ist
(Zuordnung über `provider` + `external_id`, dann über den Namen), schreibt den
Stand und einen Punkt in die Verlaufskurve.

Meldet der Anbieter eigene Puffer (FundedNext liefert
`daily_loss_till_now` und `max_loss_till_now`), gewinnen die gegenüber Jarvis'
eigener Rechnung — der Anbieter kennt seine Regeln besser.

Fehler eines Connectors werden gesammelt, nicht geworfen: ein abgelaufenes Token
darf den Abgleich der anderen Konten nicht verhindern.

### Warnungen

`notify/center.py` kennt drei Regeln — Risikolimit, Ziele hinter Plan,
Wirtschaftstermin in Kürze. Jede Meldung landet **immer** in der Datenbank; der
Versand aufs Handy ist die Kür. Eine Meldung mit gleichem Titel geht innerhalb
von vier Stunden nur einmal raus, sonst wäre der wichtigste Push der, den man
wegwischt.

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

Kein Cron, kein APScheduler: eine Schleife, die jede halbe Minute prüft, was fällig
ist. Zwei Arten von Jobs:

- **Tagesjobs** zu fester Uhrzeit. Verpasste laufen nach (Rechner war aus), aber
  höchstens einmal pro Tag.
- **Intervalljobs** alle n Minuten, optional nur in einem Zeitfenster — damit
  nachts um drei keine Warnung kommt.

## Was bewusst fehlt

- Keine Multi-User-Verwaltung — das ist *dein* Assistent.
- Keine Orderausführung. Jarvis schreibt mit und rechnet, er handelt nicht.
- Kein ORM, keine Migrationsbibliothek. Ein Schema, `CREATE TABLE IF NOT EXISTS`.
