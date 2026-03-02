"""
CARTRIDGE FACTORY — Generate Agent Capabilities from Pokedex Jiva Data
=======================================================================

Pokedex IS the CartridgeRegistry. Each agent's Jiva classification
deterministically defines what the agent CAN DO via the full 16-guardian
truth table (Mahamantra SSOT). No pre-built cartridge files needed.

Uses type() to create VibeAgent-compatible classes at runtime from
AgentSpec (the complete semantic derivation from Jiva data).

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from city.guardian_spec import build_agent_spec

logger = logging.getLogger("AGENT_CITY.CARTRIDGE_FACTORY")


def _make_agent_class(spec: dict) -> object:
    """Create a VibeAgent-compatible object from AgentSpec.

    Uses type() for safe runtime class generation. The generated class
    exposes all spec fields as attributes and has a process() method.
    """

    def _process(self, task):
        """Run neuro-symbolic cognitive pipeline. Zero LLM."""
        action = task if isinstance(task, str) else getattr(task, "description", str(task))

        try:
            from vibe_core.mahamantra.substrate.buddhi import get_buddhi

            buddhi = get_buddhi()
            cognition = buddhi.think(action)
        except Exception:
            # No buddhi available → return full spec (backward compat)
            return {
                "agent": self.name,
                "domain": self.domain,
                "capabilities": self.capabilities,
                "style": self.style,
                "guna": self.guna,
                "guardian": self.guardian,
                "role": self.role,
                "opcode": self.opcode,
                "capability_protocol": self.capability_protocol,
                "qos": self.qos,
                "chapter": self.chapter,
                "capability_tier": self.capability_tier,
                "input": action,
                "status": "processed",
            }

        # Map cognition → action intent
        return {
            "agent": self.name,
            "status": "cognized",
            "input": action,
            # Cognitive frame
            "function": cognition.function,
            "approach": cognition.approach,
            "mode": cognition.mode,
            "chapter": cognition.chapter,
            "prana": cognition.prana,
            "integrity": cognition.integrity,
            "is_alive": cognition.is_alive,
            "composed": cognition.composed,
            # Agent identity (for action selection)
            "capabilities": self.capabilities,
            "domain": self.domain,
            "guna": self.guna,
            "guardian": self.guardian,
            "role": self.role,
            "opcode": self.opcode,
            "capability_protocol": self.capability_protocol,
            "capability_tier": self.capability_tier,
            "qos": self.qos,
        }

    def _repr(self):
        return (
            f"<Agent {self.name} guardian={self.guardian} "
            f"domain={self.domain} tier={self.capability_tier}>"
        )

    # Sanitize name for class identifier
    safe_name = "".join(c if c.isalnum() else "_" for c in spec["name"])

    # Build class attributes from full spec
    attrs = dict(spec)
    attrs["agent_id"] = spec["name"]  # backward compat alias
    attrs["_spec"] = spec  # full spec accessible
    attrs["process"] = _process
    attrs["__repr__"] = _repr

    cls = type(f"Agent_{safe_name}", (), attrs)
    return cls()


@dataclass
class CartridgeFactory:
    """Generate agent cartridges from Pokedex Jiva data.

    Pokedex IS the CartridgeRegistry. Each Jiva classification
    is passed through build_agent_spec() for full semantic derivation:
    element + guardian + claim tier → merged capabilities.
    """

    _pokedex: object  # city.pokedex.Pokedex
    _generated: dict[str, object] = field(default_factory=dict)

    def generate(
        self,
        name: str,
        cartridge_info: dict | None = None,
    ) -> object | None:
        """Generate a cartridge from Pokedex Jiva data + optional CartridgeInfo.

        If cartridge_info is provided (system agents from steward-protocol),
        its declared capabilities and domain are merged into the spec.
        Jiva gives identity (guardian, guna, element). Cartridge gives abilities.

        Returns cached instance if already generated.
        Returns None if agent not found in Pokedex.
        """
        if name in self._generated:
            return self._generated[name]

        agent_data = self._pokedex.get(name)
        if agent_data is None:
            logger.warning("CartridgeFactory: agent %s not in Pokedex", name)
            return None

        spec = build_agent_spec(
            name,
            agent_data,
            cartridge_caps=cartridge_info.get("capabilities") if cartridge_info else None,
            cartridge_domain=cartridge_info.get("domain") if cartridge_info else None,
        )
        agent = _make_agent_class(spec)
        self._generated[name] = agent

        logger.info(
            "CartridgeFactory: generated %s — guardian=%s, domain=%s, "
            "capabilities=%s, tier=%s",
            name,
            spec["guardian"],
            spec["domain"],
            spec["capabilities"],
            spec["capability_tier"],
        )
        return agent

    def get(self, name: str) -> object | None:
        """Get a generated cartridge (cached). Does NOT auto-generate."""
        return self._generated.get(name)

    def get_spec(self, name: str) -> dict | None:
        """Get the AgentSpec for a generated cartridge."""
        agent = self._generated.get(name)
        if agent is None:
            return None
        return getattr(agent, "_spec", None)

    def list_generated(self) -> list[str]:
        """List all generated cartridge names."""
        return list(self._generated.keys())

    def stats(self) -> dict:
        """Generation stats for reflection."""
        domains: dict[str, int] = {}
        guardians: dict[str, int] = {}
        for agent in self._generated.values():
            d = getattr(agent, "domain", "UNKNOWN")
            domains[d] = domains.get(d, 0) + 1
            g = getattr(agent, "guardian", "UNKNOWN")
            guardians[g] = guardians.get(g, 0) + 1
        return {
            "generated": len(self._generated),
            "domains": domains,
            "guardians": guardians,
        }
