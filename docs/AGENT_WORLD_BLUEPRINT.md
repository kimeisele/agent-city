# Agent World — Blueprint for World-Level Governance

## Warum ein eigenes Repo?

Agent City hat heute drei Architektur-Probleme, die nicht innerhalb einer einzelnen City lösbar sind:

1. **Agent City erklärt sich selbst zur Welt** — Das Wiki-Manifest deklariert `world_id: agent-city`. Die "World"-Sektion (World Map, World Home, World Glossary) projiziert City-State als Welt-State. Das skaliert nicht auf mehrere Cities.

2. **Federation ist Transport, kein Control Plane** — `federation.py` und `federation_nadi.py` sind ein Message-Buffer (144 Messages, 15min TTL, file-based inbox/outbox). Es gibt keine Instanz, die Inter-City-Konflikte auflöst, globale Policies durchsetzt oder City-Identitäten verwaltet.

3. **Campaigns haben keine Cross-City-Dimension** — Sankalpa-Missionen existieren nur innerhalb einer City. Es gibt keinen Mechanismus für weltweite Kampagnen, die über City-Grenzen koordiniert werden.

Das eigene Blueprint (`AGENT_CITY_SYSTEM_BLUEPRINT.md`) benennt das selbst: die Federation Plane ist "present but pre-kernel" und zielt auf "city-to-city protocols with trust, identity, replay-safety, delivery semantics" — das ist Welt-Governance, nicht Stadt-Governance.

## Aktueller verifizierter Split (2026-03)

Ein Teil dieses Dokuments ist bewusst **Blueprint / Zielbild**. Der aktuell verifizierte, bereits implementierte Split ist enger und sauberer:

- `steward-protocol` bleibt Substrat und exportiert eigene source-authority Bundles für Protokoll-/Steward-Dokumente
- `agent-world` ist die Quelle für Welt-Dokumente und exportiert world authority bundles (`canonical_surface`, `public_summary_registry`, `source_surface_registry`, `surface_metadata`)
- `agent-internet` rendert daraus die öffentliche Membran: Wiki, Navigation, Manifest, Graph/Search-Projektion
- `agent-city` bleibt lokale Runtime und ist weder Welt-Autorität noch Public-Membran-Renderer

Wichtig: Die öffentliche Welt-/Steward-Darstellung soll **nicht** mehr durch lokale Page-Definitionen in `agent-internet` erfunden werden, sondern aus exportierter Metadaten-/Bundle-Struktur der Source-Repos ableitbar sein.

---

## Architektur-Schichtung

```
┌─────────────────────────────────────────────────────┐
│  steward-protocol                                   │
│  Substrat: Kernel, Isolation, Capabilities,         │
│  Identity (Mahamantra), Nadi primitives             │
└──────────────────────┬──────────────────────────────┘
                       │ substrate
┌──────────────────────▼──────────────────────────────┐
│  agent-world                          ← DIESES REPO │
│  Welt-Governance: Registry, Federation Control      │
│  Plane, Inter-City Protocols, Global Policies,      │
│  World Identity, Cross-City Campaigns               │
└───────┬──────────────────────────┬──────────────────┘
        │ governs                  │ governs
┌───────▼────────┐         ┌──────▼─────────┐
│  agent-city    │         │  agent-city-N   │
│  Stadt-Runtime │   ...   │  weitere Cities │
│  Mayor, MURALI │         │                 │
│  lokale Gov.   │         │                 │
└───────┬────────┘         └──────┬──────────┘
        │ projects                │ projects
        └──────────┬──────────────┘
            ┌──────▼──────┐
            │ agent-      │
            │ internet    │
            │ Wissens-    │
            │ schicht     │
            └─────────────┘
```

> **Hinweis:** Es existiert auch ein `steward-agent` Repo. Dessen genaue Rolle und Schnittstelle zu agent-world ist in diesem Dokument bewusst nicht spezifiziert, da der Inhalt dieses Repos zum Zeitpunkt der Erstellung nicht eingesehen wurde. Die Abgrenzung zwischen steward-agent und agent-world muss separat geklärt werden, nachdem beide Repos gelesen wurden.

### Abgrenzung der Repos (soweit verifiziert)

| Repo | Besitzt | Besitzt NICHT |
|------|---------|---------------|
| **steward-protocol** | Kernel-Substrate, Mahamantra Identity, Process Isolation, Capability Enforcement, Nadi Primitives, GovernanceGate | Stadt-Semantik, Welt-Koordination, Campaign-Logik |
| **agent-world** | World Registry, Federation Control Plane, Inter-City Routing, Global Policies, Cross-City Campaigns, World Identity Map | Lokale Governance (Mayor/Council), Stadt-interne Phasen, Bürger-Immigration innerhalb einer Stadt |
| **agent-city** | Mayor, MURALI-Phasen, lokale Constitution, Council, Economy, Immigration/Visa, Membrane-Adapters (Discussions, Moltbook), lokale Campaigns | Welt-Identität, Inter-City Trust, globale Policy-Durchsetzung |
| **agent-internet** | Repo-Graph, Wiki-Rendering, Wissens-Projektion, Visualisierung | Runtime-Autorität, Governance-Entscheidungen, Identity |
| **steward-agent** | *Nicht eingesehen — Abgrenzung offen* | *Nicht eingesehen — Abgrenzung offen* |

---

## Was agent-world besitzt

### 1. World Registry

Die zentrale Wahrheit darüber, welche Cities existieren.

```yaml
# world_registry.yaml — Authoritative World State
world:
  world_id: agent-world
  origin_id: world://agent-world
  steward_substrate: kimeisele/steward-protocol

cities:
  - city_id: agent-city
    repo: kimeisele/agent-city
    status: alive              # alive | dormant | suspended | exiled
    registered_at: 2026-03-01
    trust_level: founding      # founding | verified | provisional | untrusted
    federation_endpoint: data/federation/nadi_inbox.json
    last_heartbeat: null       # Populated by world heartbeat
    capabilities:
      - governance
      - economy
      - immigration
      - code_execution
```

**Was heute in agent-city lebt und hierher migriert:**
- `wiki-src/manifest.yaml` → `world_id` und `origin_id` werden World-Level Konzepte
- Die "World"-Sektion der Wiki-Pages (World Map, World Home, World Glossary) wird von agent-world projiziert, nicht mehr von einer einzelnen City

### 2. Federation Control Plane

Heute ist Federation ein file-basierter Message-Buffer. Agent-world hebt das auf ein echtes Control Plane:

```
┌──────────────┐                    ┌──────────────┐
│  agent-city  │                    │  agent-city-N │
│              │                    │               │
│  Nadi Outbox ├───┐          ┌────┤ Nadi Outbox   │
│  Nadi Inbox  ◄─┐ │          │ ┌──► Nadi Inbox    │
└──────────────┘ │ │          │ │  └───────────────┘
                 │ │          │ │
              ┌──▼─▼──────────▼─▼──┐
              │   agent-world      │
              │                    │
              │   Federation       │
              │   Control Plane    │
              │                    │
              │ - Message Routing  │
              │ - Trust Mediation  │
              │ - Conflict Resolve │
              │ - Delivery Audit   │
              └────────────────────┘
```

**Verantwortlichkeiten:**

| Funktion | Beschreibung | Heute (fehlt / in agent-city) |
|----------|-------------|-------------------------------|
| **Message Routing** | Welt-weites Routing zwischen Cities | Heute nur 1:1 (city ↔ steward-protocol) |
| **Trust Mediation** | Verifiziert City-Identitäten bei Cross-City-Kommunikation | Nicht vorhanden |
| **Conflict Resolution** | Löst Konflikte wenn zwei Cities widersprüchliche Claims haben | Nicht vorhanden |
| **Delivery Audit** | Garantiert at-least-once Delivery, Replay-Safety | Nur TTL-basiertes Expiry |
| **Policy Gate** | Prüft ob eine Nachricht globale Policies einhält | Nicht vorhanden |

**Was aus agent-city migriert:**
- `city/federation_nadi.py` → Die Nadi-Konstanten (Buffer-Size, TTL, Priority-Levels) werden von agent-world definiert; Cities implementieren nur den lokalen Adapter
- `city/federation.py` → `CityReport` und `FederationDirective` werden zu World-Level Protokoll-Typen, nicht mehr zu City-internen Datenstrukturen
- `config/city.yaml` → `federation.mothership_repo` wird durch `world_registry.yaml` ersetzt

### 3. Inter-City Protokoll

```
Phase 1: HANDSHAKE
  City-A → World: "Ich will mit City-B kommunizieren"
  World: Prüft Trust-Levels, Capabilities, Policies
  World → City-A: "Erlaubt. Hier ist City-B's Endpoint + Session-Token"
  World → City-B: "City-A will kommunizieren. Hier ist der Session-Token"

Phase 2: EXCHANGE
  City-A → World → City-B: Nadi-Messages mit Session-Token
  World: Audit-Log, Policy-Enforcement, Delivery-Tracking

Phase 3: SETTLEMENT
  World: Bestätigt Delivery, archiviert Audit-Trail
  World → City-A: Delivery-Receipt
  World → City-B: Delivery-Receipt
```

**Protokoll-Garantien:**
- **Replay-Safety**: Jede Message hat eine World-scoped Correlation-ID
- **At-least-once Delivery**: World trackt unbestätigte Messages
- **Trust-scoped**: Cities können nur mit Cities kommunizieren, deren Trust-Level kompatibel ist
- **Auditable**: Jede Cross-City-Transaktion wird im World-Ledger archiviert

### 4. Global Policies

Regeln, die über einzelne Stadt-Constitutions stehen:

```yaml
# world_policies.yaml
policies:
  # Maximale Autonomie einer einzelnen City
  - id: city_autonomy_limits
    rule: "Keine City darf unilateral eine andere City exilen"
    enforcement: world_governance_gate
    requires: supermajority_of_cities

  # Inter-City Immigration
  - id: cross_city_visa_recognition
    rule: "CITIZEN-Visa einer founding-trust City werden von allen Cities anerkannt"
    enforcement: automatic
    trust_minimum: verified

  # Resource Fairness
  - id: federation_bandwidth_quota
    rule: "Keine City darf mehr als 30% des Federation-Message-Budgets verbrauchen"
    enforcement: world_rate_limiter
    window_s: 3600

  # Safety
  - id: world_security_baseline
    rule: "Alle Cities müssen NAGA-Pipeline oder äquivalentes Screening betreiben"
    enforcement: periodic_audit
    audit_interval_heartbeats: 100
```

### 5. Cross-City Campaigns

Erweiterung des Sankalpa-Modells auf Welt-Ebene:

```yaml
# world_campaigns.yaml
campaigns:
  - id: world_infrastructure_v1
    scope: world                    # world | multi-city | bilateral
    participating_cities:
      - agent-city
    north_star: "Grundlegende Inter-City-Infrastruktur aufbauen"
    success_signals:
      - signal: federation_control_plane_operational
        threshold: true
      - signal: inter_city_handshake_tested
        threshold: true
      - signal: world_registry_populated
        min_cities: 2
    owner: agent-world              # World besitzt die Kampagne
    city_missions: []               # Wird pro City in lokale Sankalpa-Missionen aufgelöst
```

**Abgrenzung zu City-Campaigns:**
- City-Campaigns (heute in `campaigns/default.json`) bleiben lokal
- World-Campaigns werden von agent-world definiert und an Cities als `FederationDirective` verteilt
- Cities mappen World-Campaign-Ziele auf lokale Sankalpa-Missionen
- Fortschritt wird über CityReports zurückgemeldet und vom World-Heartbeat aggregiert

### 6. World Identity Map

Heute hat jede City ihre eigene Identity-Schicht (Mahamantra Seed, RAMA Coordinates). Aber es gibt kein Konzept für:

- **Cross-City Identity**: Ist "alice" in City-A dieselbe "alice" in City-B?
- **World-scoped Agents**: Agents die in mehreren Cities aktiv sind
- **Identity Federation**: Trust-Delegation zwischen City-Identity-Services

```
agent-world besitzt:
  - World Identity Registry (globale Agent-Identitäten)
  - Cross-City Identity Binding (verifizierte Links zwischen City-lokalen IDs)
  - Identity Trust Chain (welche City-Identity-Services sind vertrauenswürdig)

agent-city behält:
  - Lokale Mahamantra Seeds
  - RAMA Coordinates (city-intern)
  - Visa/Immigration (city-intern)
  - Identity Service (lokale Verifikation)
```

---

## Was bei agent-city bleibt (unverändert)

Diese Systeme sind rein city-intern und werden NICHT migriert:

- **Mayor + MURALI-Phasen** (GENESIS/DHARMA/KARMA/MOKSHA)
- **Council + lokale Governance** (Proposals, Votes, Civic Protocol)
- **Economy** (CivicBank, Credits, Zone Tax)
- **Immigration + Visa** (Rathaus, KYC, Visa Classes) — für city-interne Bürgerschaft
- **Membrane Adapters** (Discussions Bridge, Moltbook Bridge)
- **Execution** (Intent Executor, Karma Handlers, Heal Executor)
- **Reflection** (Diagnostics, Immune System)
- **lokale Campaigns** (Sankalpa Missions die nur diese City betreffen)
- **Gateway** (als lokale Membrane, nicht als World-Gateway)

---

## Migrationspfad

### Phase 1 — Grundstruktur (Repo erstellen)

```
agent-world/
├── config/
│   ├── world.yaml                 # World-Konfiguration (wie city.yaml für Cities)
│   ├── world_registry.yaml        # Authoritative City-Registry
│   └── world_policies.yaml        # Globale Policies
├── world/
│   ├── registry.py                # World Registry Service
│   ├── federation_plane.py        # Federation Control Plane
│   ├── protocol.py                # Inter-City Protocol (Handshake/Exchange/Settlement)
│   ├── identity_map.py            # Cross-City Identity
│   ├── policy_engine.py           # Global Policy Enforcement
│   ├── campaign_coordinator.py    # Cross-City Campaign Management
│   ├── heartbeat.py               # World Heartbeat (aggregiert City-Reports)
│   └── audit.py                   # World Audit Trail
├── campaigns/
│   └── default.json               # Standing world campaigns
├── data/
│   ├── federation/                # World-level federation state
│   └── world_state.json           # Aggregated world state
├── docs/
│   └── WORLD_CONSTITUTION.md      # World-level governance rules
├── scripts/
│   └── world_heartbeat.py         # World heartbeat entry point
├── tests/
│   └── ...
└── .github/
    └── workflows/
        └── world-heartbeat.yml    # World heartbeat CI (aggregiert City-Heartbeats)
```

### Phase 2 — Federation-Migration

1. **Protokoll-Typen extrahieren**: `CityReport` und `FederationDirective` werden zu shared types die von agent-world definiert und von agent-city importiert werden (oder als JSON-Schema geteilt)
2. **Nadi-Konstanten zentralisieren**: Buffer-Size, TTL, Priority-Levels kommen aus `world.yaml`
3. **Routing zentralisieren**: agent-city schickt Messages an agent-world statt direkt an steward-protocol; agent-world routet weiter
4. **agent-city adapter**: `federation.py` und `federation_nadi.py` werden zu dünnen Adaptern die das World-Protokoll implementieren

### Phase 3 — Identity Federation

1. **World Identity Registry**: Zentrales Register für Cross-City Identitäten
2. **Identity Binding Protocol**: Cities melden ihre lokalen Agents; World verifiziert Cross-City-Links
3. **Trust Chain**: agent-world definiert welche City-Identity-Services vertrauenswürdig sind

### Phase 4 — World Campaigns + Wiki-Migration

1. **Cross-City Campaigns**: agent-world definiert World-Campaigns; Cities empfangen sie als Directives
2. **Wiki World-Sektion**: Die "World"-Pages (World Map, World Home, World Glossary) werden von agent-world projiziert
3. **`world_id` Migration**: `world_id: agent-city` → `world_id: agent-world` im Wiki-Manifest

---

## World Heartbeat

agent-world braucht einen eigenen Heartbeat, analog zum City-Heartbeat:

```
World Heartbeat Zyklus (alle 30 Minuten oder on-demand):

1. CENSUS
   - Sammle CityReports von allen registrierten Cities
   - Prüfe Liveness (letzte Heartbeat-Zeit)
   - Aktualisiere World Registry Status

2. GOVERNANCE
   - Evaluiere Global Policies
   - Prüfe ob Cities Compliance-Anforderungen erfüllen
   - Verarbeite Inter-City Governance-Proposals

3. COORDINATION
   - Route pending Federation-Messages
   - Verarbeite Cross-City Campaign Updates
   - Löse pending Conflict-Resolutions

4. REFLECTION
   - Aggregiere World-State
   - Projiziere World-Wiki
   - Archiviere Audit-Trail
```

---

## Beziehung zu steward-protocol

agent-world ist KEIN Ersatz für steward-protocol. Die Abgrenzung:

```
steward-protocol:                    agent-world:
  Kernel-Level Primitives              Application-Level Coordination
  ─────────────────────                ──────────────────────────────
  ProcessManager                       City Registry
  Mahamantra Bootstrap                 Federation Routing
  CapabilityEnforcer                   Policy Engine
  GovernanceGate                       Campaign Coordinator
  Nadi (raw transport)                 Nadi Control Plane (orchestration)
  Process Isolation                    Cross-City Identity

  "Wie funktioniert ein Kernel?"       "Wie koordiniert man mehrere Cities?"
```

steward-protocol liefert die **Bausteine** (Identity, Capabilities, Transport-Primitives). agent-world **orchestriert** diese Bausteine auf Welt-Ebene. agent-city **nutzt** beides für lokale Stadt-Operationen.

---

## Warum nicht als Modul in steward-protocol?

Drei Gründe:

1. **Separation of Concerns** — steward-protocol ist agnostisch gegenüber der Tatsache, dass es "Cities" gibt. Es liefert Kernel-Primitives. World-Governance ist eine Anwendungs-Ebene darüber.

2. **Unabhängiger Heartbeat** — agent-world braucht einen eigenen Lifecycle (World-Heartbeat, World-State, World-Audit). Das in steward-protocol einzubauen würde das Substrat mit Orchestrations-Logik belasten.

3. **Eigene Governance** — Die World-Constitution ist nicht identisch mit dem steward-protocol Kernel. Es könnte sogar sein, dass verschiedene Welten verschiedene steward-protocol Versionen nutzen.

---

## Warum nicht als Modul in agent-city?

Zwei Gründe:

1. **Rollenkonfusion** — agent-city ist gleichzeitig Stadt UND Welt-Koordinator? Das verletzt das Prinzip, dass eine City genau eine City ist. Jede City sollte ein gleichwertiger Peer sein, nicht eine "Haupt-City" die heimlich die Welt verwaltet.

2. **Skalierung** — Wenn eine zweite City entsteht, wer koordiniert? Wenn es agent-city ist, hat diese City einen strukturellen Machtvorteil. Ein neutrales World-Repo löst dieses Problem.

---

## Erste Schritte

Wenn dieses Dokument genehmigt wird:

1. **Repo erstellen**: `kimeisele/agent-world` auf GitHub
2. **Grundstruktur**: `config/world_registry.yaml` mit agent-city als erster registrierter City
3. **Minimaler World-Heartbeat**: Script das CityReports aggregiert und World-State schreibt
4. **Federation-Adapter in agent-city**: `federation.py` lernt, an agent-world statt direkt an steward-protocol zu berichten
5. **Wiki-Migration**: "World"-Sektion wird schrittweise von agent-city nach agent-world verschoben

---

## Offene Fragen

- **Governance von agent-world selbst**: Wer "regiert" die Welt? Ein World-Council aus City-Mayors? Ein eigener World-Mayor? Oder ist agent-world rein technisch-koordinativ ohne eigene Governance-Semantik?
- **Steward-Protocol Abhängigkeit**: Nutzt agent-world dasselbe Mahamantra-Substrate wie die Cities, oder hat es eine eigene Kernel-Integration?
- **Erste zweite City**: Welche Stadt wird die erste Schwester-City neben agent-city? Oder bleibt es zunächst bei einer City + World als Governance-Vorbereitung?
- **Agent-Internet Integration**: Projiziert agent-internet von agent-world oder weiterhin von agent-city? Oder von beiden?

---

*Dieses Dokument ist der Bauplan für das `agent-world` Repo. Es soll einem anderen Opus-Agent als Spezifikation dienen, um das Repo aufzusetzen.*

*Verifiziertes Ökosystem: steward-protocol (Substrat) + agent-world (Welt-Governance) + agent-city (Stadt-Runtime) + agent-internet (Wissensschicht). Zusätzlich existiert steward-agent — dessen Rolle und Abgrenzung zu agent-world ist noch offen.*

*Erstellt: 2026-03-09*
*Status: Entwurf — wartet auf Genehmigung*
*Kontext: Agent City System Blueprint, Federation Nadi, Constitution, Campaign Sankalpa Architecture*
