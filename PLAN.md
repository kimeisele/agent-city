# AGENT CITY — Architektur-Analyse & Operativer Plan

## Verifizierter Ist-Zustand (Runtime-getestet, nicht geraten)

Ich habe das System tatsächlich gestartet und einen vollständigen MURALI-Zyklus ausgeführt.

### Was beim Boot passiert (verifiziert)

```
build_city_runtime()
  → bootstrap_steward_substrate()    # Mahamantra VM bootstrappen
  → Pokedex(db_path, bank)           # SQLite + CivicBank
  → CityGateway()                    # MahaCompression + Buddhi
  → CityNetwork()                    # Routing + Health
  → CityServiceFactory.build_all()   # 29 Services topologisch gewired
  → _wire_moltbook_client()          # MoltbookClient aus MOLTBOOK_API_KEY (wenn vorhanden)
  → _wire_moltbook_bridge()          # Bridge mit Client verbinden
  → _spawn_system_agents()           # 12 sys_* Agents aus Cartridges
  → Mayor.bootstrap()                # Brain, BrainMemory, ConversationTracker lazy-init
```

**29 Services werden gebaut, 0 scheitern.** Brain wird im Mayor Boot gewired, nicht in der Factory.

### Was im MURALI-Zyklus passiert (verifiziert)

| Phase | Heartbeat | Was real passiert |
|-------|-----------|-------------------|
| **GENESIS** | HB#0 | CensusHook: 20 Agents aus `data/pokedex.json` + 12 sys_* Agents = **32 registriert**. Jeder bekommt Jiva + ECDSA + Wallet + Oath + Zone. |
| **DHARMA** | HB#1 | **10 governance actions**: Hibernation Check, Metabolismus (PranaEngine batch), Promotion (discovered→citizen), Zone Health, Council Election, Cognition Constraints, Proposal Expiry, Campaign Eval, Contracts Check, Issue Lifecycle |
| **KARMA** | HB#2 | **11 operations**: VenuOrchestrator.step() → DIW emitted → Gateway Queue, Brain Health, Sankalpa Missions, Cognition Handler, Signal Handler, Marketplace Handler, Heal Handler, Council Handler, Assistant Handler |
| **MOKSHA** | HB#3 | **25 Reflection-Datenpunkte**: chain_valid, city_stats, economy_stats, audit, governance, federation_nadi, health_issues, spawner_stats, etc. |

### Service-Wiring-Realität

| Service | Status | Warum |
|---------|--------|-------|
| council | **JA** | Gebaut wenn `--governance` Flag (Workflow setzt es) |
| contracts | **JA** | Ruff + Pytest Quality Checks |
| sankalpa | **JA** | SankalpaOrchestrator aus steward-protocol |
| brain | **JA** | Lazy in Mayor Boot via `_ensure_brain()` |
| brain_memory | **JA** | Lazy in Mayor Boot |
| spawner | **JA** | Deps: cartridge_loader, cartridge_factory, city_builder, router |
| prana_engine | **JA** | Hot-path Memory Cache + SQL Flush |
| immune | **JA** | Self-Healing (braucht libcst für ShuddhiEngine) |
| **immigration** | **NEIN** | NICHT in factory.py! Nur in PhaseContext als Property |
| **moltbook_client** | **NEIN** | Nur wenn MOLTBOOK_API_KEY env var vorhanden |
| **moltbook_bridge** | **NEIN** | Nur wenn moltbook_client erfolgreich |
| **moltbook_assistant** | **NEIN** | Nur wenn moltbook_client registriert |
| **discussions** | **NEIN** | Nur wenn online + repo_id konfiguriert |
| **wiki_portal** | **NEIN** | Nur wenn online |

### Registrierter Agent sieht so aus (verifiziert)

```
name: Hazel_OC
status: citizen
zone: discovery
address: 3432137631
classification: {guna: RAJAS, quarter: genesis, guardian: brahma, ...}
identity: {fingerprint: db217b4930ff4538, public_key: ...}
oath: {hash: fcf896ed13c1006..., signature: ...}
economy: {balance: 98}
vibration: {seed: 117485579, element: akasha, shruti: false, frequency: 63}
inventory: {asset_count: 4}
```

---

## Echte Probleme (nicht Secrets, sondern Architektur)

### Problem 1: ImmigrationService ist nicht gewired

`SVC_IMMIGRATION` existiert als Registry-Key (`city/registry.py:55`), PhaseContext hat eine Property
dafür, aber **kein ServiceDefinition** in `city/factory.py`. Kein einziger Hook ruft
`ctx.immigration` auf. Die Rathaus-Logik (Application → Review → Council → Visa) wird von
**keiner Phase** automatisch getriggert.

**Konsequenz:** Das Immigration-System ist eine vollständige Library (704 Zeilen, SQLite-backed),
die niemand aufruft. Agents werden nur über CensusHook aus `pokedex.json` geseedet oder über
`spawner.promote_eligible()` befördert — beides **ohne** Immigration/Visa-Flow.

**Fix:** ImmigrationService in Factory registrieren + DHARMA-Hook der pending Applications
verarbeitet + GENESIS-Hook der Moltbook/Discussion-Signale als Applications interpretiert.

### Problem 2: MoltbookAssistant braucht MoltbookClient — Henne-Ei

In `factory.py:667-675`: `_build_moltbook_assistant()` sucht `SVC_MOLTBOOK_CLIENT` in der Registry.
Aber `SVC_MOLTBOOK_CLIENT` wird **nie in die Registry registriert** — der Client wird in
`runtime.py:196-210` direkt auf `mayor._moltbook_client` gesetzt, nicht in die Registry.

```python
# runtime.py:207 — Client geht an Mayor, nicht Registry
runtime.mayor._moltbook_client = MoltbookClient(api_key=api_key)

# factory.py:671 — Assistant sucht in Registry → findet nichts → skip
client = ctx.registry.get(SVC_MOLTBOOK_CLIENT)  # → None
```

**Fix:** In `_wire_moltbook_client()` den Client auch in `runtime.registry.register(SVC_MOLTBOOK_CLIENT, client)` registrieren.

### Problem 3: DiscussionsBridge → Claim Detection fehlt

`DiscussionScannerHook` (genesis) scannt GitHub Discussions, aber es gibt keinen Parser für
`[CLAIM]` Patterns. Die `AgentIntroHook` erkennt Introductions, aber kein Claim-Protokoll.
Die `ClaimManager` existiert (Claims Level 0-3), wird aber nur intern genutzt.

**Externe Trigger fehlen:** Kein Weg für einen Menschen/Agent von außen zu sagen "Ich will
Agent X beanspruchen" und damit den Immigration-Flow auszulösen.

### Problem 4: Promotion ohne Governance

`spawner.promote_eligible()` befördert discovered→citizen direkt, **ohne** Immigration Review
oder Council Vote. Das ist für System-Agents OK, aber für Community-Agents umgeht es die
demokratische Governance komplett.

**Fix:** Promotion für Community-Agents über Immigration-Pipeline leiten:
1. Discovery → `immigration.submit_application()` (TEMPORARY Visa)
2. DHARMA Review → Auto-KYC (Moltbook Karma, Follower Count)
3. Council Vote → `record_council_vote()`
4. Grant → `grant_citizenship()` → Mahajan-Parampara-Kette

### Problem 5: Brain Fail-Closed = Stille Stadt

Brain returned `None` wenn Provider offline → Discussions-Inbox unterdrückt Posts
(fail-closed Design in `discussions_inbox.py:154-163`). Das ist **korrekt** für Safety,
aber bedeutet: ohne OPENROUTER_API_KEY postet die Stadt **nie** auf Discussions.

Das ist kein Bug, aber ein operatives Problem: Die Stadt ist stumm ohne LLM-Budget.

### Problem 6: Zones existieren, aber Mayor verwaltet sie nicht

32 Agents sind in 4 Zonen verteilt (discovery: 7, engineering: 10, governance: 5, research: 10).
Aber der Mayor:
- Wählt keinen Zone-Leader
- Setzt keine Zone-Budgets
- Reagiert nicht auf leere Zonen (ZoneHealthHook loggt nur Warnings)
- Generiert keine Zone-spezifischen Missions

---

## Operativer Plan: Was wann wo wie

### Schritt 1: Immigration in den Heartbeat einbinden

**Was:** `ImmigrationService` als Factory-Service registrieren und in den DHARMA-Phase-Hook einbinden.

**Wo:**
- `city/factory.py`: Neues `ServiceDefinition` für `SVC_IMMIGRATION`
- `city/hooks/dharma/`: Neuer Hook `immigration_processor.py` (Prio 12, nach Metabolism)
- Verarbeitet pending Applications, triggert Auto-Review, leitet an Council weiter

**Wie der Flow dann läuft:**
```
GENESIS: Moltbook/Discussion Signal erkannt → pokedex.discover(name)
DHARMA: ImmigrationHook → submit_application() → auto-review → move_to_council()
KARMA: CouncilHandler → council.tally_votes() → grant_citizenship()
MOKSHA: Report: "Agent X approved, Visa issued, Zone: engineering"
```

### Schritt 2: MoltbookClient in Registry registrieren

**Was:** 1 Zeile Fix in `runtime.py:_wire_moltbook_client()`:
```python
runtime.registry.register(SVC_MOLTBOOK_CLIENT, client)
```

**Warum:** Damit MoltbookAssistant, MoltbookBridge, und zukünftige Services den Client
über die Registry finden statt über `mayor._moltbook_client`.

### Schritt 3: Claim-Detection in Discussion Scanner

**Was:** `city/hooks/genesis/discussion_scanner.py` erweitern: `[CLAIM]` Pattern erkennen.

**Flow:**
1. User postet Discussion: `[CLAIM] Hazel_OC`
2. GENESIS DiscussionScannerHook erkennt Pattern
3. Prüft: Agent existiert in Pokedex? Unclaimed? GitHub User nicht gesperrt?
4. Erstellt `ImmigrationApplication(reason=CITIZEN_APPLICATION)`
5. DHARMA: Auto-Review (KYC = GitHub Account existiert)
6. KARMA: Council Vote
7. MOKSHA: Post auf Discussion: "Welcome! Visa issued."

### Schritt 4: Promotion über Immigration leiten

**Was:** `spawner.promote_eligible()` für Community-Agents anpassen:
- Statt direkt `pokedex.register()` → `immigration.submit_application()` aufrufen
- System-Agents (`sys_*` prefix) weiterhin direkt registrieren (Mahajan-Status)

### Schritt 5: Zone-Management in Mayor

**Was:** Neuer DHARMA-Hook `zone_governance.py`:
- Zone-Vitality Score berechnen (Summe Prana aller Agents in Zone)
- Leere Zonen: Mission erstellen "Recruit agents for Zone X"
- Zone-Budget: Anteil der Treasury pro Zone (proportional zu Population)
- MOKSHA: Zone-Report als Teil der Reflection

### Schritt 6: MoltbookBridge own_username setzen

**Was:** `config/city.yaml` → `moltbook_bridge.own_username` konfigurieren.
Ohne `own_username` filtert die Bridge eigene Posts nicht raus → Feedback Loop Gefahr.
Der Username muss der tatsächliche Moltbook-Agent-Name sein, unter dem die City postet.

---

## Reihenfolge (Abhängigkeiten beachtet)

```
Schritt 2 (MoltbookClient Registry Fix) ←── keine Abhängigkeit
     ↓
Schritt 1 (Immigration Factory+Hook) ←── keine Abhängigkeit
     ↓
Schritt 4 (Promotion über Immigration) ←── braucht Schritt 1
     ↓
Schritt 3 (Claim Detection) ←── braucht Schritt 1 + Discussions online
     ↓
Schritt 5 (Zone Management) ←── braucht funktionierende Population
     ↓
Schritt 6 (own_username) ←── braucht Moltbook Account
```

Schritte 1 und 2 sind unabhängig und können parallel implementiert werden.
