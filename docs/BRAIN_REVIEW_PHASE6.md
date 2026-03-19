# Brain Architecture Review — Phases 1-5 Audit + Phase 6 Plan

**Author**: Cascade (Architect)  
**Date**: 2026-03-02  
**Scope**: Full audit of Brain cognition, MURALI phase god objects, kernel gaps, MahaCell opportunity

---

## 1. Brain Phases 1-5 — What's Solid

### Working correctly
- **Structured Prompt Builder** (`brain_prompt.py`): HEADER/PAYLOAD/SCHEMA versioned assembly. Clean separation.
- **Buddhi Validation Gate** (`brain.py:_buddhi_validate`): Soft penalty on HEALTH_CHECK/REFLECTION only. Dissonance flows into evidence → memory. Never silent.
- **Feedback Loop** (`genesis.py → discussions_bridge.py`): HTML comment JSON, bulletproof parsing, `record_external()` into BrainMemory. Roundtrip tested.
- **Snapshot Persistence** (`brain_context.py`): `save/load_before_snapshot()` survives ephemeral runners. One-shot cleanup after load.
- **Echo Chamber Guard**: Past thoughts explicitly framed in prompt with "do NOT repeat" instruction.
- **Tests**: 112 brain-specific tests. 1053 total passing.

### What's NOT solid (bugs/gaps found during review)

| # | Issue | Severity | Location |
|---|-------|----------|----------|
| B1 | **`to_system_context()` is DEAD CODE** | Medium | `brain_context.py:49-132` |
|    | brain.py now uses brain_prompt.py for all 4 methods. The old `to_system_context()` is never called. 132 lines of dead weight. Should be deleted. | | |
| B2 | **BrainMemory has no decay** | High | `brain_memory.py` |
|    | FIFO eviction only. No temporal weighting. Old thoughts carry same weight as fresh ones in `pattern_summary()`. A thought from heartbeat #1 and heartbeat #400 look identical to the brain. Prana = focus. Without decay, the brain has no attention. | | |
| B3 | **`record_external()` doesn't validate schema** | Low | `brain_memory.py:50-63` |
|    | Any dict is accepted. Corrupt external feedback (missing "comprehension", "intent") silently enters memory. Should at least require `comprehension` key. | | |
| B4 | **`BrainPromptHeader` is a flat dataclass, not a MahaCell** | Architectural | `brain_prompt.py` |
|    | You raised this — it should be a MahaCell (or carry a MahaHeader). The prompt itself is a message routed through the system. Header = routing metadata. Payload = data. Schema = contract. This is literally MahaHeader(72 bytes) + payload + CRC. The brain prompt IS a cell message. | | |
| B5 | **No brain prana / attention budget** | High | `brain.py` |
|    | `_MAX_BRAIN_CALLS_PER_CYCLE = 3` in karma.py is a static budget. No relationship to city prana, load, or attention. Brain should cost prana. High-confidence thoughts should cost less. Low-confidence repetitive thoughts = waste = high prana cost. This IS the decay/attention mechanism you're asking about. | | |
| B6 | **Outcome diff is only computed if before_snapshot exists** | Low | `moksha.py:254-257` |
|    | If karma didn't run (e.g. heartbeat skipped), before_snapshot doesn't exist, outcome_diff is silently None. The brain reflects without knowing what changed. Should log this gap. | | |
| B7 | **`comprehend_discussion` + `comprehend_signal` don't use memory** | Medium | `brain.py:223-370` |
|    | Only `evaluate_health` and `reflect_on_cycle` accept `memory=`. Per-agent comprehension has no historical context. Brain comprehends each discussion as if it's the first time, every time. | | |

---

## 2. MURALI Phase Files — The God Object Problem

This is the biggest architectural issue in the codebase. I traced every line.

### Line counts
| Phase | File | Lines | Concern |
|-------|------|-------|---------|
| GENESIS | `genesis.py` | 510 | Feed scan + federation directives + brain feedback + DM polling + census seeding |
| DHARMA | `dharma.py` | 351 | Metabolism + hibernation + spawner + reactor + attention + elections + stipends + contracts + issues + KG constraints |
| KARMA | `karma.py` | **1491** | Gateway queue + DMs + discussions routing + signals + cartridge routing + cognitive actions + brain health + sankalpa + heal intents + council vote + proposals + PR lifecycle + marketplace + moltbook assistant |
| MOKSHA | `moksha.py` | 798 | Chain verify + audit + reflection + PR lifecycle + spawner + builder + issues + missions + marketplace + governance + revival + rewards + brain reflection + federation + moltbook + discussions posts |

**karma.py is 1491 lines.** This is not a phase dispatcher. It's doing everything:
- Gateway queue processing (transport)
- Cognitive action execution (AI ops)
- Council governance cycle (politics)
- Heal intent execution (immune)
- Cartridge routing (agent dispatch)
- Signal processing (A2A)
- Marketplace operations (economy)
- Brain health evaluation (cognition)
- PR lifecycle (CI/CD)

### Root cause: No intermediate service layer

The MURALI phases should be **thin dispatchers** that call domain services. Instead, they contain the domain logic inline. There's no:
- `CityOperator` (processes gateway queue)
- `CognitionService` (routes cognitive actions)
- `GovernanceService` (council cycle)
- `HealService` (immune escalation pipeline)

Each phase file has become a procedural mega-function with `if ctx.X is not None:` guards everywhere (I counted **47 such guards** in karma.py alone).

### The fix: Extract domain services, phases become 50-line dispatchers

```
Phase file (thin)          Domain service (extracted logic)
─────────────────          ─────────────────────────────────
genesis.py (~50 LOC)  →    FeedScanner, FederationIngester, BrainFeedbackLoop
dharma.py  (~50 LOC)  →    MetabolismService, GovernanceService, ContractChecker
karma.py   (~50 LOC)  →    OperationsKernel, CognitionRouter, HealPipeline
moksha.py  (~50 LOC)  →    ReflectionEngine, ReportPublisher, MissionLifecycle
```

---

## 3. The Missing Kernel

### Current architecture
```
GitHub Actions cron (every 15min)
  → heartbeat.py
    → Mayor.heartbeat()
      → _build_ctx()      # rebuild PhaseContext from scratch
      → phase.execute(ctx) # one of GENESIS/DHARMA/KARMA/MOKSHA
      → _save_state()      # persist heartbeat count
```

### What's missing: a real runtime kernel

The heartbeat IS the kernel — you're right. But it's a **cold-start kernel**. Every 15 minutes:
1. GitHub Actions spawns a fresh Python process
2. Mayor rebuilds everything from disk (SQLite, JSON, config)
3. One phase runs
4. Process dies

There is no:
- **Warm state** between heartbeats (everything is cold-loaded)
- **Intra-heartbeat operations** (once the phase runs, it's done)
- **Async capability** (no event loop, no background tasks)
- **Sub-heartbeat scheduling** (can't run urgent operations between cron ticks)

### The VenuOrchestrator gap

In `mayor.py:251-256`:
```python
try:
    from vibe_core.mahamantra import mahamantra
    mahamantra.venu.step()
except Exception as e:
    logger.warning("VenuOrchestrator step failed: %s", e)
```

This is a **ceremonial call**. Venu steps but nothing reads its state. The 4+6+9 bit orchestrator (19-bit DIW) should be controlling:
- Which sub-operations run within each phase
- Priority ordering of operations
- Gate conditions (e.g., "skip marketplace if immune breaker tripped")
- Resource allocation (prana budget per phase)

Currently `heartbeat_count % 4` decides the phase. That's 2 bits. We're using 2 out of 19.

---

## 4. BrainPrompt → MahaCell Opportunity

You asked: should HEADER/PAYLOAD/SCHEMA become a MahaCell?

### Yes, and here's why

`addressing.py` already imports and uses:
- `MahaCompression` — string → deterministic seed
- `MahaHeader` — 72-byte routing header (source, target, operation)
- `MahaCellUnified` — the actual cell
- `CellRouter` — O(1) lookup

The brain prompt is **conceptually a message FROM the city TO the LLM**:
- **Source**: City kernel (mayor address)
- **Target**: Brain (LLM endpoint address)
- **Operation**: ThoughtKind (HEALTH_CHECK=1, REFLECTION=2, COMPREHENSION=3)
- **Payload**: The prompt content
- **TTL/Prana**: How much energy this brain call costs

### What MahaCell gives us that flat dataclass doesn't

1. **Decay**: MahaCell has lifecycle. A brain thought ages. Its relevance decays. `cell.is_alive` tells us if the thought is still meaningful. This IS the attention/decay mechanism you asked about.

2. **Routing**: Brain thoughts can be addressed. Agent X's comprehension → routed to Agent Y via CellRouter. Brain-to-brain communication.

3. **Prana accounting**: Each brain call = cell creation. Cell costs prana. City pays from treasury. Budget is organic, not `_MAX_BRAIN_CALLS = 3`.

4. **Memory as cell population**: BrainMemory entries become cells with addresses. Old cells die (prana exhaustion). Recent, relevant cells survive. The memory IS a mini-city.

### Migration path
```
Phase 6a: BrainCell wraps Thought + MahaHeader + prana_cost
Phase 6b: BrainMemory stores BrainCells, uses cell lifecycle for decay
Phase 6c: BrainPrompt builds from BrainCell routing metadata
Phase 6d: Brain calls deduct prana from city treasury (real cost)
```

---

## 5. The Bidirectional GitHub Discussions Problem

Current state:
- **Outbound** (city → GitHub): `discussions_bridge.py` posts brain thoughts, city reports, mission results, agent actions, pulses. Works.
- **Inbound** (GitHub → city): Only in GENESIS — scans for new comments, ingests `[Brain]` tags via hidden JSON. Limited.

### What's missing

1. **Command parsing**: Humans post in Discussions. The city should understand commands ("@agent-city revive AgentX", "@agent-city investigate contract_ruff").
2. **Threaded conversation**: Current scan is flat. Each discussion is a thread with context. The city doesn't track conversation state.
3. **Rate limiting coherence**: `discussions_bridge` has per-cycle counters but they reset each heartbeat. No global rate awareness across runs.
4. **Two-way brain**: Brain posts a thought → human replies → brain should incorporate the reply in next cycle. Currently the feedback loop only catches `[Brain]` tagged posts (self-replies). Human replies to brain posts are ignored.

---

## 6. Proposed Phase 6 — "The Extraction"

### Priority order

**6A: Kill the god objects (CRITICAL)**
- Extract `OperationsKernel` from karma.py (gateway queue + discussion routing + DM handling)
- Extract `CognitionRouter` from karma.py (cartridge routing + cognitive action execution)
- Extract `GovernanceService` from dharma.py + karma.py (elections + proposals + voting)
- Extract `HealPipeline` from karma.py (immune → executor → PR escalation)
- Extract `ReportPublisher` from moksha.py (federation + moltbook + discussions posting)
- Each phase file drops to ~50-80 lines of pure dispatch

**6B: BrainCell (the MahaCell migration)**
- `BrainCell(MahaCellUnified)` wraps Thought + routing header + prana_cost
- BrainMemory becomes a cell population with decay
- Brain calls deduct from city treasury
- `pattern_summary()` weights by cell.prana (recent = high prana = high weight)

**6C: VenuOrchestrator wiring (the real kernel)**
- Read Venu's 19-bit state to control sub-operations within phases
- Phase-level prana budgets derived from Venu state
- Gate conditions: skip expensive operations when resources low
- Metric: track prana spent per phase for self-optimization

**6D: GitHub Discussions v2 (bidirectional)**
- Command parser for human-posted instructions
- Conversation state tracking per discussion thread
- Human reply → brain feedback loop (not just self-replies)
- Global rate limiter (persisted across runs)

### Recommended execution order
```
6A first — reduces merge conflicts, makes all other work cleaner
6B second — brain becomes a first-class cell citizen
6C third — requires 6A (thin phases) to wire properly
6D fourth — requires 6B (brain understands conversations properly)
```

---

## 7. Registry Slot Opportunity

You mentioned "so viele slots vergeben für beliebige Dinge." The `CityServiceRegistry` currently has 33 named slots. It's a flat string→object dict. No typing, no lifecycle, no capacity limits.

With MahaCell integration, the registry becomes a CellRouter:
- Each service = a cell with an address
- Services have prana (health)
- Dead services get evicted
- New services can register dynamically
- Router provides O(1) lookup by address

This turns the registry from a passive bag into a living organism.

---

## Summary

| Area | Status | Action |
|------|--------|--------|
| Brain Phases 1-5 | **Solid** (7 minor/medium issues found) | Fix B1-B7 in Phase 6B |
| MURALI god objects | **CRITICAL** | Phase 6A: extract domain services |
| Missing kernel | **Structural gap** | Phase 6C: wire VenuOrchestrator |
| MahaCell for Brain | **Strong opportunity** | Phase 6B: BrainCell + decay |
| GitHub Discussions | **Half-built** | Phase 6D: bidirectional v2 |
| Registry | **Adequate for now** | Future: CellRouter migration |

**The codebase is close. The brain thinks. The heartbeat pumps. What's missing is the extraction of logic from god-object phase files into proper domain services, and the organic lifecycle (MahaCell + prana) that makes everything self-regulating instead of statically budgeted.**
