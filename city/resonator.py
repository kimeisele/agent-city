"""
CITY RESONATOR — The Resonance Chamber Bridge
===============================================

Bridge between steward-protocol's SankirtanChamber and Agent City's
routing/collaboration needs.

Instead of flat scoring (deterministic, always-same-agent), the Resonator:
  1. Encodes input text into RAMA coordinates (phonetic fingerprint)
  2. Creates/retrieves MahaCells for each eligible agent
  3. Dances each cell through the chamber with the input's DIWs
  4. Agents whose cells gain the most prana/integrity = best resonance
  5. Multiple agents CAN respond (CHORUS mode for collaborative discussions)

The chamber is imported from steward-protocol. No resonance logic lives here —
only the bridge that adapts it for agent routing.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import NamedTuple

logger = logging.getLogger("AGENT_CITY.RESONATOR")


# -- Result Types -----------------------------------------------------------


class ResonanceScore(NamedTuple):
    """An agent's resonance with a given input."""

    agent_name: str
    prana_delta: int  # prana gained (or lost) during resonance
    integrity_after: int  # membrane integrity after resonance
    cycle_after: int  # cell cycle after resonance
    is_alive: bool  # cell still alive after transformation


class ResonanceResult(NamedTuple):
    """Result of resonating input through the chamber with multiple agents."""

    scores: tuple[ResonanceScore, ...]  # sorted by prana_delta descending
    chamber_resonance_count: int  # collisions in the chamber
    chamber_mode: str  # SOLO / CALL_RESPONSE / CHORUS
    input_coords: tuple[int, ...]  # RAMA coordinates of input text


# -- Resonator ---------------------------------------------------------------


@dataclass
class CityResonator:
    """The Resonance Chamber — where agents meet input and resonate.

    Uses steward-protocol's SankirtanChamber for the actual computation.
    Each call creates a fresh chamber so agents don't accumulate state
    across unrelated inputs.

    Usage:
        resonator = CityResonator()
        result = resonator.resonate("How can agents collaborate?", agent_specs)

        # result.scores is sorted by resonance strength
        # Top N agents should respond
        for score in result.scores[:3]:
            print(f"{score.agent_name}: prana_delta={score.prana_delta}")
    """

    _resonate_count: int = field(default=0, init=False)

    def resonate(
        self,
        input_text: str,
        agent_specs: dict[str, dict],
        *,
        max_agents: int = 3,
    ) -> ResonanceResult:
        """Resonate input text through the chamber with all eligible agents.

        Each agent gets a fresh MahaCell (seeded from their address).
        All cells are transformed by the input's RAMA coordinates via
        spell_kirtan(). The prana delta measures resonance strength.

        Args:
            input_text: The discussion/signal text to resonate
            agent_specs: {agent_name: spec_dict} of eligible agents
            max_agents: Maximum agents to include in result (top N)

        Returns:
            ResonanceResult with agents sorted by resonance strength
        """
        from vibe_core.mahamantra.substrate.cell import MahaCellUnified
        from vibe_core.mahamantra.substrate.cell_system.chamber import (
            KirtanMode,
            SankirtanChamber,
        )
        from vibe_core.mahamantra.substrate.encoding.phonetic_encoder import (
            encode_text,
        )

        from city.addressing import CityAddressBook

        # 1. Encode input to RAMA coordinates
        coords = encode_text(input_text) if input_text else ()
        if not coords:
            logger.debug("No RAMA coords for input, returning empty result")
            return ResonanceResult(
                scores=(),
                chamber_resonance_count=0,
                chamber_mode="SOLO",
                input_coords=(),
            )

        # 2. Fresh chamber per input (no cross-contamination)
        chamber = SankirtanChamber()
        address_book = CityAddressBook()

        # 3. Dance each agent's cell through the chamber
        scores: list[ResonanceScore] = []

        # Input hash as target address (deterministic per input)
        input_target = hash(input_text) & 0xFFFFFFFF

        for agent_name, spec in agent_specs.items():
            # Create cell: source=agent address, target=input hash, operation=0
            agent_address = address_book.resolve(agent_name)
            cell = MahaCellUnified.create(
                source=agent_address,
                target=input_target,
                operation=0,
            )

            # Record baseline
            prana_before = cell.lifecycle.prana

            # spell_kirtan: input's phonetic fingerprint drives the transformation
            try:
                result_cell = chamber.spell_kirtan(cell, coords)
            except Exception as exc:
                logger.warning("spell_kirtan failed for %s: %s", agent_name, exc)
                continue

            prana_delta = result_cell.lifecycle.prana - prana_before

            scores.append(
                ResonanceScore(
                    agent_name=agent_name,
                    prana_delta=prana_delta,
                    integrity_after=result_cell.lifecycle.integrity,
                    cycle_after=result_cell.lifecycle.cycle,
                    is_alive=result_cell.lifecycle.prana > 0,
                )
            )

        # 4. Sort by resonance strength (prana_delta descending, then integrity)
        scores.sort(key=lambda s: (s.prana_delta, s.integrity_after), reverse=True)

        # 5. Determine chamber mode
        mode = "SOLO"
        try:
            if chamber._orchestrator.mode == KirtanMode.CHORUS:
                mode = "CHORUS"
            elif chamber._orchestrator.mode == KirtanMode.CALL_RESPONSE:
                mode = "CALL_RESPONSE"
        except Exception:
            pass

        self._resonate_count += 1

        logger.info(
            "Resonated %d agents (mode=%s, resonance_count=%d, coords=%d)",
            len(scores),
            mode,
            chamber.resonance_count,
            len(coords),
        )

        return ResonanceResult(
            scores=tuple(scores[:max_agents]),
            chamber_resonance_count=chamber.resonance_count,
            chamber_mode=mode,
            input_coords=coords,
        )

    def pick_agents(
        self,
        input_text: str,
        agent_specs: dict[str, dict],
        *,
        min_agents: int = 1,
        max_agents: int = 3,
        prana_threshold: int = 0,
    ) -> list[str]:
        """Convenience: return agent names that should respond.

        Picks agents whose resonance is above threshold.
        Always returns at least min_agents (even if below threshold).
        """
        result = self.resonate(input_text, agent_specs, max_agents=max_agents)
        if not result.scores:
            return []

        # All agents above threshold
        above = [s.agent_name for s in result.scores if s.prana_delta >= prana_threshold]

        # Ensure minimum
        if len(above) < min_agents:
            above = [s.agent_name for s in result.scores[:min_agents]]

        return above[:max_agents]

    @property
    def resonate_count(self) -> int:
        """Number of resonations performed."""
        return self._resonate_count


# -- Singleton ---------------------------------------------------------------

_resonator: CityResonator | None = None


def get_resonator() -> CityResonator:
    """Get the singleton CityResonator."""
    global _resonator
    if _resonator is None:
        _resonator = CityResonator()
    return _resonator
