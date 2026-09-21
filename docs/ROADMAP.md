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

## Als Nächstes

### Trading
- [ ] FundedNext-Konten direkt synchronisieren (MCP-Anbindung steht bereit)
- [ ] MT5-Live-Anbindung für offene Positionen
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

### Assistent
- [ ] Wake-Word statt Enter-Taste (openWakeWord)
- [ ] Streaming-Antworten im Terminal
- [ ] Telegram- oder Signal-Anbindung fürs Briefing unterwegs
- [ ] Proaktive Meldungen ("du hast 3 Tage nicht ins Journal geschrieben")

### Technik
- [ ] Verschlüsselte Datenbank (SQLCipher) als Option
- [ ] Export: Journal als CSV/Excel, Briefings als PDF
- [ ] Docker-Image für den Dauerbetrieb auf einem Mini-PC
