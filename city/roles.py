"""
CIVIC ROLES — Role Assignment for Agent City
==============================================

Roles are ASSIGNMENTS stored in Pokedex, not class inheritance.
No role hierarchy. No role objects. Just strings in the DB.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

from enum import Enum


class CivicRole(str, Enum):
    """Roles an agent can hold in the city."""

    CITIZEN = "citizen"
    COUNCIL_MEMBER = "council_member"
    ELECTED_MAYOR = "elected_mayor"


# Permissions per role
ROLE_PERMISSIONS: dict[CivicRole, frozenset[str]] = {
    CivicRole.CITIZEN: frozenset({"vote_public", "submit_petition"}),
    CivicRole.COUNCIL_MEMBER: frozenset(
        {
            "vote_public",
            "submit_petition",
            "propose",
            "vote_council",
        }
    ),
    CivicRole.ELECTED_MAYOR: frozenset(
        {
            "vote_public",
            "submit_petition",
            "propose",
            "vote_council",
            "sign_proposal",
            "call_election",
            "freeze_agent",
        }
    ),
}


def can(role: CivicRole, permission: str) -> bool:
    """Check if a role has a specific permission."""
    return permission in ROLE_PERMISSIONS.get(role, frozenset())
