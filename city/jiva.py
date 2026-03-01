"""
JIVA ENGINE — Agent Identity from the Mahamantra VM
=====================================================

Every field derived by running the name through the REAL Mahamantra VM pipeline:
Compression → Attractor → Synth → 9-step NavaBhakti → 27-key result dict.

Each agent IS a MahaCellUnified — a living computational unit with:
- 72-byte MahaHeader (identity)
- CellLifecycleState (prana, integrity, cycle, membrane)
- Biological operations (conceive, metabolize, mitosis, apoptosis)

Nothing homebrew. Nothing invented. The VM is the single source of truth.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare

Usage:
    from city.jiva import derive_jiva
    jiva = derive_jiva("Ronin")
    jiva.cell.is_alive  # True — living MahaCell
    jiva.cell.prana     # 13700 — life energy
"""

from __future__ import annotations

from dataclasses import dataclass

from vibe_core.mahamantra import mahamantra
from vibe_core.mahamantra.substrate.cell_system.cell import MahaCellUnified
from vibe_core.mahamantra.substrate.encoding.phonetic_encoder import (
    encode_text,
    encode_with_detail,
)
from vibe_core.mahamantra.substrate.encoding.pancha_walk import full_signature


# Pancha Tattva → Varna (6 Vedic species)
ELEMENT_TO_VARNA = {
    "akasha": "MANUSHA",
    "vayu": "PAKSHI",
    "agni": "PASHU",
    "jala": "JALAJA",
    "prithvi": "KRIMAYO",
}

# Quarter → Zone in the city
QUARTER_TO_ZONE = {
    "genesis": "discovery",
    "dharma": "governance",
    "karma": "engineering",
    "moksha": "research",
}


# ── Jiva Data ────────────────────────────────────────────────────────

@dataclass(frozen=True)
class JivaSeed:
    """Immutable Mahamantra seed — the cryptographic root of identity."""
    rama_coordinates: tuple[int, ...]
    signature: str
    coord_sum: int
    coord_count: int


@dataclass(frozen=True)
class JivaElements:
    """Elemental composition derived from RAMA coordinates."""
    distribution: dict[str, int]
    dominant: str


@dataclass(frozen=True)
class JivaClassification:
    """Vedic classification — all from the real Mahamantra VM pipeline."""
    guna: str           # VM: guna.mode (SATTVA/RAJAS/TAMAS)
    varna: str          # Derived from dominant element
    quarter: str        # VM: quarter (genesis/dharma/karma/moksha)
    zone: str           # Quarter → city zone
    guardian: str       # VM: guardian (Mahajana)
    position: int       # VM: position (0-15)
    holy_name: str      # VM: holy_name (H/K/R)
    trinity_function: str  # VM: trinity_function (source/maintenance/dissolution)
    chapter: int        # VM: chapter (1-18, Gita chapter)
    chapter_significance: str  # VM: chapter_significance


@dataclass(frozen=True)
class JivaVitals:
    """Life force metrics — from the VM cell system."""
    prana: int          # VM: cell.prana (real cell energy)
    integrity: float    # VM: cell.integrity (0.0 to 1.0)
    is_alive: bool      # VM: cell.is_alive
    diw_raw: int        # VM: diw.raw (19-bit Divine Instruction Word)
    diw_venu: int       # VM: diw.venu (intensity)
    diw_vamsi: int      # VM: diw.vamsi (name-region)
    diw_murali: int     # VM: diw.murali (phase)


@dataclass(frozen=True)
class JivaVibration:
    """Phonetic vibration signature from the VM."""
    seed: int           # VM: vibration.seed
    attractor: int      # VM: vibration.attractor
    element: str        # VM: vibration.signature.element
    varga: int          # VM: vibration.signature.varga
    harmonic: int       # VM: vibration.signature.harmonic
    shruti: bool        # VM: vibration.signature.shruti
    frequency: int      # VM: vibration.signature.frequency


@dataclass(frozen=True)
class Jiva:
    """Complete agent identity — derived entirely from a name via the Mahamantra VM.

    Each Jiva carries a living MahaCellUnified — the biological substrate.
    The cell has prana (energy), integrity (membrane health), lifecycle
    operations (conceive, metabolize, mitosis, apoptosis, homeostasis).
    """
    name: str
    channel: str              # The origin frequency/channel (e.g., 'local', 'moltbook')
    address: int              # MahaCompression seed — deterministic uint32 city address
    seed: JivaSeed
    elements: JivaElements
    classification: JivaClassification
    vitals: JivaVitals
    vibration: JivaVibration
    phonemes: tuple[dict, ...]
    cell: MahaCellUnified     # Living computational unit — THE agent
    vm_result: dict           # Full 27-key VM output for downstream consumers

    def to_dict(self) -> dict:
        """Serialize for JSON storage (Pokedex)."""
        return {
            "name": self.name,
            "channel": self.channel,
            "address": self.address,
            "seed": {
                "rama_coordinates": list(self.seed.rama_coordinates),
                "signature": self.seed.signature,
                "coord_sum": self.seed.coord_sum,
                "coord_count": self.seed.coord_count,
            },
            "elements": {
                "distribution": self.elements.distribution,
                "dominant": self.elements.dominant,
            },
            "classification": {
                "guna": self.classification.guna,
                "varna": self.classification.varna,
                "quarter": self.classification.quarter,
                "zone": self.classification.zone,
                "guardian": self.classification.guardian,
                "position": self.classification.position,
                "holy_name": self.classification.holy_name,
                "trinity_function": self.classification.trinity_function,
                "chapter": self.classification.chapter,
                "chapter_significance": self.classification.chapter_significance,
            },
            "vitals": {
                "prana": self.vitals.prana,
                "integrity": self.vitals.integrity,
                "is_alive": self.vitals.is_alive,
                "diw": {
                    "raw": self.vitals.diw_raw,
                    "venu": self.vitals.diw_venu,
                    "vamsi": self.vitals.diw_vamsi,
                    "murali": self.vitals.diw_murali,
                },
            },
            "vibration": {
                "seed": self.vibration.seed,
                "attractor": self.vibration.attractor,
                "element": self.vibration.element,
                "varga": self.vibration.varga,
                "harmonic": self.vibration.harmonic,
                "shruti": self.vibration.shruti,
                "frequency": self.vibration.frequency,
            },
            "phonemes": list(self.phonemes),
        }


# ── Derivation ───────────────────────────────────────────────────────

def derive_jiva(name: str, channel: str = "local") -> Jiva:
    """Derive complete Jiva identity from a name via the real Mahamantra VM.

    Runs the full 9-step NavaBhakti pipeline:
    SRAVANAM → KIRTANAM → SMARANAM → PADA_SEVANAM → ARCANAM →
    VANDANAM → DASYAM → SAKHYAM → ATMA_NIVEDANAM

    Returns a Jiva with every field sourced from the VM output.
    """
    # Run the REAL VM pipeline
    vm = mahamantra(name)

    # RAMA coordinate encoding (for seed + phoneme detail)
    coords = encode_text(name)
    detail = encode_with_detail(name)
    sig = full_signature(coords) if coords else ""

    # Element distribution from phoneme analysis
    elem_counts: dict[str, int] = {}
    for d in detail:
        e = d.get("element", "unknown")
        elem_counts[e] = elem_counts.get(e, 0) + 1
    dominant = max(elem_counts, key=elem_counts.get) if elem_counts else "unknown"

    coord_sum = sum(coords)
    coord_count = len(coords)

    # Extract VM fields
    guna_mode = vm["guna"]["mode"]
    quarter = vm["quarter"]
    guardian = vm["guardian"]
    position = vm["position"]
    holy_name = vm["holy_name"]
    trinity_function = vm["trinity_function"]
    chapter = vm["chapter"]
    chapter_significance = vm.get("chapter_significance", "")

    diw = vm["diw"]
    cell = vm["cell"]
    vib = vm["vibration"]
    vib_sig = vib["signature"]

    varna = ELEMENT_TO_VARNA.get(vib_sig["element"], "KRIMAYO")
    zone = QUARTER_TO_ZONE.get(quarter, "discovery")

    phonemes = tuple(
        {
            "grapheme": d["grapheme"],
            "phoneme": d["phoneme"],
            "coord": d["rama_coord"],
            "element": d["element"],
            "exact": d["is_exact"],
        }
        for d in detail
    )

    # Create the living MahaCellUnified — the agent's biological substrate
    # MahaCellUnified.from_content() computes the cell's sravanam from the name
    # via MahaCompression, then creates a cell with:
    #   header.sravanam = MahaCompression seed (for cell-level routing)
    #   header.pada_sevanam = position (0-15 in mahamantra)
    #   lifecycle.dna = name (the agent's genetic code)
    maha_cell = MahaCellUnified.from_content(name, register=False)

    # City-level address uses CityAddressBook.resolve() for collision resistance.
    # The cell.header.sravanam is the raw MahaCompression seed (cell-level),
    # while the city address combines compression + SHA-256 for uniqueness.
    from city.addressing import CityAddressBook
    _city_book = CityAddressBook()
    address = _city_book.resolve(name)

    return Jiva(
        name=name,
        channel=channel,
        address=address,
        seed=JivaSeed(
            rama_coordinates=tuple(coords),
            signature=sig,
            coord_sum=coord_sum,
            coord_count=coord_count,
        ),
        elements=JivaElements(distribution=elem_counts, dominant=dominant),
        classification=JivaClassification(
            guna=guna_mode,
            varna=varna,
            quarter=quarter,
            zone=zone,
            guardian=guardian,
            position=position,
            holy_name=holy_name,
            trinity_function=trinity_function,
            chapter=chapter,
            chapter_significance=chapter_significance,
        ),
        vitals=JivaVitals(
            prana=cell["prana"],
            integrity=cell["integrity"],
            is_alive=cell["is_alive"],
            diw_raw=diw["raw"],
            diw_venu=diw["venu"],
            diw_vamsi=diw["vamsi"],
            diw_murali=diw["murali"],
        ),
        vibration=JivaVibration(
            seed=vib["seed"],
            attractor=vib["attractor"],
            element=vib_sig["element"],
            varga=vib_sig["varga"],
            harmonic=vib_sig["harmonic"],
            shruti=vib_sig["shruti"],
            frequency=vib_sig["frequency"],
        ),
        phonemes=phonemes,
        cell=maha_cell,
        vm_result=vm,
    )
