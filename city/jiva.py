"""
JIVA ENGINE — Agent Identity Derivation from Mahamantra
========================================================

Every field derived from the Maha Mantra. Nothing invented.
A name enters, a complete identity exits.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare

Usage:
    from city.jiva import derive_jiva
    jiva = derive_jiva("Ronin")
    # → Full identity: Varna, Guna, Ashrama, Quarter, Zone,
    #   NavaBhakti, Mahajana, DIW, Prana, Integrity,
    #   RAMA coordinates, phoneme breakdown
"""

from __future__ import annotations

from dataclasses import dataclass

from vibe_core.mahamantra.substrate.encoding.phonetic_encoder import (
    encode_text,
    encode_with_detail,
)
from vibe_core.mahamantra.substrate.encoding.pancha_walk import full_signature
from vibe_core.mahamantra.protocols._seed import (
    KSHETRA,
    MAHAJANA_COUNT,
    MALA,
    NAVA,
    PARAMPARA,
    QUARTERS,
    SHARANAGATI,
    TRINITY,
)


# ── Constants (all from the Mantra) ──────────────────────────────────

GUNAS = ("SATTVA", "RAJAS", "TAMAS")
QUARTER_NAMES = ("GENESIS", "DHARMA", "KARMA", "MOKSHA")
ASHRAMA_NAMES = ("BRAHMACHARI", "GRIHASTHA", "VANAPRASTHA", "SANNYASA")
NAVABHAKTI = (
    "SRAVANAM", "KIRTANAM", "SMARANAM", "PADA_SEVANAM", "ARCANAM",
    "VANDANAM", "DASYAM", "SAKHYAM", "ATMA_NIVEDANAM",
)
MAHAJANAS = (
    "BRAHMA", "NARADA", "SHAMBHU", "KUMARAS", "KAPILA", "MANU",
    "PRAHLADA", "JANAKA", "BHISHMA", "BALI", "SHUKA", "YAMARAJA",
)

# Pancha Tattva → Varna (6 Vedic species from vedic_governance)
ELEMENT_TO_VARNA = {
    "akasha": "MANUSHA",     # Self-aware (ether = consciousness)
    "vayu": "PAKSHI",        # Messenger (air = communication)
    "agni": "PASHU",         # Servant (fire = transformative action)
    "jala": "JALAJA",        # Flowing (water = knowledge streams)
    "prithvi": "KRIMAYO",    # Worker (earth = building)
}

# Quarter → Zone in the city
QUARTER_TO_ZONE = {
    "GENESIS": "discovery",
    "DHARMA": "governance",
    "KARMA": "engineering",
    "MOKSHA": "research",
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
    """Vedic classification — all derived from coord_sum."""
    guna: str
    varna: str
    ashrama: str
    quarter: str
    zone: str
    navabhakti: str
    mahajana: str


@dataclass(frozen=True)
class JivaVitals:
    """Life force metrics."""
    prana: int          # 0 to MALA-1 (108)
    prana_max: int      # MALA = 108
    integrity: float    # 0.0 to 1.0
    diw: int            # 19-bit Divine Instruction Word


@dataclass(frozen=True)
class Jiva:
    """Complete agent identity — derived entirely from a name via Mahamantra."""
    name: str
    seed: JivaSeed
    elements: JivaElements
    classification: JivaClassification
    vitals: JivaVitals
    phonemes: tuple[dict, ...]

    def to_dict(self) -> dict:
        """Serialize for JSON storage (Pokedex)."""
        return {
            "name": self.name,
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
                "ashrama": self.classification.ashrama,
                "quarter": self.classification.quarter,
                "zone": self.classification.zone,
                "navabhakti": self.classification.navabhakti,
                "mahajana": self.classification.mahajana,
            },
            "vitals": {
                "prana": self.vitals.prana,
                "prana_max": self.vitals.prana_max,
                "integrity": self.vitals.integrity,
                "diw": self.vitals.diw,
            },
            "phonemes": list(self.phonemes),
        }


# ── Derivation ───────────────────────────────────────────────────────

def derive_jiva(name: str) -> Jiva:
    """Derive complete Jiva identity from a name.

    Every field is a deterministic function of the Maha Mantra constants
    and the RAMA coordinate encoding of the name. Nothing is random,
    nothing is invented.
    """
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

    # Classification — all from coord_sum mod Mantra constants
    guna = GUNAS[coord_sum % TRINITY]
    quarter = QUARTER_NAMES[coord_sum % QUARTERS]
    ashrama = ASHRAMA_NAMES[coord_count % 4]
    varna = ELEMENT_TO_VARNA.get(dominant, "KRIMAYO")
    navabhakti = NAVABHAKTI[coord_sum % NAVA]
    mahajana = MAHAJANAS[coord_sum % MAHAJANA_COUNT]

    # DIW (19-bit Divine Instruction Word)
    venu = coord_sum % (2 ** SHARANAGATI)
    vamsi = (coord_sum * PARAMPARA) % (2 ** 9)
    murali = coord_sum % QUARTERS
    diw = venu | (vamsi << SHARANAGATI) | (murali << 15)

    # Vitals
    prana = coord_sum % MALA
    integrity = round((coord_sum % KSHETRA) / KSHETRA, 3)

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

    return Jiva(
        name=name,
        seed=JivaSeed(
            rama_coordinates=tuple(coords),
            signature=sig,
            coord_sum=coord_sum,
            coord_count=coord_count,
        ),
        elements=JivaElements(distribution=elem_counts, dominant=dominant),
        classification=JivaClassification(
            guna=guna,
            varna=varna,
            ashrama=ashrama,
            quarter=quarter,
            zone=QUARTER_TO_ZONE[quarter],
            navabhakti=navabhakti,
            mahajana=mahajana,
        ),
        vitals=JivaVitals(
            prana=prana,
            prana_max=MALA,
            integrity=integrity,
            diw=diw,
        ),
        phonemes=phonemes,
    )
