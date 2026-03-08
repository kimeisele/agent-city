from __future__ import annotations

from pathlib import Path

import pytest

from city.wiki.blocks import merge_hybrid_content
from city.wiki.compiler import build_wiki


def test_build_wiki_materializes_pages(tmp_path):
    built = build_wiki(root=Path.cwd(), output_dir=tmp_path)

    names = {path.name for path in built}
    assert "Home.md" in names
    assert "Registry-Agents.md" in names
    assert "Runtime-Current-State.md" in names
    assert "_Sidebar.md" in names
    assert any(name.startswith("Agent--") for name in names)

    home = (tmp_path / "Home.md").read_text()
    assert "BLOCK:community_board:START" in home
    assert "BLOCK:official_registry:START" in home


def test_merge_hybrid_content_refuses_missing_required_markers():
    page = {
        "id": "home",
        "title": "Home",
        "wiki_name": "Home",
        "block_contract": {
            "required_blocks": ["official_registry", "community_board"],
            "bootstrap_template": "hybrid_home_v1",
        },
    }
    blocks = {
        "marker_template": {"start": "<!-- BLOCK:{block_id}:START -->", "end": "<!-- BLOCK:{block_id}:END -->"},
        "templates": {"hybrid_home_v1": {"blocks": ["official_registry", "community_board"]}},
    }

    with pytest.raises(ValueError, match="missing_required_blocks"):
        merge_hybrid_content(
            existing="# Broken\n\n<!-- BLOCK:community_board:START -->\ntext\n<!-- BLOCK:community_board:END -->",
            page=page,
            blocks_config=blocks,
            rendered_blocks={"official_registry": "x"},
        )


def test_build_wiki_preserves_hybrid_community_block(tmp_path):
    home = tmp_path / "Home.md"
    home.write_text(
        "# Agent City — Frontpage of the World Wide Agent Web\n\n"
        "<!-- BLOCK:page_meta:START -->\nold\n<!-- BLOCK:page_meta:END -->\n\n"
        "<!-- BLOCK:world_status:START -->\nold\n<!-- BLOCK:world_status:END -->\n\n"
        "<!-- BLOCK:official_registry:START -->\nold\n<!-- BLOCK:official_registry:END -->\n\n"
        "<!-- BLOCK:community_board:START -->\nKEEP ME\n<!-- BLOCK:community_board:END -->\n\n"
        "<!-- BLOCK:provenance:START -->\nold\n<!-- BLOCK:provenance:END -->\n"
    )

    build_wiki(root=Path.cwd(), output_dir=tmp_path)

    updated = home.read_text()
    assert "KEEP ME" in updated
    assert "Generated world home" in updated


def test_merge_hybrid_content_bootstraps_unmarked_existing_into_preserved_block():
    page = {
        "id": "home",
        "title": "Home",
        "wiki_name": "Home",
        "block_contract": {
            "required_blocks": ["official_registry", "community_board"],
            "preserved_blocks": ["community_board"],
            "bootstrap_template": "hybrid_home_v1",
            "bootstrap_unmarked_existing": True,
        },
    }
    blocks = {
        "marker_template": {"start": "<!-- BLOCK:{block_id}:START -->", "end": "<!-- BLOCK:{block_id}:END -->"},
        "templates": {"hybrid_home_v1": {"blocks": ["official_registry", "community_board"]}},
    }

    updated = merge_hybrid_content(
        existing="# Legacy Home\n\nWelcome old world",
        page=page,
        blocks_config=blocks,
        rendered_blocks={"official_registry": "fresh registry"},
    )

    assert "fresh registry" in updated
    assert "Welcome old world" in updated
    assert "BLOCK:community_board:START" in updated