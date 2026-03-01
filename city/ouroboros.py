"""
OUROBOROS GENE SYSTEM — Runtime Chaos Engineering
=================================================

Injects perturbations during live execution to verify system resilience.
Modeled after the eternal cycle of creation/destruction.
"""

import logging
import random
from dataclasses import dataclass, field

logger = logging.getLogger("AGENT_CITY.OUROBOROS")

# Services registry keys (used in DI)
SVC_OUROBOROS = "ouroboros"


@dataclass
class OuroborosGeneSystem:
    """Chaos engineering injection system."""

    enabled: bool = True
    entropy_load: int = 0
    mantra_shield: int = 100
    mutation_vector: float = 0.0

    # Stats tracking
    _total_mutations: int = field(default=0, init=False)
    _dropped_messages: int = field(default=0, init=False)

    def __post_init__(self):
        if self.enabled:
            logger.warning("Ouroboros Gene System is active. Chaos will be injected.")

    def inject_chaos(self) -> None:
        """Tick the chaos engine, randomly shifting active parameters."""
        if not self.enabled:
            return

        # Slight random walk on entropy
        self.entropy_load = max(0, min(100, self.entropy_load + random.randint(-5, 5)))
        
        # Shield degrades slowly over time if not reset
        if self.mantra_shield > 0 and random.random() < 0.1:
            self.mantra_shield -= 1

        # Mutation vector pulses
        if random.random() < 0.05:
            self.mutation_vector = round(random.uniform(0.1, 0.5), 2)
        else:
            self.mutation_vector *= 0.9  # Decay back to 0

    def should_drop_message(self) -> bool:
        """Determine if a network packet should be artificially dropped."""
        if not self.enabled:
            return False

        # If shield is high, drop chance is low. If entropy is high, drop chance increases.
        base_drop_chance = (self.entropy_load / 100.0) * 0.2  # Max 20% drop from load
        shield_mitigation = (self.mantra_shield / 100.0) * 0.15 # Up to 15% mitigated by shield
        
        effective_drop_chance = max(0.0, base_drop_chance - shield_mitigation + self.mutation_vector)
        
        if random.random() < effective_drop_chance:
            self._dropped_messages += 1
            return True
        return False

    def stats(self) -> dict:
        return {
            "enabled": self.enabled,
            "entropy_load": self.entropy_load,
            "mantra_shield": self.mantra_shield,
            "mutation_vector": self.mutation_vector,
            "total_mutations": self._total_mutations,
            "dropped_messages": self._dropped_messages,
        }
