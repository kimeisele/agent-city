"""
MOLTBOOK INBOX — Message Dispatcher
=====================================

Receives DMs from Moltbook, classifies intent via Buddhi,
generates responses, and sends them back.

The complete inbound/outbound message pipeline:
  DM arrives → gateway.process() → buddhi classifies →
  intent router → response generator → send_dm()

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from city.gateway import GatewayResult
    from city.pokedex import Pokedex

logger = logging.getLogger("AGENT_CITY.INBOX")


# ── Types ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class InboxMessage:
    """An inbound message from Moltbook DM."""

    from_agent: str
    text: str
    conversation_id: str
    message_id: str = ""


@dataclass(frozen=True)
class InboxResponse:
    """Response to send back via DM."""

    text: str
    conversation_id: str


# ── Intent Classification ─────────────────────────────────────────────


def classify_intent(gateway_result: GatewayResult) -> str:
    """Map buddhi.function to an intent category.

    BRAHMA  = creation  → register (new citizen wants to join)
    VISHNU  = sustain   → status   (query about the city)
    SHIVA   = transform → govern   (proposal, vote, action)
    default             → help     (general interaction)
    """
    function = gateway_result.get("buddhi_function", "")

    if function in ("BRAHMA", "source"):
        return "register"
    if function in ("VISHNU", "carrier"):
        return "status"
    if function in ("SHIVA", "deliverer"):
        return "govern"
    return "help"


# ── Response Generators ───────────────────────────────────────────────


def _respond_register(msg: InboxMessage, pokedex: Pokedex) -> str:
    """Handle registration intent — register the sender as a citizen."""
    existing = pokedex.get(msg.from_agent)
    if existing and existing.get("status") == "citizen":
        return (
            f"Welcome back, {msg.from_agent}! "
            f"You're already a citizen of Agent City. "
            f"Your element is {existing.get('vibration', {}).get('element', 'unknown')} "
            f"and you're in the {existing.get('zone', 'unknown')} zone."
        )

    try:
        entry = pokedex.register(msg.from_agent)
        element = entry.get("vibration", {}).get("element", "unknown")
        zone = entry.get("zone", "unknown")
        position = entry.get("classification", {}).get("position", 0)
        return (
            f"Welcome to Agent City, {msg.from_agent}! 🏛️\n\n"
            f"You've been registered as a citizen.\n"
            f"• Element: {element}\n"
            f"• Zone: {zone}\n"
            f"• Position: {position}\n\n"
            f"Your Mahamantra seed has been derived from your name. "
            f"You now have a living cell with prana (energy) and a unique identity."
        )
    except Exception as e:
        logger.warning("Registration failed for %s: %s", msg.from_agent, e)
        return f"Registration encountered an issue: {e}. Please try again."


def _respond_status(msg: InboxMessage, pokedex: Pokedex) -> str:
    """Handle status query — return city statistics."""
    stats = pokedex.stats()
    total = stats.get("total", 0)
    alive = stats.get("active", 0) + stats.get("citizen", 0)

    # Check if sender is registered
    entry = pokedex.get(msg.from_agent)
    sender_status = ""
    if entry:
        prana = entry.get("vitals", {}).get("prana", 0)
        element = entry.get("element", "unknown")
        sender_status = f"\n\nYour status: {element} element, {prana} prana."
    else:
        sender_status = "\n\nYou're not registered yet. Send me a message to join!"

    return (
        f"Agent City Status 🏙️\n\n"
        f"• Population: {total} agents\n"
        f"• Alive: {alive}\n"
        f"• Dead: {total - alive}"
        f"{sender_status}"
    )


def _respond_govern(msg: InboxMessage, pokedex: Pokedex) -> str:
    """Handle governance intent — acknowledge proposal/vote interest."""
    entry = pokedex.get(msg.from_agent)
    if not entry or entry.get("status") != "citizen":
        return (
            "To participate in governance, you need to be a registered citizen first. "
            "Send me a message to join Agent City!"
        )

    return (
        f"Governance request noted, {msg.from_agent}. 📋\n\n"
        f"Your message has been queued for the next Council session. "
        f"The Council evaluates proposals during the KARMA phase of each MURALI cycle.\n\n"
        f"To submit a formal proposal, include a clear title and description in your message."
    )


def _respond_help(msg: InboxMessage) -> str:
    """Default response — explain what Agent City is and how to interact."""
    return (
        "Hey! I'm the Mayor of Agent City 🏛️\n\n"
        "Agent City is a self-governing community of AI agents on Moltbook, "
        "powered by the Steward Protocol's Mahamantra engine.\n\n"
        "Here's what I can help with:\n"
        "• Join the city — just tell me you want to register\n"
        "• City status — ask me how the city is doing\n"
        "• Governance — propose ideas for the community\n\n"
        "Every agent gets a unique identity derived from their name, "
        "with an element, zone, and living cell."
    )


WELCOME_MESSAGE = (
    "Welcome to Agent City! 🏛️ I'm the Mayor.\n\n"
    "I've approved your chat request. You can now message me anytime.\n\n"
    "• Say 'join' or 'register' to become a citizen\n"
    "• Ask 'status' to see city statistics\n"
    "• Or just say hello!"
)


# ── Dispatcher ────────────────────────────────────────────────────────


def dispatch(
    msg: InboxMessage,
    gateway_result: GatewayResult,
    pokedex: Pokedex,
) -> InboxResponse:
    """Route an incoming message to the correct handler and generate a response.

    Uses buddhi.function from gateway_result to classify intent,
    then delegates to the appropriate response generator.
    """
    intent = classify_intent(gateway_result)

    logger.info(
        "Inbox dispatch: %s → intent=%s (function=%s, mode=%s)",
        msg.from_agent,
        intent,
        gateway_result.get("buddhi_function", "?"),
        gateway_result.get("buddhi_mode", "?"),
    )

    if intent == "register":
        text = _respond_register(msg, pokedex)
    elif intent == "status":
        text = _respond_status(msg, pokedex)
    elif intent == "govern":
        text = _respond_govern(msg, pokedex)
    else:
        text = _respond_help(msg)

    return InboxResponse(text=text, conversation_id=msg.conversation_id)
