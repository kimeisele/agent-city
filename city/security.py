"""
Agent City Security Core — VajraGuarded Mixin
==============================================

Runtime tamper protection for critical services.
Adapted from steward-protocol (vibe_core/protocols/mahajanas/nrisimha/types/security.py).

Usage:
    class MyService(VajraGuarded):
        def __init__(self):
            VajraGuarded.__init__(self)
            self._critical = {...}
            self.protect_attribute("_critical")
            self.vajra_seal()

    svc = MyService()
    svc._critical = "hacked"  # raises PermissionError("VAJRA VIOLATION")
"""

import logging
from typing import Set

logger = logging.getLogger("AGENT_CITY.SECURITY")


class VajraGuarded:
    """Mixin that seals objects against attribute modification at runtime.

    Once vajra_seal() is called, protected attributes become immutable.
    Any attempt to modify them raises PermissionError.
    """

    def __init__(self):
        object.__setattr__(self, "_vajra_sealed", False)
        object.__setattr__(self, "_vajra_protected", set())

    def protect_attribute(self, name: str) -> None:
        """Mark an attribute as immutable after seal."""
        self._vajra_protected.add(name)

    def vajra_seal(self) -> None:
        """Activate the seal. Protected attributes become immutable."""
        object.__setattr__(self, "_vajra_sealed", True)
        logger.info(
            "VAJRA SEAL: %s locked. Protected: %s", self.__class__.__name__, self._vajra_protected
        )

    def vajra_unseal(self) -> None:
        """Temporarily unseal for controlled upgrades. Use sparingly."""
        object.__setattr__(self, "_vajra_sealed", False)
        logger.warning("VAJRA UNSEAL: %s unlocked!", self.__class__.__name__)

    def is_vajra_sealed(self) -> bool:
        return getattr(self, "_vajra_sealed", False)

    def get_protected_attributes(self) -> Set[str]:
        return getattr(self, "_vajra_protected", set()).copy()

    def __setattr__(self, name: str, value) -> None:
        if name in ("_vajra_sealed", "_vajra_protected"):
            object.__setattr__(self, name, value)
            return
        if getattr(self, "_vajra_sealed", False):
            protected = getattr(self, "_vajra_protected", set())
            if name in protected:
                logger.error(
                    "VAJRA VIOLATION: Attempt to modify '%s' on %s", name, self.__class__.__name__
                )
                raise PermissionError(
                    f"VAJRA VIOLATION: '{name}' on {self.__class__.__name__} "
                    f"is sealed. The blueprint is immutable."
                )
        object.__setattr__(self, name, value)
