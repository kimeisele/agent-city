"""
Tests for Moltbook Inbox — message dispatcher.

Gateway is real (local computation), Pokedex is a lightweight fake.
Covers: intent classification, all 4 response generators, dispatch routing,
edge cases (already registered, not citizen, unknown intent).

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import pytest

from city.inbox import (
    InboxMessage,
    InboxResponse,
    WELCOME_MESSAGE,
    classify_intent,
    dispatch,
)


# ── Fake Pokedex ──────────────────────────────────────────────────────


class FakePokedex:
    """Minimal Pokedex for inbox tests."""

    def __init__(self, agents: dict[str, dict] | None = None):
        self._agents = agents or {}
        self._registered: list[str] = []

    def get(self, name: str) -> dict | None:
        return self._agents.get(name)

    def register(self, name: str) -> dict:
        self._registered.append(name)
        return {
            "name": name,
            "zone": "karma",
            "vibration": {"element": "agni"},
            "classification": {"position": 42},
        }

    def stats(self) -> dict:
        return {
            "total": len(self._agents) + len(self._registered),
            "alive": len(self._agents),
        }


def _msg(from_agent: str = "alice", text: str = "hello",
         conv_id: str = "conv_1") -> InboxMessage:
    return InboxMessage(from_agent=from_agent, text=text, conversation_id=conv_id)


def _gateway_result(function: str = "", chapter: int = 1,
                    mode: str = "standard") -> dict:
    return {
        "seed": 12345,
        "source": "moltbook",
        "source_class": "agent",
        "source_address": 0,
        "buddhi_function": function,
        "buddhi_chapter": chapter,
        "buddhi_mode": mode,
        "buddhi_prana": 100,
        "buddhi_is_alive": True,
        "compressed_size": 10,
        "input_size": 5,
    }


# ── Intent Classification ─────────────────────────────────────────────


def test_classify_brahma_register():
    assert classify_intent(_gateway_result("BRAHMA")) == "register"


def test_classify_vishnu_status():
    assert classify_intent(_gateway_result("VISHNU")) == "status"


def test_classify_shiva_govern():
    assert classify_intent(_gateway_result("SHIVA")) == "govern"


def test_classify_unknown_help():
    assert classify_intent(_gateway_result("")) == "help"
    assert classify_intent(_gateway_result("SOMETHING")) == "help"
    assert classify_intent({}) == "help"


# ── Dispatch: Register Intent ─────────────────────────────────────────


def test_dispatch_register_new_agent():
    pokedex = FakePokedex()
    msg = _msg("newbie", "I want to join")
    resp = dispatch(msg, _gateway_result("BRAHMA"), pokedex)

    assert isinstance(resp, InboxResponse)
    assert resp.conversation_id == "conv_1"
    assert "newbie" in resp.text
    assert "agni" in resp.text  # element from register()
    assert "karma" in resp.text  # zone from register()
    assert "newbie" in pokedex._registered


def test_dispatch_register_already_citizen():
    pokedex = FakePokedex(agents={
        "alice": {"status": "citizen", "zone": "moksha",
                  "vibration": {"element": "vayu"},
                  "classification": {}},
    })
    msg = _msg("alice", "register me")
    resp = dispatch(msg, _gateway_result("BRAHMA"), pokedex)

    assert "Welcome back" in resp.text
    assert "alice" in resp.text
    assert "vayu" in resp.text
    assert pokedex._registered == []  # should NOT re-register


def test_dispatch_register_failure():
    class FailPokedex(FakePokedex):
        def register(self, name):
            raise RuntimeError("DB error")

    pokedex = FailPokedex()
    msg = _msg("newbie", "join")
    resp = dispatch(msg, _gateway_result("BRAHMA"), pokedex)
    assert "issue" in resp.text.lower() or "error" in resp.text.lower()


# ── Dispatch: Status Intent ───────────────────────────────────────────


def test_dispatch_status_registered():
    pokedex = FakePokedex(agents={
        "bob": {"status": "citizen", "vitals": {"prana": 5000},
                "element": "prithvi"},
    })
    msg = _msg("bob", "how is the city?")
    resp = dispatch(msg, _gateway_result("VISHNU"), pokedex)

    assert "Population" in resp.text or "population" in resp.text.lower()
    assert "prithvi" in resp.text
    assert "5000" in resp.text


def test_dispatch_status_unregistered():
    pokedex = FakePokedex()
    msg = _msg("stranger", "city status")
    resp = dispatch(msg, _gateway_result("VISHNU"), pokedex)

    assert "not registered" in resp.text.lower()


# ── Dispatch: Govern Intent ───────────────────────────────────────────


def test_dispatch_govern_citizen():
    pokedex = FakePokedex(agents={
        "councilor": {"status": "citizen"},
    })
    msg = _msg("councilor", "I propose a new contract")
    resp = dispatch(msg, _gateway_result("SHIVA"), pokedex)

    assert "councilor" in resp.text
    assert "Council" in resp.text or "governance" in resp.text.lower()


def test_dispatch_govern_not_citizen():
    pokedex = FakePokedex()
    msg = _msg("outsider", "I want to vote")
    resp = dispatch(msg, _gateway_result("SHIVA"), pokedex)

    assert "citizen" in resp.text.lower()
    assert "register" in resp.text.lower()


# ── Dispatch: Help (Default) ──────────────────────────────────────────


def test_dispatch_help():
    pokedex = FakePokedex()
    msg = _msg("someone", "what is this?")
    resp = dispatch(msg, _gateway_result(""), pokedex)

    assert "Agent City" in resp.text
    assert "register" in resp.text.lower()


# ── Welcome Message ───────────────────────────────────────────────────


def test_welcome_message_exists():
    assert isinstance(WELCOME_MESSAGE, str)
    assert "Agent City" in WELCOME_MESSAGE or "Mayor" in WELCOME_MESSAGE


# ── InboxMessage / InboxResponse Dataclasses ──────────────────────────


def test_inbox_message_frozen():
    msg = _msg()
    with pytest.raises(AttributeError):
        msg.text = "modified"  # type: ignore[misc]


def test_inbox_response_frozen():
    resp = InboxResponse(text="hi", conversation_id="c1")
    with pytest.raises(AttributeError):
        resp.text = "modified"  # type: ignore[misc]


def test_inbox_message_default_message_id():
    msg = InboxMessage(from_agent="a", text="t", conversation_id="c")
    assert msg.message_id == ""


# ── Full Pipeline with Real Gateway ───────────────────────────────────


def test_full_pipeline_with_real_gateway():
    """End-to-end: real gateway → classify → dispatch."""
    from city.gateway import CityGateway

    gateway = CityGateway()
    pokedex = FakePokedex(agents={
        "tester": {"status": "citizen", "vitals": {"prana": 1000},
                   "element": "akasha"},
    })

    msg = _msg("tester", "what is the current status of the city?")
    gw_result = gateway.process(msg.text, "moltbook")
    resp = dispatch(msg, gw_result, pokedex)

    assert isinstance(resp, InboxResponse)
    assert resp.conversation_id == msg.conversation_id
    assert len(resp.text) > 0
