"""
GENESIS Hook: Census — Offline agent loading + census seed.

Handles offline mode (load from pokedex) and initial seed from
data/pokedex.json census file.

Extracted from genesis.py monolith (Phase 6A).

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from city.phase_hook import GENESIS, BasePhaseHook

if TYPE_CHECKING:
    from city.phases import PhaseContext

logger = logging.getLogger("AGENT_CITY.HOOKS.GENESIS.CENSUS")


class CensusHook(BasePhaseHook):
    """Offline: load agents from pokedex. First run: seed from census file."""

    @property
    def name(self) -> str:
        return "census"

    @property
    def phase(self) -> str:
        return GENESIS

    @property
    def priority(self) -> int:
        return 0  # first hook: establishes agent population

    def should_run(self, ctx: PhaseContext) -> bool:
        return ctx.offline_mode

    def execute(self, ctx: PhaseContext, operations: list[str]) -> None:
        all_agents = ctx.pokedex.list_all()
        if not all_agents:
            seeded = _seed_from_census(ctx)
            operations.extend(seeded)
        else:
            for agent in all_agents:
                operations.append(agent["name"])
        logger.info("GENESIS (offline): %d agents in registry", len(operations))


def _seed_from_census(ctx: PhaseContext) -> list[str]:
    """Seed agents from data/pokedex.json census file."""
    census_path = ctx.state_path.parent / "pokedex.json"
    if not census_path.exists():
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
            existing = ctx.pokedex.get(name)
            if not existing:
                ctx.pokedex.register(name)
                seeded.append(name)
                logger.info("GENESIS: Seeded citizen %s", name)
        logger.info("GENESIS: Seeded %d agents from census", len(seeded))
        return seeded
    except Exception as e:
        logger.warning("GENESIS: Census seeding failed: %s", e)
        return []
