# Roadmap

Was jetzt steht (v0.1) und was als Nächstes sinnvoll ist.

## Steht

- [x] SQLite-Kern, 13 Tabellen, ohne Fremdpakete
- [x] Aufgaben, Gewohnheiten mit Streaks, Notizen, Termine, Stimmungstagebuch
- [x] Trading-Journal mit R-Multiple, Konten, Prop-Firm-Wachhund
- [x] CSV-Import (MT4/MT5, cTrader, generisch) mit Duplikat-Erkennung
- [x] Kennzahlen, Aufschlüsselung nach Symbol/Setup/Wochentag/Stunde, Leck-Analyse
- [x] Positionsgrößen- und CRV-Rechner mit Währungswarnung
- [x] Marktdaten über FMP, Indikatoren (SMA/EMA/RSI/ATR), Trend-Bias, Levels
- [x] Wirtschaftskalender, Makro-Dashboard, Nachrichten
- [x] Morgen-Briefing als Markdown, HTML und Sprache
- [x] Agentenschleife mit 38 Werkzeugen, Anthropic / Ollama / Offline
- [x] Langzeitgedächtnis und Persönlichkeit
- [x] Sprachmodus (TTS/STT steckbar), Web-Dashboard, Zeitplaner
- [x] 112 Tests, alle ohne Netz

## Steht (v0.2)

- [x] **App fürs Handy** (PWA): installierbar, dunkel, fünf Bereiche, offline lesbar
- [x] Vermögensübersicht über alle Konten mit Verlaufskurve je Konto
- [x] Ziele: messbar, mit Deadline, Tempo-Rechnung, auch abwärts (abnehmen, Schulden)
- [x] Ziele aktualisieren sich selbst aus dem Kontostand
- [x] FundedNext-Anbindung: Stände, Equity, Phase, echte Puffer des Anbieters
- [x] Push per ntfy und Telegram mit Dedupe
- [x] Warnregeln: Risikolimit, Ziel hinter Plan, Wirtschaftstermin in Kürze
- [x] Ereignisstrom: offene App-Fenster aktualisieren sich von selbst
- [x] Intervall-Jobs im Zeitplaner (Abgleich alle 30 Min, Warnungen alle 15 Min)
- [x] 201 Tests, alle ohne Netz

## Als Nächstes

### Trading
- [ ] MT5-Live-Anbindung für offene Positionen
- [ ] Weitere Prop-Firms (FTMO, The5ers) als eigene Connectoren
- [ ] Screenshots zu Trades, Setup-Checkliste vor dem Entry
- [ ] Backtest einer Regel gegen das eigene Journal ("was wäre ohne Fade-Setup?")
- [ ] Korrelationswarnung: zwei offene Trades im selben Risiko

### Leben
- [ ] CalDAV/iCal-Import für echte Termine
- [ ] Wiederkehrende Aufgaben
- [ ] Wochenrückblick als eigene Routine

### Markt
- [ ] Session-Ranges (Asien/London/New York) im Briefing
- [ ] Alarme: Preis erreicht Level, Wirtschaftstermin in 15 Minuten
- [ ] Mehrere Zeitebenen in der Analyse (H4 + D1)

### App
- [ ] Trade direkt in der App eintragen (Formular statt Chat)
- [ ] Web Push (VAPID), damit auch ohne ntfy/Telegram Meldungen ankommen
- [ ] Diagramm der Equity-Kurve in groß, mit Tooltip
- [ ] Spracheingabe im Chat (Mikrofon-Knopf)

### Assistent
- [ ] Wake-Word statt Enter-Taste (openWakeWord)
- [ ] Streaming-Antworten im Terminal und in der App
- [ ] Telegram als Gegenrichtung: Jarvis antwortet auch im Messenger
- [ ] Proaktive Meldungen ("du hast 3 Tage nicht ins Journal geschrieben")

### Technik
- [ ] Verschlüsselte Datenbank (SQLCipher) als Option
- [ ] Export: Journal als CSV/Excel, Briefings als PDF
- [ ] Docker-Image für den Dauerbetrieb auf einem Mini-PC
