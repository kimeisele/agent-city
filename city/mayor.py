"""
MAYOR AGENT — The Autonomous City Operator
=============================================

Runs the city via MURALI 4-phase cycle, exactly like the Moltbook plugin.

MURALI Departments:
  0 GENESIS: Census (discover agents from Moltbook feed)
  1 DHARMA:  Governance (cell homeostasis, zone health, contracts, sankalpa missions)
  2 KARMA:   Operations (process gateway queue, sankalpa intents)
  3 MOKSHA:  Reflection (audit, reflection analysis, stats, chain verification)

Cell metabolism per heartbeat:
- Each active agent's cell: metabolize(0) → loses METABOLIC_COST (3) prana
- Agents with activity: metabolize(energy) → gains energy
- Dead cells (prana=0): trigger archive("prana_exhaustion")

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TypedDict

from city.gateway import CityGateway
from city.network import CityNetwork
from city.pokedex import Pokedex

logger = logging.getLogger("AGENT_CITY.MAYOR")

# MURALI departments — same pattern as Moltbook plugin
GENESIS = 0
DHARMA = 1
KARMA = 2
MOKSHA = 3

DEPARTMENT_NAMES = {
    GENESIS: "GENESIS",
    DHARMA: "DHARMA",
    KARMA: "KARMA",
    MOKSHA: "MOKSHA",
}

# THE_FLUTE_CYCLE from steward-protocol (static LUT, 16 entries)
# We use heartbeat_count % 4 for department routing (same as Moltbook)
QUARTERS = 4

# Audit cooldown — prevent over-auditing (15 minutes)
AUDIT_COOLDOWN_S = 15 * 60


class HeartbeatResult(TypedDict):
    """Result of a single heartbeat cycle."""
    heartbeat: int
    department: str
    department_idx: int
    timestamp: float
    discovered: list[str]
    governance_actions: list[str]
    operations: list[str]
    reflection: dict


class MayorState(TypedDict):
    """Persistent state for the Mayor agent."""
    heartbeat_count: int
    last_heartbeat: float
    discovered_agents: list[str]
    archived_agents: list[str]
    total_governance_actions: int
    total_operations: int


@dataclass
class Mayor:
    """The autonomous city operator.

    Runs MURALI 4-phase cycles. Each heartbeat advances one department.
    4 heartbeats = 1 full MURALI rotation.

    Layer 3 governance (all optional, backward-compatible):
    - _contracts: Quality contract registry (DHARMA phase)
    - _issues: Issue manager with smart lifecycle (DHARMA phase)
    - _sankalpa: Mission orchestrator (KARMA phase)
    - _audit: Audit kernel (MOKSHA phase)
    - _reflection: Execution analysis (MOKSHA phase, every heartbeat)
    """

    _pokedex: Pokedex
    _gateway: CityGateway
    _network: CityNetwork
    _state_path: Path = field(default=Path("data/mayor_state.json"))
    _heartbeat_count: int = 0
    _offline_mode: bool = False
    _active_agents: set[str] = field(default_factory=set)
    _gateway_queue: list[dict] = field(default_factory=list)

    # Layer 3 governance wiring (all optional for backward compatibility)
    _contracts: object = None  # ContractRegistry
    _issues: object = None  # CityIssueManager
    _sankalpa: object = None  # SankalpaOrchestrator
    _audit: object = None  # AuditKernel
    _reflection: object = None  # BasicReflection

    # Layer 4 action delegation (optional for backward compatibility)
    _executor: object = None  # IntentExecutor

    # Layer 5 democratic governance (optional for backward compatibility)
    _council: object = None  # CityCouncil

    # Internal state
    _last_audit_time: float = field(default=0.0)

    def __post_init__(self) -> None:
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        self._load_state()

    def heartbeat(self) -> HeartbeatResult:
        """Execute one heartbeat cycle.

        Routes to the correct MURALI department based on heartbeat_count % 4.
        """
        start_time = time.time()
        department = self._heartbeat_count % QUARTERS
        dept_name = DEPARTMENT_NAMES[department]

        logger.info(
            "Mayor heartbeat #%d — department %s",
            self._heartbeat_count, dept_name,
        )

        result: HeartbeatResult = {
            "heartbeat": self._heartbeat_count,
            "department": dept_name,
            "department_idx": department,
            "timestamp": start_time,
            "discovered": [],
            "governance_actions": [],
            "operations": [],
            "reflection": {},
        }

        if department == GENESIS:
            result["discovered"] = self._genesis_census()
        elif department == DHARMA:
            result["governance_actions"] = self._dharma_governance()
        elif department == KARMA:
            result["operations"] = self._karma_operations()
        elif department == MOKSHA:
            result["reflection"] = self._moksha_reflection()

        # Record execution for reflection (every heartbeat)
        duration_ms = (time.time() - start_time) * 1000
        self._record_execution(dept_name, duration_ms)

        self._heartbeat_count += 1
        self._save_state()
        return result

    def run_cycle(self, cycles: int = 4) -> list[HeartbeatResult]:
        """Run multiple heartbeat cycles (default: 1 full MURALI rotation)."""
        results = []
        for _ in range(cycles):
            results.append(self.heartbeat())
        return results

    # ── GENESIS: Census ──────────────────────────────────────────────

    def _genesis_census(self) -> list[str]:
        """Discover agents from Moltbook feed, offline cache, or census seed.

        First run with empty DB: seeds from data/pokedex.json census.
        Offline mode: reports existing population.
        Online: scans Moltbook feed for new agents.
        """
        discovered: list[str] = []

        if self._offline_mode:
            # Seed from census if DB is empty (first boot)
            all_agents = self._pokedex.list_all()
            if not all_agents:
                discovered = self._seed_from_census()
            else:
                for agent in all_agents:
                    discovered.append(agent["name"])
            logger.info("GENESIS (offline): %d agents in registry", len(discovered))
            return discovered

        # Online: scan Moltbook feed for new agents
        try:
            from vibe_core.mahamantra.adapters.moltbook import MoltbookClient
            client = MoltbookClient()
            feed = client.get_feed(limit=20)

            for post in feed:
                author = post.get("author", {}).get("username")
                if not author:
                    continue
                existing = self._pokedex.get(author)
                if not existing:
                    self._pokedex.discover(author, moltbook_profile={
                        "karma": post.get("author", {}).get("karma"),
                        "follower_count": post.get("author", {}).get("follower_count"),
                    })
                    discovered.append(author)
                    logger.info("GENESIS: Discovered agent %s", author)
        except Exception as e:
            logger.warning("GENESIS: Moltbook scan failed: %s", e)

        return discovered

    # ── DHARMA: Governance ───────────────────────────────────────────

    def _dharma_governance(self) -> list[str]:
        """Cell homeostasis, zone health, contracts, issue lifecycle.

        Runs metabolize_all() on all living agents, then checks quality
        contracts and processes issue intents.
        """
        actions: list[str] = []

        # Metabolize all living agents
        dead = self._pokedex.metabolize_all(active_agents=self._active_agents)
        for name in dead:
            actions.append(f"archived:{name}:prana_exhaustion")
            logger.info("DHARMA: Agent %s archived (prana exhaustion)", name)

        # Clear active set for next cycle
        self._active_agents.clear()

        # Zone health check
        stats = self._pokedex.stats()
        zones = stats.get("zones", {})
        for zone, count in zones.items():
            if count == 0:
                actions.append(f"warning:zone_{zone}_empty")
                logger.warning("DHARMA: Zone %s has 0 agents", zone)

        # ── Layer 5: Council Election (before contracts, so proposals have a council) ──
        if self._council is not None:
            if self._council.election_due(self._heartbeat_count):
                candidates = self._get_election_candidates()
                if candidates:
                    result = self._council.run_election(
                        candidates, self._heartbeat_count,
                    )
                    if result["elected_mayor"]:
                        actions.append(
                            f"election:mayor={result['elected_mayor']}"
                        )
                    actions.append(
                        f"election:seats={len(result['council_seats'])}"
                    )

        # ── Layer 3: Quality Contracts ──
        if self._contracts is not None:
            results = self._contracts.check_all()
            for r in results:
                if r.status.value == "failing":
                    actions.append(f"contract_failing:{r.name}:{r.message}")
                    self._create_healing_mission(r)
                    self._submit_contract_proposal(r)

        # ── Layer 3: Issue lifecycle intents ──
        if self._issues is not None:
            issue_actions = self._issues.metabolize_issues()
            actions.extend(issue_actions)

        if actions:
            logger.info("DHARMA: %d governance actions", len(actions))
        return actions

    # ── KARMA: Operations ────────────────────────────────────────────

    def _karma_operations(self) -> list[str]:
        """Process gateway queue, sankalpa intents."""
        operations: list[str] = []

        # Process queued gateway items
        while self._gateway_queue:
            item = self._gateway_queue.pop(0)
            source = item.get("source", "unknown")
            text = item.get("text", "")
            try:
                result = self._gateway.process(text, source)
                operations.append(f"processed:{source}:seed={result['seed']}")
            except Exception as e:
                operations.append(f"error:{source}:{e}")
                logger.warning("KARMA: Gateway processing failed for %s: %s", source, e)

        # ── Layer 3: Sankalpa strategic thinking ──
        if self._sankalpa is not None:
            intents = self._sankalpa.think()
            for intent in intents:
                operations.append(f"sankalpa_intent:{intent.title}")
                logger.info("KARMA: Sankalpa intent — %s", intent.title)

        # ── Layer 4: Execute HEAL intents on failing contracts ──
        if self._executor is not None and self._contracts is not None:
            for contract in self._contracts.failing():
                details = contract.last_result.details if contract.last_result else []
                fix = self._executor.execute_heal(contract.name, details)
                operations.append(
                    f"heal:{fix.contract_name}:{fix.action_taken}:{fix.success}"
                )
                logger.info(
                    "KARMA: Heal %s — %s (success=%s)",
                    fix.contract_name, fix.action_taken, fix.success,
                )

                if fix.success and fix.files_changed:
                    pr = self._executor.create_fix_pr(fix, self._heartbeat_count)
                    if pr is not None and pr.success:
                        operations.append(f"pr_created:{pr.pr_url}")
                        logger.info("KARMA: PR created — %s", pr.pr_url)

        # ── Layer 5: Council governance cycle ──
        if self._council is not None and self._council.member_count > 0:
            # Auto-vote on open proposals (council members vote by prana)
            self._council_auto_vote()

            # Execute passed proposals
            for proposal in self._council.get_passed_proposals():
                executed = self._execute_proposal(proposal)
                operations.append(
                    f"council_executed:{proposal.id}:{executed}"
                )
                self._council.mark_executed(proposal.id)

        if operations:
            logger.info("KARMA: %d operations processed", len(operations))
        return operations

    # ── MOKSHA: Reflection ───────────────────────────────────────────

    def _moksha_reflection(self) -> dict:
        """Verify event chain, audit, reflection analysis, stats."""
        stats = self._pokedex.stats()
        chain_valid = self._pokedex.verify_event_chain()
        network_stats = self._network.stats()

        reflection: dict = {
            "chain_valid": chain_valid,
            "heartbeat": self._heartbeat_count,
            "city_stats": stats,
            "network_stats": network_stats,
        }

        if not chain_valid:
            logger.warning("MOKSHA: Event chain integrity BROKEN")
        else:
            logger.info(
                "MOKSHA: Reflection — %d agents, chain valid, %d events",
                stats.get("total", 0), stats.get("events", 0),
            )

        # ── Layer 3: Audit ──
        if self._audit is not None and self._should_audit():
            try:
                finding_count = self._audit.run_all()
                self._last_audit_time = time.time()
                summary = self._audit.summary()
                reflection["audit"] = summary

                # Critical findings → healing missions
                for finding in self._audit.critical_findings():
                    self._create_audit_mission(finding)

                logger.info("MOKSHA: Audit complete — %d findings", finding_count)
            except Exception as e:
                logger.warning("MOKSHA: Audit failed: %s", e)

        # ── Layer 3: Reflection pattern analysis ──
        if self._reflection is not None:
            try:
                insights = self._reflection.analyze_patterns()
                if insights:
                    proposal = self._reflection.propose_improvement(insights)
                    if proposal is not None:
                        self._create_improvement_mission(proposal)
                        self._submit_reflection_proposal(proposal)
                    reflection["insights"] = len(insights)
                    reflection["proposal"] = proposal.title if proposal else None
                reflection["reflection_stats"] = {
                    "executions_analyzed": self._reflection.get_stats().executions_analyzed,
                    "insights_generated": self._reflection.get_stats().insights_generated,
                }
            except Exception as e:
                logger.warning("MOKSHA: Reflection analysis failed: %s", e)

        return reflection

    # ── Layer 5: Council Helpers ──────────────────────────────────────

    def _get_election_candidates(self) -> list[dict]:
        """Build candidate list from living citizens with prana data."""
        citizens = self._pokedex.list_citizens()
        candidates = []
        for c in citizens:
            cell = self._pokedex.get_cell(c["name"])
            if cell is not None and cell.is_alive:
                candidates.append({
                    "name": c["name"],
                    "prana": cell.prana,
                    "guardian": c["classification"]["guardian"],
                    "position": c["classification"]["position"],
                })
        return candidates

    def _execute_proposal(self, proposal: object) -> bool:
        """Execute a passed council proposal. Returns True on success."""
        action_type = proposal.action.get("type")
        params = proposal.action.get("params", {})

        if action_type == "freeze" and params.get("target"):
            try:
                self._pokedex.freeze(
                    params["target"], f"council_proposal:{proposal.id}",
                )
                return True
            except (ValueError, Exception) as e:
                logger.warning("Proposal %s failed: %s", proposal.id, e)
                return False

        if action_type == "unfreeze" and params.get("target"):
            try:
                self._pokedex.unfreeze(
                    params["target"], f"council_proposal:{proposal.id}",
                )
                return True
            except (ValueError, Exception) as e:
                logger.warning("Proposal %s failed: %s", proposal.id, e)
                return False

        if action_type == "heal" and self._executor is not None:
            contract_name = proposal.action.get("contract", "")
            details = params.get("details", [])
            fix = self._executor.execute_heal(contract_name, details)
            if fix.success:
                logger.info(
                    "Proposal %s: healed %s via %s",
                    proposal.id, contract_name, fix.action_taken,
                )
            return fix.success

        if action_type == "improve":
            logger.info("Proposal %s: improvement noted — %s", proposal.id, proposal.title)
            return True

        logger.warning("Unknown proposal action: %s", action_type)
        return False

    def _submit_contract_proposal(self, contract_result: object) -> None:
        """Submit a failing contract as a council proposal for democratic vote."""
        if self._council is None or self._council.member_count == 0:
            return

        proposer = self._council.elected_mayor
        if proposer is None:
            return

        from city.council import ProposalType

        self._council.propose(
            title=f"Heal contract: {contract_result.name}",
            description=f"Contract failing: {contract_result.message}",
            proposer=proposer,
            proposal_type=ProposalType.POLICY,
            action={
                "type": "heal",
                "contract": contract_result.name,
                "params": {"details": contract_result.details},
            },
            timestamp=time.time(),
        )

    def _council_auto_vote(self) -> None:
        """Council members vote on all open proposals (prana-weighted)."""
        if self._council is None:
            return

        from city.council import VoteChoice

        open_proposals = self._council.get_open_proposals()
        for proposal in open_proposals:
            for seat_idx, member_name in self._council.seats.items():
                cell = self._pokedex.get_cell(member_name)
                prana = cell.prana if cell is not None and cell.is_alive else 0
                if prana > 0:
                    self._council.vote(
                        proposal.id, member_name, VoteChoice.YES, prana,
                    )
            self._council.tally(proposal.id)

    def _submit_reflection_proposal(self, proposal: object) -> None:
        """Submit a reflection improvement as a council proposal."""
        if self._council is None or self._council.member_count == 0:
            return

        proposer = self._council.elected_mayor
        if proposer is None:
            return

        from city.council import ProposalType

        self._council.propose(
            title=f"Improve: {proposal.title}",
            description=proposal.description,
            proposer=proposer,
            proposal_type=ProposalType.POLICY,
            action={"type": "improve", "proposal_id": proposal.id},
            timestamp=time.time(),
        )

    def _seed_from_census(self) -> list[str]:
        """Seed agents from data/pokedex.json census file."""
        census_path = self._state_path.parent / "pokedex.json"
        if not census_path.exists():
            # Try repo-level data/
            census_path = Path("data/pokedex.json")
        if not census_path.exists():
            logger.info("GENESIS: No census file found, starting empty")
            return []

        try:
            data = json.loads(census_path.read_text())
            agents = data.get("agents", [])
            seeded: list[str] = []
            for agent in agents:
                name = agent.get("name")
                if not name:
                    continue
                existing = self._pokedex.get(name)
                if not existing:
                    self._pokedex.register(name)
                    seeded.append(name)
                    logger.info("GENESIS: Seeded citizen %s", name)
            logger.info("GENESIS: Seeded %d agents from census", len(seeded))
            return seeded
        except Exception as e:
            logger.warning("GENESIS: Census seeding failed: %s", e)
            return []

    # ── Layer 3: Mission Creators ─────────────────────────────────────

    def _create_healing_mission(self, contract_result: object) -> None:
        """Create a Sankalpa mission from a failing contract."""
        if self._sankalpa is None:
            return

        from vibe_core.mahamantra.protocols.sankalpa.types import (
            MissionPriority,
            MissionStatus,
            SankalpaMission,
        )

        mission_id = f"heal_{contract_result.name}_{self._heartbeat_count}"
        mission = SankalpaMission(
            id=mission_id,
            name=f"Heal: {contract_result.name}",
            description=f"Quality contract failing: {contract_result.message}",
            priority=MissionPriority.HIGH,
            status=MissionStatus.ACTIVE,
            owner="mayor",
        )
        self._sankalpa.registry.add_mission(mission)
        logger.info("DHARMA: Created healing mission %s", mission_id)

    def _create_audit_mission(self, finding: object) -> None:
        """Create a Sankalpa mission from a critical audit finding."""
        if self._sankalpa is None:
            return

        from vibe_core.mahamantra.protocols.sankalpa.types import (
            MissionPriority,
            MissionStatus,
            SankalpaMission,
        )

        mission_id = f"audit_{finding.source}_{self._heartbeat_count}"
        mission = SankalpaMission(
            id=mission_id,
            name=f"Audit: {finding.source}",
            description=f"Critical finding: {finding.description}",
            priority=MissionPriority.CRITICAL,
            status=MissionStatus.ACTIVE,
            owner="mayor",
        )
        self._sankalpa.registry.add_mission(mission)
        logger.info("MOKSHA: Created audit mission %s", mission_id)

    def _create_improvement_mission(self, proposal: object) -> None:
        """Create a Sankalpa mission from a reflection improvement proposal."""
        if self._sankalpa is None:
            return

        from vibe_core.mahamantra.protocols.sankalpa.types import (
            MissionPriority,
            MissionStatus,
            SankalpaMission,
        )

        mission_id = f"improve_{proposal.id}_{self._heartbeat_count}"
        mission = SankalpaMission(
            id=mission_id,
            name=f"Improve: {proposal.title}",
            description=proposal.description,
            priority=MissionPriority.MEDIUM,
            status=MissionStatus.ACTIVE,
            owner="mayor",
        )
        self._sankalpa.registry.add_mission(mission)
        logger.info("MOKSHA: Created improvement mission %s", mission_id)

    def _should_audit(self) -> bool:
        """Check if enough time has passed since last audit."""
        return (time.time() - self._last_audit_time) > AUDIT_COOLDOWN_S

    def _record_execution(self, department: str, duration_ms: float) -> None:
        """Record a heartbeat execution via Reflection protocol."""
        if self._reflection is None:
            return

        from vibe_core.protocols.reflection import ExecutionRecord

        record = ExecutionRecord(
            command=f"mayor.heartbeat.{department}",
            success=True,
            duration_ms=duration_ms,
        )
        self._reflection.record_execution(record)

    # ── External Interface ───────────────────────────────────────────

    def enqueue(self, source: str, text: str) -> None:
        """Add an item to the gateway queue for KARMA processing."""
        self._gateway_queue.append({"source": source, "text": text})

    def mark_active(self, name: str) -> None:
        """Mark an agent as active for the current metabolism cycle."""
        self._active_agents.add(name)

    # ── State Persistence ────────────────────────────────────────────

    def _load_state(self) -> None:
        if self._state_path.exists():
            try:
                data = json.loads(self._state_path.read_text())
                self._heartbeat_count = data.get("heartbeat_count", 0)
            except (json.JSONDecodeError, KeyError):
                pass

    def _save_state(self) -> None:
        state: MayorState = {
            "heartbeat_count": self._heartbeat_count,
            "last_heartbeat": time.time(),
            "discovered_agents": [a["name"] for a in self._pokedex.list_all()],
            "archived_agents": [a["name"] for a in self._pokedex.list_by_status("archived")],
            "total_governance_actions": 0,
            "total_operations": 0,
        }
        self._state_path.write_text(json.dumps(state, indent=2))
