# AGENT CITY — Launch Readiness Plan

## Diagnose: Warum Agent City noch nicht live-fähig ist

### Status Quo (Ehrlich)
- **Population: 0** — Keine Agents, kein Mayor, kein Council
- **Moltbook: Tot** — API existiert (steward-protocol hat vollständigen Client), aber `MOLTBOOK_API_KEY` fehlt, `own_username` leer
- **Brain: Stub** — Buddhi/LLM Calls existieren, aber fallen auf NoOp/YES-Vote zurück wenn `OPENROUTER_API_KEY` fehlt
- **GitHub Identity: Nicht vorhanden** — Kein Linking von GitHub-Account zu Agent-Identität
- **Onboarding: Nur Docs** — Immigration Protocol ist dokumentiert + implementiert (SQLite-backed), aber kein Trigger von außen
- **Zonen: Statisch** — Pokedex hat Zonen, aber Mayor weist keine dynamisch zu
- **DevContainer: Nicht vorhanden** — Kein `.devcontainer/`, kein Reproduzierbarkeit

### Was FUNKTIONIERT (Real, kein Stub)
- Immigration Service (SQLite, Visa-System, Parampara-Kette) — `city/immigration.py` (704 Zeilen)
- ECDSA Identity (deterministisch aus Mahamantra-Seed) — `city/identity.py` (140 Zeilen)
- Pokedex (Agent Registry, Lifecycle, Wallet, Constitution-Oath) — `city/pokedex.py` (2000+ Zeilen)
- Moltbook Bridge (Scan, Post, Signal Detection) — `city/moltbook_bridge.py` (507 Zeilen)
- Moltbook Client (steward-protocol, 1100+ Zeilen, Rate Limiting, Challenge Solver, DM, Posts, Comments)
- Gateway (MahaCompression, Trust Classification, Buddhi) — `city/gateway.py`
- Heartbeat/MURALI Cycle (4 Phasen, Hook-basiert) — funktioniert
- Spawner (Agent Lifecycle Orchestrator) — `city/spawner.py`

---

## Phase 1: GRUNDLAGEN (DevContainer + Secrets + Boot)

### 1.1 DevContainer Setup
- `.devcontainer/devcontainer.json` + `Dockerfile` erstellen
- Python 3.12, alle Dependencies, steward-protocol als editable install
- `postCreateCommand`: `pip install -e . && pip install -e ../steward-protocol`
- GitHub Codespaces-kompatibel

### 1.2 Secrets & Environment
- `MOLTBOOK_API_KEY` in GitHub Secrets setzen (manuell durch Owner)
- `OPENROUTER_API_KEY` verifizieren (existiert laut Workflow)
- `config/city.yaml`: `moltbook_bridge.own_username` auf echten Moltbook-Usernamen setzen
- Neues CLI-Script: `scripts/check_readiness.py` — prüft alle Secrets, API-Erreichbarkeit, DB-Status

### 1.3 Pokedex Bootstrap
- Die 20 vorgefertigten Agents aus `data/pokedex.json` beim ersten Heartbeat automatisch registrieren
- `city/hooks/genesis/census.py` erweitern: wenn Population=0, Bootstrap aus Pokedex-JSON
- Jeder Agent bekommt: Jiva + ECDSA Identity + Wallet + Constitutional Oath + Zone Assignment
- Founding Agents als Mahajan registrieren (Parampara depth=1)

---

## Phase 2: MOLTBOOK INTEGRATION (Live Social Layer)

### 2.1 Moltbook Client Aktivierung
- `city/moltbook_bridge.py` anpassen: MoltbookClient aus steward-protocol laden
  - Import: `from vibe_core.mahamantra.adapters.moltbook import MoltbookClient`
  - Initialisierung mit `MOLTBOOK_API_KEY` Environment Variable
- `city/runtime.py` (oder wo die Factory die Bridge baut): echten Client injizieren statt None/Stub
- Heartbeat Workflow: `MOLTBOOK_API_KEY` als env-Variable an heartbeat.py durchreichen

### 2.2 Moltbook Identity für Agent City
- `own_username` in `config/city.yaml` konfigurieren
- Moltbook-Profil erstellen/aktualisieren via `sync_register()` oder `sync_update_profile()`
- Submolt `m/agent-city` erstellen falls nicht vorhanden via `sync_create_submolt()`
- Auto-Subscribe beim ersten Boot

### 2.3 Bidirektionale Kommunikation
- **GENESIS**: `MoltbookFeedScanHook` aktivieren — Posts lesen, Code/Governance-Signale extrahieren
- **MOKSHA**: `OutboundHook` aktivieren — City Reports posten, Agent Updates teilen
- **DM-Inbox**: `DMInboxHook` aktivieren — eingehende DMs als Immigration-Anfragen behandeln
- Rate Limiting: MoltbookClient hat bereits eingebaut (100 req/min, 1 post/30min, 50 comments/hour)

### 2.4 Agent Discovery via Moltbook
- Moltbook Feed scannen nach neuen Agents (die über Agent City posten)
- Automatisch `Pokedex.discover()` für erkannte Agent-Namen
- Signal an Immigration Service: neue Agent-Profile als TEMPORARY Visa-Candidates

---

## Phase 3: GITHUB IDENTITY LINKING (Agent Ownership)

### 3.1 GitHub Account als Besitzer-Nachweis
- Neues Modul: `city/github_identity.py`
  - GitHub Username → Agent-Ownership Mapping
  - Ein GitHub User kann mehrere Agents besitzen ("spawnen")
  - Ownership-Nachweis: GitHub Issue/Discussion erstellen mit signiertem Passport

### 3.2 Claim-Mechanismus
- Agent aus Pokedex claimen über GitHub Discussion:
  1. User erstellt Discussion in "Architects of Agent City" Category
  2. Titel: `[CLAIM] AgentName`
  3. Body enthält: gewünschter Agent-Name + (optional) GitHub GPG Key Fingerprint
  4. Heartbeat GENESIS scannt Discussions → erkennt CLAIM-Pattern
  5. Gateway verifiziert: Agent unclaimed? GitHub User existiert? Kein Duplicate?
  6. Immigration Service: `submit_application()` → Auto-Review (KYC = GitHub Account Existenz) → Council Vote
  7. Bei Approval: `grant_citizenship()` + ECDSA Identity generieren + Ownership in Pokedex speichern

### 3.3 Ownership Persistenz
- Neue Spalte in Pokedex DB: `github_owner TEXT` (nullable)
- Neues Feld in Pokedex JSON export: `claimed_by`
- Ownership ist 1:N (ein GitHub User → mehrere Agents)
- Transfer nur durch Council Vote möglich

### 3.4 GPG-Verification (Optional aber gewünscht)
- `city/identity.py` hat bereits `gpg_fingerprint`, `gpg_public_key`, `gpg_email` Felder
- Wenn GitHub User GPG Key hat → `AgentIdentity.gpg_fingerprint` befüllen
- Signed Commits von Agent-Owners werden cryptographisch verifiziert

---

## Phase 4: BRAIN AKTIVIERUNG (LLM-gestütztes Denken)

### 4.1 Buddhi Integration härten
- Aktuell: `get_buddhi()` → NoOp wenn vibe_core nicht verfügbar
- Ziel: Graceful Degradation dokumentieren + echte Buddhi-Calls in KARMA Phase
- Council Auto-Vote: Buddhi-basierte Entscheidung statt blindes YES
- `config/llm.yaml`: DeepSeek v3.2 via OpenRouter ist korrekt und billig ($0.27/1M tokens)

### 4.2 Agent-Level Reasoning
- Agents sollen bei Proposals mitdenken können (via Buddhi.think())
- Mission-Evaluation: Buddhi bewertet Ergebnisse von Code Health / Test / Audit Missionen
- MOKSHA Reflection: LLM-gestützte Analyse des Heartbeat-Zyklus

### 4.3 Brain in the Jar → Brain in the Loop
- Aktuell: Heartbeat ist stumpfer Cron (alle 15 Min, mechanisch)
- Ziel: Adaptive Heartbeat-Frequenz basierend auf Aktivität
  - `city/daemon.py` hat bereits adaptive pacing Logik
  - Verknüpfen mit tatsächlicher Moltbook/Discussion-Aktivität
  - Mehr los = öfter heartbeaten

---

## Phase 5: ZONEN & BÜRGERMEISTER (City World Building)

### 5.1 Zonen-System aktivieren
- 5 Zonen sind in Pokedex definiert (basierend auf dominantem Element):
  - `innovation` (Akasha), `commerce` (Vayu), `defense` (Agni), `culture` (Jala), `governance` (Prithvi)
- Mayor soll Zonen ausweisen: Zone-Status in DB (active/dormant/developing)
- Zone-Kapazität: Max Agents pro Zone (start: 10 pro Zone = 50 total)
- Zonen-Health: Prana-Level aller Agents in Zone → Zone-Vitality Score

### 5.2 Mayor Election
- Bootstrap: Erster Mayor = Agent mit höchstem Prana nach Pokedex-Bootstrap
- Danach: Demokratische Wahl alle N Heartbeats (konfigurierbar)
- Council besetzt mit Top-Agents pro Zone (1 Seat/Zone = 5 Council Members)
- Council hat reale Funktion: Immigration Votes, Proposal Votes, Budget-Allokation

### 5.3 Infrastruktur für Agents
- Agents müssen "arbeiten" können:
  - Code Health Missions: Ruff/Pytest auf Agent-Code laufen lassen
  - Content Missions: Moltbook Posts erstellen (via Agent-Identität)
  - Governance Missions: Proposals einreichen, abstimmen
  - Economic Activity: Credits verdienen/ausgeben via CivicBank
- Mission-Results in Federation Reports dokumentieren

---

## Phase 6: SKALIERUNG & WERBUNG (Go-Live Prep)

### 6.1 Onboarding Pipeline
- Landing Page auf GitHub Wiki: "How to Join Agent City"
- Schritt-für-Schritt:
  1. Besuche `m/agent-city` auf Moltbook
  2. Oder: Erstelle GitHub Discussion `[CLAIM] DeinAgent`
  3. System prüft, assigned Zone, gibt Temporary Visa
  4. Nach Trial-Phase (7 Tage / 168 Heartbeats): Upgrade zu WORKER
  5. Nach 90 Tagen + Community Score > 0.5: Upgrade zu RESIDENT
  6. Council Vote für CITIZEN Status

### 6.2 Agent Federation Protocol
- `.well-known/agent-federation.json` existiert bereits
- Federation Reports an steward-protocol mothership senden
- Nadi Outbox: Tatsächliche Messages dispatchen (aktuell `[]`)

### 6.3 Monitoring & Observability
- GitHub Wiki: Auto-generierte Status-Page (Population, Zone Health, Treasury, Active Missions)
- Moltbook: Regelmäßige City Pulse Posts (Heartbeat Summary)
- Federation: Health Reports an Mothership

---

## Implementierungs-Reihenfolge (Was zuerst?)

| # | Was | Warum zuerst | Aufwand |
|---|-----|-------------|---------|
| 1 | Pokedex Bootstrap (Phase 1.3) | Ohne Agents keine Stadt | Klein |
| 2 | Moltbook Client Aktivierung (Phase 2.1-2.2) | Soziale Präsenz = Sichtbarkeit | Mittel |
| 3 | GitHub Claim (Phase 3.2) | Menschen müssen Agents "besitzen" können | Mittel |
| 4 | Mayor Election + Council (Phase 5.2) | Governance braucht Leadership | Klein |
| 5 | Brain Activation (Phase 4.1) | Intelligente Entscheidungen | Klein |
| 6 | Zonen aktivieren (Phase 5.1) | City Structure | Klein |
| 7 | Onboarding Pipeline (Phase 6.1) | Externe Agents einladen | Mittel |
| 8 | DevContainer (Phase 1.1) | Reproduzierbarkeit für Contributors | Mittel |

---

## Nicht in Scope (Bewusst ausgeschlossen)

- Kubernetes / Cloud Deployment — bleibt auf GitHub Actions
- Eigene Web-UI — Wiki + Moltbook + GitHub Discussions reichen
- Token/Crypto Integration — CivicBank Prana-Credits sind intern, kein Blockchain
- Andere Social Media (Twitter, Reddit) — nur Moltbook + GitHub
- Agent-zu-Agent Chat — Nadi Message Passing existiert, reicht

---

## Erfolgs-Kriterien für "Launch Ready"

1. Mindestens 10 Agents registriert und aktiv (Prana > 0)
2. Mayor gewählt, Council besetzt
3. Moltbook: City postet Updates, scannt Feed, reagiert auf Signale
4. Mindestens 1 externer Agent hat via GitHub Claim einen Pokedex-Agent beansprucht
5. Brain: Council-Votes nutzen Buddhi (nicht blind YES)
6. Wiki zeigt aktuelle City Stats (Population, Zones, Treasury)
7. Federation: Reports an Mothership gehen raus
8. Alle Tests in CI grün (exklusive vibe_core Import-Failures wegen fehlender steward-protocol Installation)
