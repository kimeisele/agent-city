from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from city.mayor_context import MayorContextBridge
from city.mayor_execution import MayorExecutionBridge
from city.mayor_lifecycle import MayorLifecycleBridge
from city.mayor_observation import MayorObservationBridge
from city.registry import SVC_BRAIN, SVC_BRAIN_MEMORY, SVC_CONVERSATION_TRACKER

if TYPE_CHECKING:
    from city.mayor import Mayor


@dataclass(frozen=True)
class MayorBootBridge:
    """Owns Mayor boot-time collaborator setup and restore choreography."""

    def bootstrap(self, mayor: Mayor) -> None:
        self._ensure_runtime_bridges(mayor)
        mayor._lifecycle.ensure_storage_dir()
        self._ensure_brain(mayor)
        self._ensure_brain_memory(mayor)
        self._ensure_conversation_tracker(mayor)
        mayor._lifecycle.restore_mayor(mayor)
        mayor._observation.wire_event_handlers(mayor)

    def _ensure_runtime_bridges(self, mayor: Mayor) -> None:
        if mayor._context is None:
            mayor._context = MayorContextBridge()
        if mayor._execution is None:
            mayor._execution = MayorExecutionBridge()
        if mayor._observation is None:
            mayor._observation = MayorObservationBridge()
        if mayor._lifecycle is None:
            mayor._lifecycle = MayorLifecycleBridge(state_path=mayor._state_path)

    def _ensure_brain(self, mayor: Mayor) -> None:
        if mayor._registry.has(SVC_BRAIN):
            return
        from city.brain import CityBrain

        mayor._registry.register(SVC_BRAIN, CityBrain())

    def _ensure_brain_memory(self, mayor: Mayor) -> None:
        if mayor._registry.has(SVC_BRAIN_MEMORY):
            return
        from city.brain_memory import BrainMemory

        brain_memory = BrainMemory(path=mayor._state_path.parent / "brain_memory.json")
        brain_memory.load()
        mayor._registry.register(SVC_BRAIN_MEMORY, brain_memory)

    def _ensure_conversation_tracker(self, mayor: Mayor) -> None:
        if mayor._registry.has(SVC_CONVERSATION_TRACKER):
            return
        from city.discussions_commands import ConversationTracker

        tracker = ConversationTracker()
        mayor._lifecycle.restore_conversation_tracker(tracker)
        mayor._registry.register(SVC_CONVERSATION_TRACKER, tracker)