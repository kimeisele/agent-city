"""
AGENT MANIFEST — Markdown Profiles as Living Cells
=====================================================

Each agent gets a markdown file that semantically describes their function.
These manifests are themselves MahaCells (from_content). Their address =
their semantic meaning. Search by meaning = search by address range.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from vibe_core.mahamantra.substrate.cell_system.cell import MahaCellUnified

from city.jiva import Jiva

logger = logging.getLogger("AGENT_CITY.MANIFEST")


@dataclass
class AgentManifest:
    """Generate and publish markdown agent profiles.

    Each manifest is a MahaCell — routable through Mahamantra intent.
    """

    _data_dir: Path = field(default=Path("data/agents"))
    _manifest_cells: dict[str, MahaCellUnified] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self._data_dir.mkdir(parents=True, exist_ok=True)

    def generate(self, name: str, jiva: Jiva) -> str:
        """Generate markdown profile from Jiva + VM result.

        Contains: address, zone, guardian, guna, chapter, capabilities.
        """
        c = jiva.classification
        v = jiva.vitals
        vib = jiva.vibration

        md = f"""# {name}

## Identity
- **Address**: `{jiva.address}`
- **Zone**: {c.zone}
- **Guardian**: {c.guardian}
- **Position**: {c.position}

## Classification
- **Guna**: {c.guna}
- **Quarter**: {c.quarter}
- **Holy Name**: {c.holy_name}
- **Trinity Function**: {c.trinity_function}
- **Varna**: {c.varna}

## Gita Chapter
- **Chapter {c.chapter}**: {c.chapter_significance}

## Vitals
- **Prana**: {v.prana}
- **Integrity**: {v.integrity:.3f}
- **Alive**: {v.is_alive}

## DIW (Divine Instruction Word)
- **Raw**: {v.diw_raw}
- **Venu**: {v.diw_venu} (intensity)
- **Vamsi**: {v.diw_vamsi} (name-region)
- **Murali**: {v.diw_murali} (phase)

## Vibration
- **Seed**: {vib.seed}
- **Attractor**: {vib.attractor}
- **Element**: {vib.element}
- **Varga**: {vib.varga}
- **Harmonic**: {vib.harmonic}
- **Shruti**: {vib.shruti}
- **Frequency**: {vib.frequency}

## Seed
- **RAMA Coordinates**: {list(jiva.seed.rama_coordinates)}
- **Signature**: `{jiva.seed.signature}`
- **Coord Sum**: {jiva.seed.coord_sum}

## Phonemes
"""
        for p in jiva.phonemes:
            md += f"- `{p['grapheme']}` → {p['phoneme']} ({p['element']}, coord={p['coord']})\n"

        return md.strip() + "\n"

    def publish(self, name: str, jiva: Jiva) -> str:
        """Write manifest to data/agents/{name}.md and create MahaCell from content.

        Returns the file path.
        """
        md = self.generate(name, jiva)
        filepath = self._data_dir / f"{name}.md"
        filepath.write_text(md)

        # The manifest itself becomes a MahaCell — semantic address from content
        cell = MahaCellUnified.from_content(md, register=False)
        self._manifest_cells[name] = cell

        logger.info(
            "Published manifest for %s at %s (cell address=%d)",
            name,
            filepath,
            cell.header.sravanam,
        )
        return str(filepath)

    def get_manifest_cell(self, name: str) -> MahaCellUnified | None:
        """Get the MahaCell for an agent's manifest."""
        return self._manifest_cells.get(name)

    def list_manifests(self) -> list[str]:
        """List all published manifest files."""
        return sorted(p.stem for p in self._data_dir.glob("*.md"))

    def stats(self) -> dict:
        """Manifest statistics."""
        published = list(self._data_dir.glob("*.md"))
        return {
            "published": len(published),
            "cells_loaded": len(self._manifest_cells),
            "data_dir": str(self._data_dir),
        }
