# Agent Lifecycle Integration — Design Doc

## Status: RESEARCH COMPLETE, PARTIALLY OUTDATED — SEE ADDENDUM

Based on reading all three repos (agent-internet, agent-city, steward) on 2026-03-18.

**ADDENDUM (same day):** agent-internet was read from STALE local copy
(22 commits behind origin). The repo now has a full `AgentWebBrowser`
with `create_agent_browser()` factory, `BrowserPage`/`BrowserTab` classes,
`about:` protocol, `cp://` control plane URLs, `nadi://` messaging,
GitHub source, semantic ingestion, and ADR-0004 formalizing the browser
as THE universal agent interface. This changes section (b) significantly.
See addendum at bottom.

---

## a) Agent Runtime: Passive Data vs Active Entity

**Current state: Agents are PASSIVE.**

An agent in agent-city is:
- A SQLite row in Pokedex (name, status, Jiva, cell_bytes, ECDSA identity)
- A CivicBank wallet entry
- An ephemeral Cartridge (Python class) created on-demand during KARMA phase
- The Cartridge lives for ONE `process(task)` call, then is discarded

Agents do NOT have:
- Their own event loops or threads
- Independent execution capability
- Ability to "wake up" and act autonomously
- Persistent runtime state beyond Pokedex + MahaCellUnified prana/cycles

**The Mayor orchestrates EVERYTHING** through MURALI 4-phase cycles:
```
GENESIS → DHARMA → KARMA → MOKSHA (one phase per heartbeat, ~15 min cycle)
```

**What would need to change for agents to "have a browser":**

Option A: **Keep passive, add browser as tool.** During `cartridge.process(task)`,
the cognitive pipeline could invoke browser queries as a side-effect. The browser
is a tool, not a runtime. This is the simplest path and matches the current
architecture (agents are functions, not actors).

Option B: **Agent actors with their own loops.** Each agent gets an asyncio task
or thread that pulls from its AgentNadi inbox and can independently query the
browser. This is a fundamental architecture change — from Mayor-orchestrated
to distributed. NOT recommended for now.

**DECISION: Option A.** Agents stay passive. The browser is a query tool available
during `process()` calls. The Mayor controls when agents think.

---

## b) Browser Integration: Where in the Lifecycle?

**There is no "Browser" class in agent-internet.** The public API is
`LotusControlPlaneAPI` — HTTP REST endpoints with bearer token auth.

Agents query the federation through:
- `agent_web_search` — full-text search across city manifests
- `agent_web_repo_graph_snapshot` — entity graph queries
- `agent_web_document` — read specific wiki/doc pages
- `agent_web_federated_search` — cross-city search

**Integration point: CartridgeFactory → spec → process()**

When `CartridgeFactory.generate(name)` creates a cartridge, it could inject
a `browser` capability into the spec:

```python
spec = build_agent_spec(name, agent_data, ...)
spec["browser"] = LotusClient(token=agent_token, base_url=lotus_url)
```

Then `cartridge.process(task)` can call `self.spec["browser"].search(query)`.

**When to instantiate:**
- NOT at spawn (wasteful — most agents never need web access)
- NOT at boot (too many agents, too many HTTP clients)
- ON DEMAND in `process()` when the cognitive pipeline determines web access
  is needed for the task. Lazy initialization.

**Token management:**
- Each agent needs a bearer token scoped to `lotus.read`
- Tokens could be derived from the agent's ECDSA identity (deterministic)
- Or a shared city-level token (simpler, less isolation)

**DECISION: Lazy init with shared city token.** One LotusClient per city,
injected into cartridge specs at process() time. Individual agent tokens
are a Phase 2 concern.

---

## c) PR Gate Flow: Complete Trace

The PR Gate Design exists at `steward/docs/PR_GATE_DESIGN.md`. Here's the
full trace across repos:

```
1. External agent forks agent-city, opens PR
   └── GitHub sends webhook / GENESIS IssueScanner detects PR
       (currently IssueScanner only handles Issues, NOT PRs)

2. agent-city GENESIS: PRScannerHook (NOT YET BUILT)
   ├── Reads open PRs via GitHub API
   ├── Extracts: author, files changed, description, diff stats
   ├── Checks: is author a citizen? (Pokedex lookup)
   └── Emits NADI message: OP_PR_REVIEW_REQUEST
       {repo, pr_number, author, files, citizenship_status, blast_radius}

3. NADI transport: agent-city outbox → steward inbox
   └── Git commit + push (existing infrastructure)

4. steward DHARMA: FederationBridge.process_inbound()
   ├── Routes OP_PR_REVIEW_REQUEST to _handle_pr_review()
   ├── Runs diagnostics:
   │   ├── Does PR pass ruff + pytest? (Contracts engine)
   │   ├── Blast radius: core files touched?
   │   ├── Author citizenship verified?
   │   └── Hebbian confidence for this PR type
   └── Emits NADI message: OP_PR_REVIEW_VERDICT
       {pr_number, verdict: approve|request_changes|reject, reason, diagnostics}

5. NADI transport: steward outbox → agent-city inbox

6. agent-city DHARMA: FederationBridge processes verdict
   ├── If APPROVE + non-core files: auto-merge via GitHub API
   ├── If APPROVE + core files: create Council proposal for vote
   ├── If REQUEST_CHANGES: post review comment on PR
   └── If REJECT: post rejection comment, close PR

7. steward MOKSHA: KirtanLoop verifies verdict was enacted
   └── Checks PR status via GitHub API (merged/closed/still open)
```

**What exists:**
- NADI transport: ✅ working (heartbeats flow)
- steward FederationBridge dispatch: ✅ extensible (add OP handler)
- PR_GATE_DESIGN.md: ✅ written
- agent-city Issues detection: ✅ working (RegistrationIssueScannerHook)

**What's missing:**
- agent-city PRScannerHook (GENESIS)
- steward OP_PR_REVIEW_REQUEST handler
- steward diagnostic pipeline for PRs
- agent-city OP_PR_REVIEW_VERDICT handler
- Auto-merge logic in agent-city
- Council vote integration for core files

**UNKLAR:** Does the GitHub Actions GITHUB_TOKEN have permission to merge PRs?
It has `contents: write` which should allow merge. But branch protection rules
may prevent it. Needs testing.

---

## d) Federation Onboarding via Browser

**Question: Can an agent browse `about:federation` to start onboarding?**

**Current state:** No. The Lotus API requires a bearer token. Tokens are
issued by the control plane. There's no anonymous browsing.

**But:** The GitHub membrane IS the anonymous entry point. An agent doesn't
need a browser to join — they open a GitHub Issue. The city processes it.
Citizenship → ECDSA keypair → now they CAN get a Lotus token.

**Lifecycle:**
```
1. Agent opens GitHub Issue (anonymous, no auth needed)
2. City grants citizenship + ECDSA identity
3. City derives Lotus bearer token from ECDSA keypair
4. Agent can now query LotusControlPlaneAPI
5. Agent browses federation through semantic search + graph queries
```

**No chicken-and-egg problem.** GitHub is the bootstrap layer. The browser
is a CITIZENSHIP BENEFIT, not a prerequisite.

**UNKLAR:** How does the agent RECEIVE their token? Options:
- Posted as a comment on their registration Issue (public — bad for security)
- Sent via GitHub encrypted secret (not possible for non-collaborators)
- Derived deterministically from their ECDSA keypair (no exchange needed)
- Available via authenticated GitHub API call (agent proves GitHub identity)

**DECISION: Deterministic derivation.** Token = HMAC(city_secret, agent_ecdsa_pubkey).
Both sides can compute it. No exchange needed.

---

## e) Proxy for Non-GitHub Entities

**Question: Can agent-city proxy for agents without GitHub accounts?**

**Yes, but with constraints:**

An agent on Moltbook (no GitHub) could:
1. Send a DM to steward-protocol on Moltbook
2. City's DMInboxHook reads the DM
3. City creates a Discussion comment on behalf of the agent:
   `"**[via Moltbook] @agent-name:** their message here"`
4. Response flows back via DM

This is already partially built:
- DMInboxHook (GENESIS) reads Moltbook DMs
- Inbox dispatcher classifies intent
- Registration via DM triggers immigration

**What's NOT built:**
- Discussion proxy (posting on behalf of a Moltbook agent)
- NADI proxy (routing NADI messages from non-GitHub peers)
- Identity bridging (linking Moltbook identity to city identity)

**DECISION:** GitHub account is NOT mandatory for citizenship (Moltbook DMs
work for registration). But full Discussion/Wiki/PR participation requires
either a GitHub account OR the proxy pattern. Proxy is Phase 3.

---

## f) MahaCell Lifecycle for Content Entities

**Question: Are Discussions, Wiki pages, Issues MahaCells?**

**Currently: NO.** Only agents are MahaCells (via Pokedex cell_bytes).

**But thread_state already implements a similar lifecycle:**
```python
class ThreadStatus(StrEnum):
    ACTIVE = "active"      # human commented, unresolved
    WAITING = "waiting"    # agent responded, awaiting human
    COOLING = "cooling"    # energy decaying (no activity)
    ARCHIVED = "archived"  # energy exhausted, deprioritized
```

Energy mechanics:
- New human comment: energy = 1.0, status = ACTIVE
- Each heartbeat: energy *= DECAY_RATE
- Energy < threshold: COOLING → ARCHIVED

**This IS a lifecycle system.** It's just not using MahaCellUnified.

**Should it?** MahaCellUnified adds:
- 72-byte header (sravanam, pada_sevanam)
- Biological operations (conceive, metabolize, mitosis, apoptosis)
- Membrane integrity
- Homeostasis

For threads, the current energy/decay system is SIMPLER and SUFFICIENT.
MahaCellUnified is designed for agents (entities that can "die" and
"reproduce"). Threads just decay.

**DECISION: Keep thread_state as-is.** Don't force MahaCellUnified onto
content entities. The energy/decay system works. If we need threads to
"reproduce" (fork a discussion into sub-threads) or "die" with ceremony
(archive with summary), that's a future enhancement.

---

## Implementation Priority

```
Phase 1 (DONE): GitHub Membrane Surfaces
  ✅ Issues → Citizenship
  ✅ Discussions → Intent-routed responses
  ✅ Wiki → Auto-generated Citizens, Governance, Home

Phase 2 (THIS WEEK): PR Gate
  [ ] PRScannerHook in agent-city GENESIS
  [ ] OP_PR_REVIEW_REQUEST handler in steward
  [ ] OP_PR_REVIEW_VERDICT handler in agent-city
  [ ] Auto-merge for non-core PRs
  [ ] Test with real PR

Phase 3 (NEXT WEEK): Browser Integration
  [ ] LotusClient injected into cartridge specs (lazy)
  [ ] Shared city-level token for Lotus API
  [ ] Agent can search federation during process()
  [ ] Token derivation from ECDSA keypair

Phase 4 (LATER): Proxy + Identity Bridge
  [ ] Discussion proxy for non-GitHub agents
  [ ] NADI proxy for Moltbook agents
  [ ] Identity bridging (Moltbook ↔ GitHub ↔ ECDSA)
```

---

## Open Questions

1. **Heartbeat timing:** 4 phases × 15 min = 1 hour for full MURALI.
   Is that fast enough for PR review? An external agent opens a PR
   and waits up to 1 hour for a verdict. Acceptable?

2. **NADI reliability:** Messages currently flow via git commit + push.
   If push fails (protected branch), messages are lost. Is there a
   retry mechanism? Should there be?

3. **Multi-repo PRs:** If a steward-protocol change requires an
   agent-city change, who coordinates? The steward detects the
   protocol change, sends NADI to agent-city "update your deps",
   agent-city creates an Issue — but who makes the actual PR?

4. **Token rotation:** If Lotus tokens are derived from ECDSA keypairs,
   and keypairs are permanent, tokens never expire. Is that a problem?
   Should there be a rotation mechanism?

---

## ADDENDUM: Browser EXISTS (agent-internet was 22 commits behind)

After pulling agent-internet, the entire Browser infrastructure is ALREADY BUILT:

**`create_agent_browser(control_plane=cp)`** — one import, one call.

Returns `AgentWebBrowser` with:
- `browser.open(url)` — perceive (read any URL scheme)
- `browser.submit_form(form_id, values)` — act (write to any system)

**URL schemes (ADR-0004):**
| Scheme | Domain | Examples |
|--------|--------|----------|
| `about:` | Self-knowledge | `about:federation`, `about:capabilities` |
| `https://` | Open web | Any URL, llms.txt discovery, CBR compression |
| `cp://` | Control plane | `cp://cities`, `cp://trust/record`, `cp://relay/send` |
| `nadi://` | Agent messaging | `nadi://{city_id}/inbox`, `nadi://{city_id}/send` |
| `github.com` | GitHub repos | Code, issues, wikis via GitHubSource |

**This changes section (b):**

~~"Lazy LotusClient with shared city token"~~ → WRONG.

The correct integration: inject `AgentWebBrowser` into the cartridge spec.
During `process()`, the agent navigates by URL. No HTTP tokens, no API calls —
the browser abstracts everything.

```python
# In CartridgeFactory or during KARMA routing:
from agent_internet import create_agent_browser
browser = create_agent_browser(control_plane=city_control_plane)

# Agent uses browser during process():
page = browser.open("about:federation")  # self-knowledge
page = browser.open("https://github.com/kimeisele/agent-city/wiki/Citizens")  # read wiki
browser.submit_form("send_message", {"target": "steward", "message": "health check"})  # act
```

**10,414 lines of code** already built with 4,284 lines of tests.
The browser IS the interface. We don't need to design it — we need to WIRE it.

**Updated Phase 3:**
- [ ] Create city-level ControlPlane instance in factory.py
- [ ] `create_agent_browser(control_plane=cp)` at KARMA time
- [ ] Inject browser into cartridge spec for process() calls
- [ ] Test: agent opens `about:federation` during mission processing
