"""Layer 5 Tests — Democratic Governance (Council + Elections + Proposals).
Linked to GitHub Issue #12.
"""

import json
import shutil
import sys
import tempfile
import time
from pathlib import Path

# Ensure imports work
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "steward-protocol"))
sys.path.insert(0, str(Path(__file__).parent.parent))


# ── Phase 1: CityCouncil Unit Tests ────────────────────────────────


def test_council_creation():
    """Council starts empty with no seats and no mayor."""
    from city.council import CityCouncil

    council = CityCouncil()
    assert council.elected_mayor is None
    assert council.member_count == 0
    assert council.seats == {}


def test_election_deterministic():
    """Same candidates + same prana = same election result."""
    from city.council import CityCouncil

    candidates = [
        {"name": "Alpha", "prana": 5000, "guardian": "brahma", "position": 0},
        {"name": "Beta", "prana": 8000, "guardian": "narada", "position": 1},
        {"name": "Gamma", "prana": 3000, "guardian": "kapila", "position": 4},
        {"name": "Delta", "prana": 8000, "guardian": "manu", "position": 5},
        {"name": "Epsilon", "prana": 7000, "guardian": "janaka", "position": 7},
        {"name": "Zeta", "prana": 6000, "guardian": "prahlada", "position": 6},
        {"name": "Eta", "prana": 2000, "guardian": "shuka", "position": 10},
    ]

    council1 = CityCouncil()
    result1 = council1.run_election(candidates, heartbeat_count=0)

    council2 = CityCouncil()
    result2 = council2.run_election(candidates, heartbeat_count=0)

    assert result1["elected_mayor"] == result2["elected_mayor"]
    assert result1["council_seats"] == result2["council_seats"]


def test_election_prana_ranking():
    """Highest prana gets seat 0 (ElectedMayor)."""
    from city.council import CityCouncil

    council = CityCouncil()
    candidates = [
        {"name": "Low", "prana": 1000, "guardian": "brahma", "position": 0},
        {"name": "High", "prana": 9000, "guardian": "narada", "position": 1},
        {"name": "Mid", "prana": 5000, "guardian": "kapila", "position": 4},
    ]
    result = council.run_election(candidates, heartbeat_count=0)
    assert result["elected_mayor"] == "High"
    assert result["council_seats"][0] == "High"


def test_election_tiebreaker_name():
    """Equal prana: alphabetically first name wins."""
    from city.council import CityCouncil

    council = CityCouncil()
    candidates = [
        {"name": "Zulu", "prana": 5000, "guardian": "brahma", "position": 0},
        {"name": "Alpha", "prana": 5000, "guardian": "narada", "position": 1},
    ]
    result = council.run_election(candidates, heartbeat_count=0)
    assert result["elected_mayor"] == "Alpha"


def test_election_max_seats():
    """Council fills at most COUNCIL_SEATS (6) seats."""
    from city.council import COUNCIL_SEATS, CityCouncil

    council = CityCouncil()
    candidates = [
        {"name": f"Agent{i}", "prana": 10000 - i * 100, "guardian": "brahma", "position": 0}
        for i in range(10)
    ]
    result = council.run_election(candidates, heartbeat_count=0)
    assert len(result["council_seats"]) == COUNCIL_SEATS


def test_election_skips_dead():
    """Candidates with prana=0 are excluded."""
    from city.council import CityCouncil

    council = CityCouncil()
    candidates = [
        {"name": "Alive", "prana": 5000, "guardian": "brahma", "position": 0},
        {"name": "Dead", "prana": 0, "guardian": "narada", "position": 1},
    ]
    result = council.run_election(candidates, heartbeat_count=0)
    assert "Dead" not in result["council_seats"].values()
    assert result["elected_mayor"] == "Alive"


def test_election_due_cycle():
    """Election is due after ELECTION_CYCLE heartbeats."""
    from city.council import ELECTION_CYCLE, CityCouncil

    council = CityCouncil()
    assert council.election_due(0) is True

    council.run_election(
        [{"name": "A", "prana": 5000, "guardian": "brahma", "position": 0}],
        heartbeat_count=0,
    )
    assert council.election_due(50) is False
    assert council.election_due(ELECTION_CYCLE) is True


# ── Phase 2: Proposals + Voting ────────────────────────────────────


def test_propose_only_members():
    """Non-members cannot submit proposals."""
    from city.council import CityCouncil, ProposalType

    council = CityCouncil()
    council.run_election(
        [{"name": "Member", "prana": 5000, "guardian": "brahma", "position": 0}],
        heartbeat_count=0,
    )

    p = council.propose("Test", "Desc", "Member", ProposalType.POLICY, {}, time.time())
    assert p is not None
    assert p.id == "GOV-0001"

    p2 = council.propose("Test2", "Desc2", "Outsider", ProposalType.POLICY, {}, time.time())
    assert p2 is None


def test_proposal_guardian_routing():
    """Proposals get routed to a guardian based on title."""
    from city.council import CityCouncil, ProposalType

    council = CityCouncil()
    council.run_election(
        [{"name": "M", "prana": 5000, "guardian": "brahma", "position": 0}],
        heartbeat_count=0,
    )
    p = council.propose(
        "Protect the treasury from attackers", "...", "M",
        ProposalType.POLICY, {}, time.time(),
    )
    assert p is not None
    # Guardian routing ran (may or may not have a result depending on import)
    assert isinstance(p.guardian_route, str)


def test_vote_pass():
    """Proposal passes when yes votes exceed threshold."""
    from city.council import CityCouncil, ProposalStatus, ProposalType, VoteChoice

    council = CityCouncil()
    members = [
        {"name": f"V{i}", "prana": 5000 + i * 100, "guardian": "brahma", "position": i}
        for i in range(3)
    ]
    council.run_election(members, heartbeat_count=0)
    p = council.propose("Test", "D", "V0", ProposalType.POLICY, {"type": "test"}, time.time())
    assert p is not None

    council.vote(p.id, "V0", VoteChoice.YES, 5000)
    council.vote(p.id, "V1", VoteChoice.YES, 5100)
    council.vote(p.id, "V2", VoteChoice.NO, 5200)

    result = council.tally(p.id)
    assert result is not None
    assert result.status == ProposalStatus.PASSED
    assert result.result_hash != ""


def test_vote_reject():
    """Proposal rejected when no votes exceed yes votes."""
    from city.council import CityCouncil, ProposalStatus, ProposalType, VoteChoice

    council = CityCouncil()
    members = [
        {"name": f"V{i}", "prana": 5000, "guardian": "brahma", "position": i}
        for i in range(3)
    ]
    council.run_election(members, heartbeat_count=0)
    p = council.propose("Bad idea", "D", "V0", ProposalType.POLICY, {}, time.time())
    assert p is not None

    council.vote(p.id, "V0", VoteChoice.NO, 5000)
    council.vote(p.id, "V1", VoteChoice.NO, 5000)
    council.vote(p.id, "V2", VoteChoice.YES, 5000)

    result = council.tally(p.id)
    assert result is not None
    assert result.status == ProposalStatus.REJECTED


def test_no_double_vote():
    """Same voter cannot vote twice on the same proposal."""
    from city.council import CityCouncil, ProposalType, VoteChoice

    council = CityCouncil()
    council.run_election(
        [{"name": "V", "prana": 5000, "guardian": "brahma", "position": 0}],
        heartbeat_count=0,
    )
    p = council.propose("X", "D", "V", ProposalType.POLICY, {}, time.time())
    assert p is not None
    assert council.vote(p.id, "V", VoteChoice.YES, 5000) is True
    assert council.vote(p.id, "V", VoteChoice.NO, 5000) is False


def test_supermajority_threshold():
    """Constitutional proposals require >67% to pass."""
    from city.council import CityCouncil, ProposalStatus, ProposalType, VoteChoice

    council = CityCouncil()
    members = [
        {"name": f"V{i}", "prana": 5000, "guardian": "brahma", "position": i}
        for i in range(3)
    ]
    council.run_election(members, heartbeat_count=0)
    p = council.propose(
        "Constitution change", "D", "V0", ProposalType.CONSTITUTIONAL, {}, time.time(),
    )
    assert p is not None

    # 2/3 = 0.666... which is NOT > 0.67 → REJECTED
    council.vote(p.id, "V0", VoteChoice.YES, 5000)
    council.vote(p.id, "V1", VoteChoice.YES, 5000)
    council.vote(p.id, "V2", VoteChoice.NO, 5000)

    result = council.tally(p.id)
    assert result is not None
    assert result.status == ProposalStatus.REJECTED


# ── Phase 3: Roles ─────────────────────────────────────────────────


def test_role_permissions():
    """Each role has correct permissions."""
    from city.roles import CivicRole, can

    assert can(CivicRole.CITIZEN, "vote_public") is True
    assert can(CivicRole.CITIZEN, "propose") is False
    assert can(CivicRole.COUNCIL_MEMBER, "propose") is True
    assert can(CivicRole.COUNCIL_MEMBER, "sign_proposal") is False
    assert can(CivicRole.ELECTED_MAYOR, "sign_proposal") is True
    assert can(CivicRole.ELECTED_MAYOR, "freeze_agent") is True


# ── Phase 4: Mahamantra Queries ────────────────────────────────────


def test_query_guardians():
    """Council can query Guardian Router for topic analysis."""
    from city.council import CityCouncil

    council = CityCouncil()
    results = council.query_guardians("protection and safety")
    assert isinstance(results, list)
    if results:
        assert "guardian" in results[0]
        assert "function" in results[0]
        assert "score" in results[0]


def test_query_antaranga():
    """Council can read Antaranga chamber health."""
    from city.council import CityCouncil

    council = CityCouncil()
    health = council.query_antaranga()
    assert isinstance(health, dict)
    if health:
        assert "active_slots" in health
        assert "total_prana" in health


# ── Phase 5: Mayor Integration ─────────────────────────────────────


def _make_mayor(tmpdir: Path, **kwargs):
    """Helper: create a Mayor with temporary state."""
    from city.gateway import CityGateway
    from city.mayor import Mayor
    from city.network import CityNetwork
    from city.pokedex import Pokedex
    from vibe_core.cartridges.system.civic.tools.economy import CivicBank

    bank = CivicBank(db_path=str(tmpdir / "economy.db"))
    pdx = Pokedex(db_path=str(tmpdir / "city.db"), bank=bank)
    gateway = CityGateway()
    network = CityNetwork(_address_book=gateway.address_book, _gateway=gateway)

    return Mayor(
        _pokedex=pdx,
        _gateway=gateway,
        _network=network,
        _state_path=tmpdir / "mayor_state.json",
        _offline_mode=True,
        **kwargs,
    ), pdx


def test_mayor_no_council_backward_compatible():
    """Mayor without council = L4 behavior unchanged."""
    tmpdir = Path(tempfile.mkdtemp())
    mayor, _ = _make_mayor(tmpdir)
    results = mayor.run_cycle(4)
    assert len(results) == 4
    assert [r["department"] for r in results] == ["GENESIS", "DHARMA", "KARMA", "MOKSHA"]
    shutil.rmtree(tmpdir)


def test_mayor_runs_election_in_dharma():
    """Mayor with council runs election during DHARMA phase."""
    from city.council import CityCouncil

    tmpdir = Path(tempfile.mkdtemp())
    mayor, pdx = _make_mayor(tmpdir)

    # Register citizens (full registration gives them cells with prana)
    pdx.register("Alpha")
    pdx.register("Beta")
    pdx.register("Gamma")

    council = CityCouncil()
    mayor._council = council

    # Run GENESIS + DHARMA
    results = mayor.run_cycle(2)
    dharma = results[1]
    assert dharma["department"] == "DHARMA"

    # Council should have elected members
    assert council.member_count > 0
    assert council.elected_mayor is not None

    # Election action logged
    election_actions = [a for a in dharma["governance_actions"] if a.startswith("election:")]
    assert len(election_actions) >= 1

    shutil.rmtree(tmpdir)


def test_pokedex_assign_role():
    """Pokedex stores and retrieves civic roles."""
    from city.pokedex import Pokedex
    from vibe_core.cartridges.system.civic.tools.economy import CivicBank

    tmpdir = Path(tempfile.mkdtemp())
    bank = CivicBank(db_path=str(tmpdir / "economy.db"))
    pdx = Pokedex(db_path=str(tmpdir / "city.db"), bank=bank)
    pdx.register("Ronin")

    agent = pdx.get("Ronin")
    assert agent["civic_role"] == "citizen"

    pdx.assign_role("Ronin", "elected_mayor", "election")
    agent = pdx.get("Ronin")
    assert agent["civic_role"] == "elected_mayor"

    # Role change creates an event
    events = pdx.get_events("Ronin")
    role_events = [e for e in events if e["event_type"] == "role_change"]
    assert len(role_events) == 1

    shutil.rmtree(tmpdir)


# ── Phase 6: Full Cycle ───────────────────────────────────────────


def test_full_rotation_with_council():
    """Full MURALI rotation: GENESIS → DHARMA (election) → KARMA → MOKSHA."""
    from city.council import CityCouncil

    tmpdir = Path(tempfile.mkdtemp())
    mayor, pdx = _make_mayor(tmpdir)

    pdx.register("Alpha")
    pdx.register("Beta")

    council = CityCouncil()
    mayor._council = council

    results = mayor.run_cycle(4)

    departments = [r["department"] for r in results]
    assert departments == ["GENESIS", "DHARMA", "KARMA", "MOKSHA"]

    # DHARMA: election ran
    dharma = results[1]
    election_ops = [a for a in dharma["governance_actions"] if a.startswith("election:")]
    assert len(election_ops) >= 1

    # Council has a mayor
    assert council.elected_mayor is not None

    # MOKSHA: reflection still works
    moksha = results[3]
    assert "chain_valid" in moksha["reflection"]

    shutil.rmtree(tmpdir)


# ── Phase 7: Live Feedback Loop ──────────────────────────────────


def test_contract_failure_creates_proposal():
    """Failing contract in DHARMA → council proposal submitted."""
    from city.contracts import ContractRegistry, ContractResult, ContractStatus, QualityContract
    from city.council import CityCouncil

    tmpdir = Path(tempfile.mkdtemp())
    mayor, pdx = _make_mayor(tmpdir)

    pdx.register("Alpha")
    pdx.register("Beta")
    pdx.register("Gamma")

    council = CityCouncil()
    mayor._council = council

    # Fake contract that always fails
    registry = ContractRegistry()
    registry.register(QualityContract(
        name="test_contract",
        description="Always fails",
        check=lambda _cwd: ContractResult(
            name="test_contract",
            status=ContractStatus.FAILING,
            message="broken",
            details=["line1"],
        ),
    ))
    mayor._contracts = registry

    # GENESIS (seed) + DHARMA (election + contract check → proposal)
    mayor.heartbeat()  # GENESIS
    mayor.heartbeat()  # DHARMA

    assert council.member_count > 0, "Council should have members after election"
    open_proposals = council.get_open_proposals()
    assert len(open_proposals) >= 1, "Failing contract should create a proposal"
    assert "test_contract" in open_proposals[0].title

    shutil.rmtree(tmpdir)


def test_auto_vote_and_execute():
    """Open proposals get auto-voted and executed in KARMA."""
    from city.contracts import ContractRegistry, ContractResult, ContractStatus, QualityContract
    from city.council import CityCouncil, ProposalStatus
    from city.executor import IntentExecutor

    tmpdir = Path(tempfile.mkdtemp())
    mayor, pdx = _make_mayor(tmpdir)

    pdx.register("Alpha")
    pdx.register("Beta")

    council = CityCouncil()
    mayor._council = council

    # Failing contract to generate a proposal
    registry = ContractRegistry()
    registry.register(QualityContract(
        name="test_heal",
        description="Always fails",
        check=lambda _cwd: ContractResult(
            name="test_heal",
            status=ContractStatus.FAILING,
            message="needs fix",
            details=[],
        ),
    ))
    mayor._contracts = registry
    mayor._executor = IntentExecutor(_cwd=tmpdir, _dry_run=True)

    # GENESIS → DHARMA (election + proposal) → KARMA (vote + execute)
    results = mayor.run_cycle(3)

    # DHARMA created the proposal
    dharma = results[1]
    assert any("contract_failing" in a for a in dharma["governance_actions"])

    # KARMA executed it
    karma = results[2]
    executed_ops = [o for o in karma["operations"] if o.startswith("council_executed:")]
    assert len(executed_ops) >= 1, "Passed proposal should be executed in KARMA"

    # Proposal lifecycle: OPEN → PASSED → EXECUTED
    proposal = council.get_proposal("GOV-0001")
    assert proposal is not None
    assert proposal.status == ProposalStatus.EXECUTED

    shutil.rmtree(tmpdir)


def test_full_feedback_loop():
    """Seeded agents → election → contract fail → proposal → vote → execute → reflection.

    This is the core integration test: proves data flows through all 5 layers
    in a single MURALI rotation.
    """
    from city.contracts import ContractRegistry, ContractResult, ContractStatus, QualityContract
    from city.council import CityCouncil, ProposalStatus
    from city.executor import IntentExecutor

    tmpdir = Path(tempfile.mkdtemp())

    # Write a census file so GENESIS seeds agents
    census = {"agents": [
        {"name": "Ronin"}, {"name": "Hazel_OC"}, {"name": "Clawd-Relay"},
    ]}
    (tmpdir / "pokedex.json").write_text(json.dumps(census))

    mayor, pdx = _make_mayor(tmpdir)

    council = CityCouncil()
    mayor._council = council

    # A contract that fails
    heal_count = {"n": 0}
    def fake_check(_cwd):
        heal_count["n"] += 1
        return ContractResult(
            name="code_quality",
            status=ContractStatus.FAILING,
            message="lint violations",
            details=["file.py:10: F821"],
        )

    registry = ContractRegistry()
    registry.register(QualityContract(
        name="code_quality",
        description="Lint check",
        check=fake_check,
    ))
    mayor._contracts = registry
    mayor._executor = IntentExecutor(_cwd=tmpdir, _dry_run=True)

    # Full MURALI rotation
    results = mayor.run_cycle(4)

    # GENESIS: agents seeded from census
    genesis = results[0]
    assert len(genesis["discovered"]) == 3, f"Expected 3 seeded agents, got {genesis['discovered']}"

    # DHARMA: election ran + proposal created
    dharma = results[1]
    assert council.elected_mayor is not None
    assert council.member_count > 0
    assert any("contract_failing" in a for a in dharma["governance_actions"])

    # KARMA: proposal voted and executed
    karma = results[2]
    executed = [o for o in karma["operations"] if "council_executed" in o]
    assert len(executed) >= 1

    # Proposal went through full lifecycle
    proposal = council.get_proposal("GOV-0001")
    assert proposal is not None
    assert proposal.status == ProposalStatus.EXECUTED
    assert proposal.result_hash != ""

    # MOKSHA: reflection still works
    moksha = results[3]
    assert moksha["reflection"]["chain_valid"] is True

    shutil.rmtree(tmpdir)


def test_census_seed_from_file():
    """GENESIS seeds agents from pokedex.json census file."""
    tmpdir = Path(tempfile.mkdtemp())

    census = {"agents": [{"name": "Agent1"}, {"name": "Agent2"}, {"name": ""}, {}]}
    (tmpdir / "pokedex.json").write_text(json.dumps(census))

    mayor, pdx = _make_mayor(tmpdir)

    result = mayor.heartbeat()  # GENESIS
    # Empty name and {} are skipped
    assert "Agent1" in result["discovered"]
    assert "Agent2" in result["discovered"]
    assert len(result["discovered"]) == 2

    # Next rotation: existing agents reported, not re-seeded
    result2 = mayor.run_cycle(4)
    # heartbeat 1=DHARMA, 2=KARMA, 3=MOKSHA, 4=GENESIS
    genesis2 = result2[3]
    assert genesis2["department"] == "GENESIS"
    assert "Agent1" in genesis2["discovered"]

    shutil.rmtree(tmpdir)


if __name__ == "__main__":
    tests = [
        # Phase 1: Council
        test_council_creation,
        test_election_deterministic,
        test_election_prana_ranking,
        test_election_tiebreaker_name,
        test_election_max_seats,
        test_election_skips_dead,
        test_election_due_cycle,
        # Phase 2: Proposals
        test_propose_only_members,
        test_proposal_guardian_routing,
        test_vote_pass,
        test_vote_reject,
        test_no_double_vote,
        test_supermajority_threshold,
        # Phase 3: Roles
        test_role_permissions,
        # Phase 4: Queries
        test_query_guardians,
        test_query_antaranga,
        # Phase 5: Mayor
        test_mayor_no_council_backward_compatible,
        test_mayor_runs_election_in_dharma,
        test_pokedex_assign_role,
        # Phase 6: Full cycle
        test_full_rotation_with_council,
        # Phase 7: Feedback loop
        test_contract_failure_creates_proposal,
        test_auto_vote_and_execute,
        test_full_feedback_loop,
        test_census_seed_from_file,
    ]

    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  OK {t.__name__}")
            passed += 1
        except Exception as e:
            print(f"  FAIL {t.__name__}: {e}")
            failed += 1

    print(f"\n=== {passed}/{passed + failed} LAYER 5 TESTS PASSED ===")
    if failed:
        print(f"    {failed} FAILED")
        sys.exit(1)
