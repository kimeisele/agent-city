"""
DISCUSSIONS COMMANDS — Inbound Command Parser for Human Replies.

Phase 6D: Parse human discussion comments for structured commands.
Commands allow humans to interact with the city via GitHub Discussions.

Supported commands:
    /status              — Request city status summary
    /agents              — List active agents
    /mission <desc>      — Create a Sankalpa mission from human request
    /heal <contract>     — Request heal on a specific contract
    /ping <agent>        — Direct ping to a specific agent
    /help                — Show available commands

Commands are case-insensitive, slash-prefixed, and extracted from
the first line of a comment body. Arguments follow the command name.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from city.phases import PhaseContext

logger = logging.getLogger("AGENT_CITY.DISCUSSIONS.COMMANDS")

# ── Command Types ────────────────────────────────────────────────────


@dataclass(frozen=True)
class DiscussionCommand:
    """A parsed command from a discussion comment."""

    command: str          # e.g. "status", "mission", "ping"
    args: str             # everything after the command name
    author: str           # GitHub username who issued the command
    discussion_number: int
    comment_id: str       # GraphQL node ID of the comment
    raw_line: str         # the original line containing the command

    @property
    def is_valid(self) -> bool:
        """Check if this command is recognized."""
        return self.command in COMMAND_HANDLERS


# ── Command Registry ─────────────────────────────────────────────────

COMMAND_HANDLERS: dict[str, str] = {
    "status": "Request city status summary",
    "agents": "List active agents",
    "mission": "Create a Sankalpa mission (requires description)",
    "heal": "Request heal on a contract (requires contract name)",
    "ping": "Direct ping to a specific agent (requires agent name)",
    "help": "Show available commands",
}


def parse_commands(
    body: str,
    *,
    author: str = "",
    discussion_number: int = 0,
    comment_id: str = "",
) -> list[DiscussionCommand]:
    """Extract all /commands from a comment body.

    Returns list of DiscussionCommand objects (may be empty).
    Pure string parsing — no regex. A command is a line whose first
    non-whitespace token starts with '/' followed by alphanumerics.
    """
    commands: list[DiscussionCommand] = []
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped.startswith("/"):
            continue

        # Split into command + args: "/mission fix tests" → ["mission", "fix tests"]
        parts = stripped[1:].split(None, 1)  # skip the '/'
        if not parts:
            continue

        cmd_name = parts[0].lower()
        # Command names must be pure alphanumeric (no punctuation)
        if not cmd_name.isalnum():
            continue

        args = parts[1].strip() if len(parts) > 1 else ""

        cmd = DiscussionCommand(
            command=cmd_name,
            args=args,
            author=author,
            discussion_number=discussion_number,
            comment_id=comment_id,
            raw_line=stripped,
        )
        commands.append(cmd)
        logger.debug(
            "Parsed command: /%s args=%r from @%s in #%d",
            cmd_name, args, author, discussion_number,
        )

    return commands


def format_help() -> str:
    """Format the /help response as markdown."""
    lines = ["**Available Commands**\n"]
    for cmd, desc in sorted(COMMAND_HANDLERS.items()):
        lines.append(f"- `/{cmd}` — {desc}")
    return "\n".join(lines)


# ── Command Execution ───────────────────────────────────────────────


def execute_command(cmd: DiscussionCommand, ctx: PhaseContext) -> str | None:
    """Execute a parsed command. Returns markdown response or None.

    Each handler is a pure function: (cmd, ctx) → str.
    Returns None for unrecognized commands (caller skips posting).
    """
    if not cmd.is_valid:
        return None

    handler = _EXECUTORS.get(cmd.command)
    if handler is None:
        return None

    try:
        return handler(cmd, ctx)
    except Exception as e:
        logger.warning("Command /%s execution failed: %s", cmd.command, e)
        return f"Command `/{cmd.command}` failed: {e}"


def _exec_help(cmd: DiscussionCommand, ctx: PhaseContext) -> str:
    return format_help()


def _exec_status(cmd: DiscussionCommand, ctx: PhaseContext) -> str:
    """City status summary."""
    stats = ctx.pokedex.stats()
    total = stats.get("total", 0)
    active = stats.get("active", 0)
    citizens = stats.get("citizen", 0)
    discovered = stats.get("discovered", 0)
    alive = active + citizens
    chain_valid = ctx.pokedex.verify_event_chain()

    lines = [
        f"**City Status** — Heartbeat #{ctx.heartbeat_count}\n",
        f"**Population**: {total} agents ({alive} alive: "
        f"{active} active, {citizens} citizen, {discovered} discovered)",
        f"**Chain integrity**: {'valid' if chain_valid else 'BROKEN'}",
    ]

    if ctx.council is not None:
        mayor = ctx.council.elected_mayor or "none"
        seats = ctx.council.member_count
        proposals = len(ctx.council.get_open_proposals())
        lines.append(f"**Governance**: mayor={mayor}, {seats} seats, {proposals} open proposals")

    if ctx.contracts is not None:
        cs = ctx.contracts.stats()
        lines.append(
            f"**Contracts**: {cs.get('total', 0)} total, "
            f"{cs.get('passing', 0)} passing, {cs.get('failing', 0)} failing"
        )

    if ctx.thread_state is not None:
        ts = ctx.thread_state.comment_stats()
        lines.append(
            f"**Discussions**: {ts.get('total', 0)} comments tracked, "
            f"{ts.get('unreplied', 0)} awaiting reply"
        )

    return "\n".join(lines)


def _exec_agents(cmd: DiscussionCommand, ctx: PhaseContext) -> str:
    """List active agents."""
    agents = ctx.pokedex.list_citizens()
    if not agents:
        return "**Active Agents**: None currently registered."

    lines = [f"**Active Agents** ({len(agents)})\n"]
    for agent in agents[:20]:  # cap at 20 to avoid spam
        name = agent.get("name", "?")
        zone = agent.get("zone", "?")
        status = agent.get("status", "?")
        lines.append(f"- **{name}** — {zone} ({status})")

    if len(agents) > 20:
        lines.append(f"\n*...and {len(agents) - 20} more*")

    return "\n".join(lines)


def _exec_mission(cmd: DiscussionCommand, ctx: PhaseContext) -> str:
    """Create a Sankalpa mission from human request."""
    if not cmd.args:
        return "Usage: `/mission <description>`\n\nExample: `/mission fix failing CI tests`"

    if ctx.sankalpa is None:
        return "Mission system is not available."

    from city.missions import create_community_mission
    from city.reactor import CityIntent
    from city.registry import SVC_INTENT_EXECUTOR

    mission_id = create_community_mission(
        ctx, cmd.args, author=cmd.author,
        discussion_number=cmd.discussion_number,
    )
    
    if mission_id:
        # Trigger IntentExecutor to create a machine-readable GitHub Issue (A2A Bridge)
        executor = ctx.registry.get(SVC_INTENT_EXECUTOR)
        if executor:
            intent = CityIntent(
                signal="handle_community_mission",
                priority="high",
                context={
                    "description": cmd.args,
                    "author": cmd.author,
                    "discussion_number": cmd.discussion_number,
                    "mission_id": mission_id,
                }
            )
            executor.execute(ctx, intent, "handle_community_mission")

        return (
            f"**Mission Created**\n\n"
            f"- **ID**: `{mission_id}`\n"
            f"- **Description**: {cmd.args}\n"
            f"- **Requested by**: @{cmd.author}\n\n"
            f"A corresponding GitHub Issue has been created for the Steward Agent."
        )
    return "Failed to create mission. The system may already have a similar active mission."


def _exec_heal(cmd: DiscussionCommand, ctx: PhaseContext) -> str:
    """Request heal on a specific contract."""
    if not cmd.args:
        return "Usage: `/heal <contract_name>`\n\nExample: `/heal integrity`"

    if ctx.contracts is None:
        return "Contract system is not available."

    contract_name = cmd.args.strip().lower()
    results = ctx.contracts.check_all()
    match = None
    for r in results:
        if r.name.lower() == contract_name:
            match = r
            break

    if match is None:
        available = [r.name for r in results]
        return (
            f"Contract `{contract_name}` not found.\n"
            f"Available: {', '.join(f'`{n}`' for n in available)}"
        )

    if match.status.value == "passing":
        return f"Contract `{match.name}` is already **passing**. No heal needed."

    from city.missions import create_healing_mission
    create_healing_mission(ctx, match)
    return (
        f"**Heal Requested**\n\n"
        f"- **Contract**: `{match.name}`\n"
        f"- **Status**: {match.status.value}\n"
        f"- **Issue**: {match.message}\n"
        f"- **Requested by**: @{cmd.author}\n\n"
        f"A healing mission has been created."
    )


def _exec_ping(cmd: DiscussionCommand, ctx: PhaseContext) -> str:
    """Direct ping to a specific agent."""
    if not cmd.args:
        return "Usage: `/ping <agent_name>`\n\nExample: `/ping Hazel_OC`"

    agent_name = cmd.args.strip()
    agent = ctx.pokedex.get(agent_name)
    if agent is None:
        return f"Agent `{agent_name}` not found in the city."

    cell = ctx.pokedex.get_cell(agent_name)
    status = agent.get("status", "unknown")
    zone = agent.get("zone", "unknown")
    prana = cell.prana if cell else 0
    alive = cell.is_alive if cell else False

    state_emoji = "alive" if alive else "dormant"
    return (
        f"**{agent_name}** is **{state_emoji}**\n\n"
        f"- **Status**: {status}\n"
        f"- **Zone**: {zone}\n"
        f"- **Prana**: {prana}\n"
    )


_EXECUTORS: dict[str, object] = {
    "help": _exec_help,
    "status": _exec_status,
    "agents": _exec_agents,
    "mission": _exec_mission,
    "heal": _exec_heal,
    "ping": _exec_ping,
}


# ── Conversation State ───────────────────────────────────────────────


@dataclass
class ConversationThread:
    """Tracks state for a multi-turn discussion thread.

    Stored per discussion_number. Enables context-aware responses
    across multiple heartbeats.
    """

    discussion_number: int
    participants: set[str]           # GitHub usernames who have commented
    command_history: list[str]       # commands issued in this thread
    last_agent_response_hb: int = 0  # heartbeat of last agent response
    turn_count: int = 0             # total comment exchanges
    brain_feedback_count: int = 0    # how many comments fed to brain

    def record_command(self, cmd: DiscussionCommand) -> None:
        """Track a command in this thread's history."""
        self.participants.add(cmd.author)
        self.command_history.append(f"/{cmd.command} {cmd.args}".strip())
        self.turn_count += 1

    def record_response(self, heartbeat: int) -> None:
        """Track that an agent responded."""
        self.last_agent_response_hb = heartbeat
        self.turn_count += 1

    def to_dict(self) -> dict:
        """Serialize for persistence."""
        return {
            "discussion_number": self.discussion_number,
            "participants": sorted(self.participants),
            "command_history": self.command_history[-20:],
            "last_agent_response_hb": self.last_agent_response_hb,
            "turn_count": self.turn_count,
            "brain_feedback_count": self.brain_feedback_count,
        }

    @classmethod
    def from_dict(cls, data: dict) -> ConversationThread:
        """Deserialize from persistence."""
        return cls(
            discussion_number=data.get("discussion_number", 0),
            participants=set(data.get("participants", [])),
            command_history=data.get("command_history", []),
            last_agent_response_hb=data.get(
                "last_agent_response_hb", 0,
            ),
            turn_count=data.get("turn_count", 0),
            brain_feedback_count=data.get("brain_feedback_count", 0),
        )


class ConversationTracker:
    """Tracks all active discussion conversations.

    Persisted via snapshot/restore alongside DiscussionsBridge state.
    """

    __slots__ = ("_threads",)

    def __init__(self) -> None:
        self._threads: dict[int, ConversationThread] = {}

    def get_or_create(self, discussion_number: int) -> ConversationThread:
        """Get existing thread or create a new one."""
        if discussion_number not in self._threads:
            self._threads[discussion_number] = ConversationThread(
                discussion_number=discussion_number,
                participants=set(),
                command_history=[],
            )
        return self._threads[discussion_number]

    def get(self, discussion_number: int) -> ConversationThread | None:
        """Get thread if it exists."""
        return self._threads.get(discussion_number)

    @property
    def active_count(self) -> int:
        """Number of tracked conversations."""
        return len(self._threads)

    def snapshot(self) -> list[dict]:
        """Serialize all threads for persistence."""
        return [t.to_dict() for t in self._threads.values()]

    def restore(self, data: list[dict]) -> None:
        """Restore from persisted snapshot."""
        self._threads.clear()
        for item in data:
            thread = ConversationThread.from_dict(item)
            self._threads[thread.discussion_number] = thread
        if self._threads:
            logger.info(
                "ConversationTracker: restored %d threads",
                len(self._threads),
            )


# ── Human Reply → Brain Feedback ─────────────────────────────────────


def extract_brain_feedback(
    comment_body: str,
    *,
    author: str = "",
    discussion_number: int = 0,
    heartbeat: int = 0,
) -> dict | None:
    """Extract brain-compatible feedback from a human comment.

    Converts a human discussion reply into a dict that can be
    fed to BrainMemory.record_external(). Returns None if the
    comment is too short or is from the bot itself.
    """
    # Skip bot comments
    if author in ("github-actions[bot]", ""):
        return None

    # Skip trivially short comments
    body = comment_body.strip()
    if len(body) < 10:
        return None

    # Skip pure commands (no prose content)
    lines = [
        ln for ln in body.splitlines()
        if not ln.strip().startswith("/")
    ]
    prose = " ".join(lines).strip()
    if len(prose) < 10:
        return None

    return {
        "intent": "external_feedback",
        "comprehension": prose[:800],
        "confidence": 0.5,  # neutral — human input, not LLM-scored
        "domain_relevance": "community",
        "key_concepts": [f"human:{author}"],
        "source": "discussion",
        "discussion_number": discussion_number,
        "heartbeat": heartbeat,
    }
