"""Tests for FederationRelay — Hub transport for NADI messages.

Verifies:
- push_to_hub: local outbox → Hub nadi_inbox.json
- pull_from_hub: Hub nadi_outbox.json → local inbox
- Deduplication, TTL filtering, buffer cap
- Hook wiring (pull in GENESIS, push in MOKSHA)

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import json
import time
from unittest.mock import MagicMock, patch

import pytest

from city.federation_relay import FederationRelay
from city.hooks.genesis.federation_relay_pull import FederationRelayPullHook
from city.hooks.moksha.federation_relay_push import FederationRelayPushHook


def _make_message(
    operation: str = "pr_review_request",
    source: str = "agent-city",
    pr_number: int = 1,
    timestamp: float | None = None,
    ttl_s: float = 7200.0,
) -> dict:
    return {
        "source": source,
        "target": "steward-protocol",
        "operation": operation,
        "payload": {"pr_number": pr_number},
        "priority": 1,
        "correlation_id": "",
        "timestamp": timestamp or time.time(),
        "ttl_s": ttl_s,
    }


class TestFederationRelay:
    """Unit tests for FederationRelay — mocked GitHub API."""

    def test_push_to_hub_sends_messages(self, tmp_path):
        """Local outbox messages are pushed to Hub inbox."""
        outbox = tmp_path / "nadi_outbox.json"
        inbox = tmp_path / "nadi_inbox.json"

        msgs = [_make_message(pr_number=42), _make_message(pr_number=43)]
        outbox.write_text(json.dumps(msgs))

        relay = FederationRelay(local_outbox=outbox, local_inbox=inbox)

        with patch.object(relay, "_token", "fake-token"), \
             patch.object(relay, "_read_hub_file", return_value=([], "sha123")), \
             patch.object(relay, "_write_hub_file", return_value=True) as mock_write:

            pushed = relay.push_to_hub()

        assert pushed == 2
        mock_write.assert_called_once()
        written_data = mock_write.call_args[0][1]
        assert len(written_data) == 2
        assert json.loads(outbox.read_text()) == []

    def test_push_merges_with_existing_hub_inbox(self, tmp_path):
        """Push merges new messages with existing Hub inbox."""
        outbox = tmp_path / "nadi_outbox.json"
        inbox = tmp_path / "nadi_inbox.json"

        new_msg = _make_message(pr_number=99)
        outbox.write_text(json.dumps([new_msg]))

        existing_hub = [_make_message(pr_number=1, source="other")]

        relay = FederationRelay(local_outbox=outbox, local_inbox=inbox)

        with patch.object(relay, "_token", "fake-token"), \
             patch.object(relay, "_read_hub_file", return_value=(existing_hub, "sha")), \
             patch.object(relay, "_write_hub_file", return_value=True) as mock_write:

            pushed = relay.push_to_hub()

        assert pushed == 1
        written_data = mock_write.call_args[0][1]
        assert len(written_data) == 2

    def test_push_empty_outbox_noop(self, tmp_path):
        """Empty local outbox → no push."""
        outbox = tmp_path / "nadi_outbox.json"
        outbox.write_text("[]")

        relay = FederationRelay(local_outbox=outbox, local_inbox=tmp_path / "in.json")

        with patch.object(relay, "_token", "fake-token"):
            assert relay.push_to_hub() == 0

    def test_push_no_token(self, tmp_path):
        """No token → no push."""
        outbox = tmp_path / "nadi_outbox.json"
        outbox.write_text(json.dumps([_make_message()]))

        relay = FederationRelay(local_outbox=outbox, local_inbox=tmp_path / "in.json")

        with patch.object(relay, "_token", ""):
            assert relay.push_to_hub() == 0

    def test_pull_from_hub_gets_new_messages(self, tmp_path):
        """New Hub outbox messages are pulled into local inbox."""
        outbox = tmp_path / "nadi_outbox.json"
        inbox = tmp_path / "nadi_inbox.json"

        hub_messages = [
            _make_message(operation="pr_review_verdict", source="steward", pr_number=42),
        ]

        relay = FederationRelay(local_outbox=outbox, local_inbox=inbox)

        with patch.object(relay, "_token", "fake-token"), \
             patch.object(relay, "_read_hub_file", return_value=(hub_messages, "sha")):

            pulled = relay.pull_from_hub()

        assert pulled == 1
        local_data = json.loads(inbox.read_text())
        assert len(local_data) == 1
        assert local_data[0]["payload"]["pr_number"] == 42

    def test_pull_deduplicates(self, tmp_path):
        """Already-seen messages are not pulled again."""
        outbox = tmp_path / "nadi_outbox.json"
        inbox = tmp_path / "nadi_inbox.json"

        ts = time.time()
        existing = _make_message(source="steward", pr_number=1, timestamp=ts)
        inbox.write_text(json.dumps([existing]))

        hub_messages = [
            existing,  # same — should be deduped
            _make_message(source="steward", pr_number=2),  # new
        ]

        relay = FederationRelay(local_outbox=outbox, local_inbox=inbox)

        with patch.object(relay, "_token", "fake-token"), \
             patch.object(relay, "_read_hub_file", return_value=(hub_messages, "sha")):

            pulled = relay.pull_from_hub()

        assert pulled == 1
        local_data = json.loads(inbox.read_text())
        assert len(local_data) == 2

    def test_pull_skips_expired(self, tmp_path):
        """Expired messages on Hub are not pulled."""
        expired_msg = _make_message(
            source="steward",
            timestamp=time.time() - 10000,
            ttl_s=1.0,
        )

        relay = FederationRelay(
            local_outbox=tmp_path / "out.json",
            local_inbox=tmp_path / "in.json",
        )

        with patch.object(relay, "_token", "fake-token"), \
             patch.object(relay, "_read_hub_file", return_value=([expired_msg], "sha")):

            assert relay.pull_from_hub() == 0

    def test_pull_no_token(self, tmp_path):
        """No token → no pull."""
        relay = FederationRelay(
            local_outbox=tmp_path / "out.json",
            local_inbox=tmp_path / "in.json",
        )
        with patch.object(relay, "_token", ""):
            assert relay.pull_from_hub() == 0

    def test_stats(self, tmp_path):
        """Stats returns correct counts."""
        outbox = tmp_path / "nadi_outbox.json"
        inbox = tmp_path / "nadi_inbox.json"
        outbox.write_text(json.dumps([_make_message(), _make_message()]))
        inbox.write_text(json.dumps([_make_message()]))

        relay = FederationRelay(local_outbox=outbox, local_inbox=inbox)
        s = relay.stats()
        assert s["local_outbox"] == 2
        assert s["local_inbox"] == 1

    def test_push_hub_write_failure_preserves_outbox(self, tmp_path):
        """If Hub write fails, local outbox is NOT cleared."""
        outbox = tmp_path / "nadi_outbox.json"
        msgs = [_make_message(pr_number=42)]
        outbox.write_text(json.dumps(msgs))

        relay = FederationRelay(local_outbox=outbox, local_inbox=tmp_path / "in.json")

        with patch.object(relay, "_token", "fake-token"), \
             patch.object(relay, "_read_hub_file", return_value=([], "sha")), \
             patch.object(relay, "_write_hub_file", return_value=False):

            pushed = relay.push_to_hub()

        assert pushed == 0
        # Outbox should still have the message
        assert len(json.loads(outbox.read_text())) == 1


class TestRelayHooks:
    """Test the GENESIS pull and MOKSHA push hooks."""

    def test_pull_hook_properties(self):
        hook = FederationRelayPullHook()
        assert hook.name == "federation_relay_pull"
        assert hook.phase == "genesis"
        assert hook.priority == 28

    def test_push_hook_properties(self):
        hook = FederationRelayPushHook()
        assert hook.name == "federation_relay_push"
        assert hook.phase == "moksha"
        assert hook.priority == 62

    @patch("city.federation_relay.FederationRelay")
    def test_pull_hook_calls_relay(self, MockRelay):
        """Pull hook instantiates relay and calls pull_from_hub."""
        mock_relay = MockRelay.return_value
        mock_relay.pull_from_hub.return_value = 5

        ctx = MagicMock()
        ctx.federation_nadi = MagicMock()
        ctx.offline_mode = False
        ops: list[str] = []

        hook = FederationRelayPullHook()
        hook.execute(ctx, ops)

        mock_relay.pull_from_hub.assert_called_once()
        assert "relay_pull:5" in ops

    @patch("city.federation_relay.FederationRelay")
    def test_push_hook_calls_relay(self, MockRelay):
        """Push hook instantiates relay and calls push_to_hub."""
        mock_relay = MockRelay.return_value
        mock_relay.push_to_hub.return_value = 3

        ctx = MagicMock()
        ctx.federation_nadi = MagicMock()
        ctx.offline_mode = False
        ctx._reflection = {}
        ops: list[str] = []

        hook = FederationRelayPushHook()
        hook.execute(ctx, ops)

        mock_relay.push_to_hub.assert_called_once()
        assert "relay_push:3" in ops

    def test_pull_hook_gate_offline(self):
        ctx = MagicMock()
        ctx.federation_nadi = MagicMock()
        ctx.offline_mode = True
        assert FederationRelayPullHook().should_run(ctx) is False

    def test_push_hook_gate_no_nadi(self):
        ctx = MagicMock()
        ctx.federation_nadi = None
        ctx.offline_mode = False
        assert FederationRelayPushHook().should_run(ctx) is False

    @patch("city.federation_relay.FederationRelay")
    def test_pull_hook_failure_non_fatal(self, MockRelay):
        """Relay failure doesn't crash the hook."""
        MockRelay.side_effect = Exception("network error")

        ctx = MagicMock()
        ctx.federation_nadi = MagicMock()
        ctx.offline_mode = False
        ops: list[str] = []

        hook = FederationRelayPullHook()
        hook.execute(ctx, ops)  # should not raise
        assert len(ops) == 0
