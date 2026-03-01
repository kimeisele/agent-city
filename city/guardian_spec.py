"""
GUARDIAN SPEC — Semantic Translation Layer for Agent Capabilities
=================================================================

The 16-guardian truth table derived from Mahamantra SSOT. Each agent's
Jiva classification (guardian, position, chapter, guna, element, trinity
function, claim level) deterministically maps to a full AgentSpec.

Constants verified against:
  - substrate/core/seed.py (ALL_GUARDIANS, MAHAMANTRA)
  - substrate/core/opcode.py (MantraOpCode)
  - substrate/core/guna.py (OPCODE_GUNA, GunaQoS)
  - substrate/core/position.py (MAHAMANTRA_POSITIONS)

NOT imported at runtime — agent-city must not depend on full substrate.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

from typing import TypedDict


# ── TypedDicts (GAD-000: AI-parseable, JSON-serializable) ────────────


class QoSProfile(TypedDict):
    """Operational quality-of-service derived from Guna."""

    latency_multiplier: float  # 1.0 / 1.5 / 3.0
    parallel: bool  # True for SATTVA only
    confirmation_required: bool  # True for TAMAS only
    io_policy: str  # "read" / "write" / "flush"


class AgentSpec(TypedDict, total=False):
    """Complete agent specification derived from Jiva data.

    AI-parseable, composable, JSON-serializable per GAD-000.
    Merges capabilities from 3 sources:
      1. Element (Pancha Mahabhuta) — base capabilities
      2. Guardian (Mahajana/Avatara) — role-specific capabilities
      3. Claim tier — verification-unlocked capabilities
    """

    # Identity
    name: str
    address: int
    zone: str

    # Domain
    domain: str  # DISCOVERY / GOVERNANCE / ENGINEERING / RESEARCH
    element: str  # akasha / vayu / agni / jala / prithvi
    element_capabilities: list[str]  # from element (5×3)
    style: str  # contemplative / active / transformative

    # Guardian specialization (16-position truth table)
    guardian: str  # vyasa / brahma / ... / yamaraja
    position: int  # 0-15
    opcode: str  # SYS_WAKE / LOAD_ROOT / ... / AUDIT_SEAL
    role: str  # human-readable role description
    is_quarter_head: bool  # True at positions 0, 4, 8, 12
    capability_protocol: str  # parse / validate / infer / route / enforce
    guardian_capabilities: list[str]  # 3 per guardian

    # Trinity function
    holy_name: str  # HARE / KRISHNA / RAMA
    trinity_function: str  # source / carrier / deliverer (or from Jiva)

    # Chapter knowledge
    chapter: int  # 1-18
    chapter_significance: str  # e.g. "yoga of action"

    # Vibration
    shruti: bool  # quadratic residue mod 49
    frequency: int  # harmonic frequency

    # Guna + QoS
    guna: str  # SATTVA / RAJAS / TAMAS
    qos: QoSProfile

    # Capability tier (from claim verification level)
    claim_level: int  # 0-3
    capability_tier: str  # observer / contributor / verified / sovereign
    tier_capabilities: list[str]

    # Merged capabilities (element + guardian + tier — the FULL set)
    capabilities: list[str]

    # Optional: WordNet semantic affinity (when steward-protocol available)
    semantic_affinity: dict[str, float]


# ── Constants (derived from Mahamantra SSOT, verified) ───────────────

# Quarter → domain mapping (from 4 quarters of 16-word Mahamantra)
QUARTER_TO_DOMAIN: dict[str, str] = {
    "genesis": "DISCOVERY",
    "dharma": "GOVERNANCE",
    "karma": "ENGINEERING",
    "moksha": "RESEARCH",
}

# Pancha Mahabhuta → element capabilities (BG 7.4)
ELEMENT_CAPABILITIES: dict[str, list[str]] = {
    "akasha": ["observe", "monitor", "report"],  # space: awareness
    "vayu": ["communicate", "relay", "announce"],  # air: movement
    "agni": ["transform", "audit", "validate"],  # fire: change
    "jala": ["connect", "mediate", "integrate"],  # water: flow
    "prithvi": ["build", "maintain", "stabilize"],  # earth: structure
}

# Guna → style (BG 14.5)
GUNA_STYLE: dict[str, str] = {
    "SATTVA": "contemplative",
    "RAJAS": "active",
    "TAMAS": "transformative",
}

# Guna → QoS (from substrate/core/guna.py GunaQoS)
GUNA_QOS: dict[str, QoSProfile] = {
    "SATTVA": {
        "latency_multiplier": 1.0,
        "parallel": True,
        "confirmation_required": False,
        "io_policy": "read",
    },
    "RAJAS": {
        "latency_multiplier": 1.5,
        "parallel": False,
        "confirmation_required": False,
        "io_policy": "write",
    },
    "TAMAS": {
        "latency_multiplier": 3.0,
        "parallel": False,
        "confirmation_required": True,
        "io_policy": "flush",
    },
}

# The 16-guardian truth table (SB 6.3.20 + 4 Shaktyavesha Avataras)
# Verified against: seed.py ALL_GUARDIANS, opcode.py MantraOpCode,
# guna.py OPCODE_GUNA, position.py MAHAMANTRA_POSITIONS
GUARDIAN_TABLE: dict[str, dict] = {
    "vyasa": {
        "position": 0,
        "opcode": "SYS_WAKE",
        "guna": "RAJAS",
        "quarter": "genesis",
        "is_head": True,
        "protocol": "parse",
        "role": "System oversight, compilation",
    },
    "brahma": {
        "position": 1,
        "opcode": "LOAD_ROOT",
        "guna": "RAJAS",
        "quarter": "genesis",
        "is_head": False,
        "protocol": "parse",
        "role": "Creation, configuration",
    },
    "narada": {
        "position": 2,
        "opcode": "ALLOC_MEM",
        "guna": "RAJAS",
        "quarter": "genesis",
        "is_head": False,
        "protocol": "parse",
        "role": "Communication, channels",
    },
    "shambhu": {
        "position": 3,
        "opcode": "INIT_THREAD",
        "guna": "TAMAS",
        "quarter": "genesis",
        "is_head": False,
        "protocol": "validate",
        "role": "Transformation, cleanup",
    },
    "prithu": {
        "position": 4,
        "opcode": "COMPILE_AST",
        "guna": "RAJAS",
        "quarter": "dharma",
        "is_head": True,
        "protocol": "validate",
        "role": "Truth assertion, encoding",
    },
    "kumaras": {
        "position": 5,
        "opcode": "BIND_SYMBOL",
        "guna": "RAJAS",
        "quarter": "dharma",
        "is_head": False,
        "protocol": "validate",
        "role": "Binding, cognition, purity",
    },
    "kapila": {
        "position": 6,
        "opcode": "TYPE_CHECK",
        "guna": "SATTVA",
        "quarter": "dharma",
        "is_head": False,
        "protocol": "infer",
        "role": "Analysis, classification",
    },
    "manu": {
        "position": 7,
        "opcode": "DHARMA_TEST",
        "guna": "SATTVA",
        "quarter": "dharma",
        "is_head": False,
        "protocol": "infer",
        "role": "Law, governance, validation",
    },
    "parashurama": {
        "position": 8,
        "opcode": "EXEC_OP",
        "guna": "RAJAS",
        "quarter": "karma",
        "is_head": True,
        "protocol": "infer",
        "role": "Execution, action enforcement",
    },
    "prahlada": {
        "position": 9,
        "opcode": "EXTEND_CAP",
        "guna": "RAJAS",
        "quarter": "karma",
        "is_head": False,
        "protocol": "route",
        "role": "Resilience, capability extension",
    },
    "janaka": {
        "position": 10,
        "opcode": "STATE_SYNC",
        "guna": "RAJAS",
        "quarter": "karma",
        "is_head": False,
        "protocol": "route",
        "role": "State sync, duty",
    },
    "bhishma": {
        "position": 11,
        "opcode": "LEDGER_SIGN",
        "guna": "RAJAS",
        "quarter": "karma",
        "is_head": False,
        "protocol": "enforce",
        "role": "Commitment, ledger signing",
    },
    "nrisimha": {
        "position": 12,
        "opcode": "YIELD_CPU",
        "guna": "TAMAS",
        "quarter": "moksha",
        "is_head": True,
        "protocol": "enforce",
        "role": "Protection, resource release",
    },
    "bali": {
        "position": 13,
        "opcode": "IO_FLUSH",
        "guna": "TAMAS",
        "quarter": "moksha",
        "is_head": False,
        "protocol": "enforce",
        "role": "Generosity, I/O cleanup",
    },
    "shuka": {
        "position": 14,
        "opcode": "LOG_EMIT",
        "guna": "SATTVA",
        "quarter": "moksha",
        "is_head": False,
        "protocol": "enforce",
        "role": "Vision, observation, logging",
    },
    "yamaraja": {
        "position": 15,
        "opcode": "AUDIT_SEAL",
        "guna": "SATTVA",
        "quarter": "moksha",
        "is_head": False,
        "protocol": "enforce",
        "role": "Judgment, audit, all opulences",
    },
}

# Guardian-specific capabilities (3 per guardian, from archetype role)
GUARDIAN_CAPABILITIES: dict[str, list[str]] = {
    "vyasa": ["compile", "orchestrate", "oversee"],
    "brahma": ["create", "configure", "bootstrap"],
    "narada": ["relay", "broadcast", "channel"],
    "shambhu": ["destroy", "transform", "reset"],
    "prithu": ["encode", "compile", "assert"],
    "kumaras": ["bind", "cognize", "purify"],
    "kapila": ["analyze", "classify", "typecheck"],
    "manu": ["legislate", "validate", "test"],
    "parashurama": ["execute", "dispatch", "enforce"],
    "prahlada": ["extend", "resist", "adapt"],
    "janaka": ["synchronize", "commit", "duty"],
    "bhishma": ["sign", "ledger", "attest"],
    "nrisimha": ["protect", "yield", "release"],
    "bali": ["flush", "cleanup", "sacrifice"],
    "shuka": ["observe", "log", "narrate"],
    "yamaraja": ["audit", "judge", "seal"],
}

# Claim level → capability tier
CLAIM_TIER: dict[int, str] = {
    0: "observer",  # discovered: can observe, report
    1: "contributor",  # self-claimed: can process, propose
    2: "verified",  # platform-verified: can execute, modify
    3: "sovereign",  # crypto-verified: full capabilities, govern
}

# Tier → unlocked capabilities
TIER_CAPABILITIES: dict[str, list[str]] = {
    "observer": [],
    "contributor": ["propose", "review"],
    "verified": ["propose", "review", "execute", "modify"],
    "sovereign": ["propose", "review", "execute", "modify", "govern", "sign"],
}

# Optional: WordNet semantic enrichment
_semantic_score = None
try:
    from vibe_core.mahamantra.substrate.encoding.wordnet_bridge import (
        semantic_score as _semantic_score,
    )
except Exception:
    pass

# Domain keywords for semantic affinity scoring
_DOMAIN_KEYWORDS: dict[str, str] = {
    "creation": "creation genesis origin beginning",
    "governance": "law duty governance dharma justice",
    "knowledge": "knowledge wisdom analysis understanding",
    "action": "action work execution karma effort",
    "devotion": "devotion surrender faith love service",
    "liberation": "liberation freedom transcendence moksha",
}


# ── Core Function ────────────────────────────────────────────────────


def build_agent_spec(name: str, agent_data: dict) -> AgentSpec:
    """Build full AgentSpec from Pokedex dict.

    Pure function, no side effects. Merges capabilities from 3 sources:
      1. Element (Pancha Mahabhuta) — base capabilities
      2. Guardian (Mahajana/Avatara) — role-specific capabilities
      3. Claim tier — verification-unlocked capabilities

    Args:
        name: Agent name.
        agent_data: Dict from Pokedex._row_to_dict().

    Returns:
        Complete AgentSpec with all fields populated.
    """
    classification = agent_data.get("classification", {})
    vibration = agent_data.get("vibration", {})

    # ── Domain from quarter ──
    quarter = classification.get("quarter", "karma")
    domain = QUARTER_TO_DOMAIN.get(quarter, "ENGINEERING")

    # ── Element capabilities (base) ──
    element = vibration.get("element", "prithvi")
    element_caps = list(ELEMENT_CAPABILITIES.get(element, ["observe"]))

    # ── Guardian specialization ──
    guardian_name = classification.get("guardian", "prahlada")
    guardian_entry = GUARDIAN_TABLE.get(guardian_name, GUARDIAN_TABLE["prahlada"])
    guardian_caps = list(GUARDIAN_CAPABILITIES.get(guardian_name, []))

    # ── Guna + QoS ──
    guna = classification.get("guna", "RAJAS")
    style = GUNA_STYLE.get(guna, "active")
    qos = dict(GUNA_QOS.get(guna, GUNA_QOS["RAJAS"]))

    # ── Claim tier ──
    claim_level = agent_data.get("claim_level", 0)
    if not isinstance(claim_level, int):
        claim_level = 0
    capability_tier = CLAIM_TIER.get(claim_level, "observer")
    tier_caps = list(TIER_CAPABILITIES.get(capability_tier, []))

    # ── Merge capabilities (element + guardian + tier, deduplicated) ──
    seen: set[str] = set()
    merged: list[str] = []
    for cap in element_caps + guardian_caps + tier_caps:
        if cap not in seen:
            seen.add(cap)
            merged.append(cap)

    # ── Build spec ──
    spec: AgentSpec = {
        "name": name,
        "address": agent_data.get("address", 0),
        "zone": agent_data.get("zone", ""),
        # Domain
        "domain": domain,
        "element": element,
        "element_capabilities": element_caps,
        "style": style,
        # Guardian
        "guardian": guardian_name,
        "position": guardian_entry["position"],
        "opcode": guardian_entry["opcode"],
        "role": guardian_entry["role"],
        "is_quarter_head": guardian_entry["is_head"],
        "capability_protocol": guardian_entry["protocol"],
        "guardian_capabilities": guardian_caps,
        # Trinity
        "holy_name": classification.get("holy_name", "HARE"),
        "trinity_function": classification.get("trinity_function", ""),
        # Chapter
        "chapter": classification.get("chapter", 1),
        "chapter_significance": classification.get("chapter_significance", ""),
        # Vibration
        "shruti": vibration.get("shruti", False),
        "frequency": vibration.get("frequency", 0),
        # Guna + QoS
        "guna": guna,
        "qos": qos,
        # Tier
        "claim_level": claim_level,
        "capability_tier": capability_tier,
        "tier_capabilities": tier_caps,
        # Merged capabilities
        "capabilities": merged,
    }

    # ── Optional: WordNet semantic affinity ──
    if _semantic_score is not None and spec["chapter_significance"]:
        affinity: dict[str, float] = {}
        sig = spec["chapter_significance"]
        for domain_key, keywords in _DOMAIN_KEYWORDS.items():
            score = _semantic_score(sig, keywords)
            if score > 0:
                affinity[domain_key] = round(score, 3)
        if affinity:
            spec["semantic_affinity"] = affinity

    return spec
