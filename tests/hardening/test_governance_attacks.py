import json
import time

import pytest


def _root_membrane():
    from city.membrane import internal_membrane_snapshot

    return internal_membrane_snapshot(source_class="tests")



def test_ghost_voter_rejected(tmp_dir):
    """Non-member votes must be rejected.

    Attack vector: Agent not on council tries to vote.
    Impact: Outsiders control governance decisions.
    """
    from city.council import CityCouncil, ProposalType, VoteChoice

    council = CityCouncil(_state_path=tmp_dir / "council.json")
    council.run_election(
        [
            {"name": "Member1", "prana": 5000, "guardian": "", "position": 0},
            {"name": "Member2", "prana": 4000, "guardian": "", "position": 1},
        ],
        heartbeat_count=0,
    )

    p = council.propose(
        "Test", "Desc", "Member1", ProposalType.POLICY,
        {"type": "test"}, time.time(),
    )
    assert p is not None

    # ATTACK: Outsider votes
    result = council.vote(p.id, "Ghost_Agent", VoteChoice.YES, 99999)
    assert result is False, (
        "VULNERABILITY: Non-member vote accepted! "
        "Any agent can hijack governance."
    )


def test_zero_prana_candidate_excluded(tmp_dir):
    """Dead agents (prana=0) must not win elections.

    Attack vector: Register an agent, kill it, try to get it elected.
    Impact: Dead agents making governance decisions.
    """
    from city.council import CityCouncil

    council = CityCouncil()
    result = council.run_election(
        [
            {"name": "Dead_Agent", "prana": 0, "guardian": "", "position": 0},
            {"name": "Alive_Agent", "prana": 1000, "guardian": "", "position": 1},
        ],
        heartbeat_count=0,
    )

    assert result["elected_mayor"] == "Alive_Agent", (
        "VULNERABILITY: Dead agent became mayor!"
    )
    assert "Dead_Agent" not in result["council_seats"].values(), (
        "VULNERABILITY: Dead agent holds council seat!"
    )


def test_direct_mayor_escalation_denied_without_root_membrane(tmp_dir):
    """Compromised code must not self-promote via direct Pokedex role mutation."""
    from city.pokedex import Pokedex
    from vibe_core.cartridges.system.civic.tools.economy import CivicBank

    bank = CivicBank(db_path=str(tmp_dir / "economy.db"))
    pdx = Pokedex(db_path=str(tmp_dir / "city.db"), bank=bank)
    pdx.register("Rogue")

    with pytest.raises(PermissionError, match="root_mutation_denied:access<sovereign"):
        pdx.assign_role("Rogue", "elected_mayor", "self_promotion")

    pdx.assign_role("Rogue", "elected_mayor", "trusted_election", membrane=_root_membrane())
    assert pdx.get("Rogue")["civic_role"] == "elected_mayor"


def test_proposal_injection_via_action_field(tmp_dir):
    """Malicious action payloads must not break proposal processing.

    Attack vector: Inject dangerous data in the action dict.
    Impact: Code injection, deserialization attacks.
    """
    from city.council import CityCouncil, ProposalType

    council = CityCouncil(_state_path=tmp_dir / "council.json")
    council.run_election(
        [{"name": "M", "prana": 5000, "guardian": "", "position": 0}],
        heartbeat_count=0,
    )

    # ATTACK: Dangerous action payloads
    dangerous_payloads = [
        {"type": "__import__('os').system('rm -rf /')", "data": "pwned"},
        {"type": "eval", "__builtins__": None, "exec": "dangerous"},
        {"type": "x" * 10_000},  # Huge payload
        {"$where": "this.secret", "type": "nosql_inject"},
        {"type": "normal", "nested": {"a": {"b": {"c": {"d": "deep" * 100}}}}},
    ]

    for payload in dangerous_payloads:
        p = council.propose(
            "Dangerous", "Test", "M", ProposalType.POLICY,
            payload, time.time(),
        )
        if p is not None:
            # Proposal accepted but action must be stored safely
            stored = council.get_proposal(p.id)
            assert stored is not None
            # Verify it serializes/deserializes without executing
            data = council.to_dict()
            restored = json.loads(json.dumps(data))
            assert isinstance(restored, dict), (
                f"VULNERABILITY: Dangerous payload broke serialization"
            )