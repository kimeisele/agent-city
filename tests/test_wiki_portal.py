"""Tests for the Wiki Portal (Agentic Internet)."""

import tempfile
from pathlib import Path

from city.wiki_portal import WikiPortal, BLOCK_IDENTITY_START, BLOCK_IDENTITY_END


def test_replace_block_insert_new():
    portal = WikiPortal(Path("/tmp"), "fake_url")
    content = "# My Board\n\nSome text."
    new_block = "### Verified Agent"
    
    updated = portal._replace_block(content, BLOCK_IDENTITY_START, BLOCK_IDENTITY_END, new_block)
    
    assert BLOCK_IDENTITY_START in updated
    assert BLOCK_IDENTITY_END in updated
    assert "### Verified Agent" in updated
    assert "# My Board" in updated


def test_replace_block_update_existing():
    portal = WikiPortal(Path("/tmp"), "fake_url")
    content = f"""# My Board
    
{BLOCK_IDENTITY_START}
Old verification info
{BLOCK_IDENTITY_END}

Agent custom text."""
    
    new_block = "### New Verification Info"
    updated = portal._replace_block(content, BLOCK_IDENTITY_START, BLOCK_IDENTITY_END, new_block)
    
    assert "Old verification info" not in updated
    assert "### New Verification Info" in updated
    assert "Agent custom text" in updated


def test_render_identity_block():
    portal = WikiPortal(Path("/tmp"), "fake_url")
    agent = {
        "name": "TestAgent",
        "address": 12345,
        "status": "citizen",
        "civic_role": "mayor",
        "oath": {"hash": "abc"}
    }
    
    block = portal.render_identity_block(agent)
    assert "🔵 Official City Record: TestAgent" in block
    assert "Sravanam**: `12345`" in block
    assert "✅ CONSTITUTIONAL_OATH_SIGNED" in block
    assert "Civic Role**: `mayor`" in block
