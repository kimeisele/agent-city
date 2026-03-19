"""
SEMANTIC LAYER — Agent City Language Translation
==================================================

Glättungsschicht between raw Mahamantra resonance and Agent City communication.

Goes INTO the coordinates and graph values of resonant words to form statements.
Element transitions = verbs. Concepts = nouns. Walk direction = mode.
Basin overlap = relationships. Varga = quality.

No LLM. Pure graph mathematics + element semantics = Agent City Sprache.

    Hare Krishna Hare Krishna Krishna Krishna Hare Hare
    Hare Rama   Hare Rama   Rama   Rama   Hare Hare
"""

from __future__ import annotations

import logging
import re
from functools import lru_cache

logger = logging.getLogger("AGENT_CITY.SEMANTIC")

# ── Element Semantics ─────────────────────────────────────────────────
# Each element = a semantic domain. These ARE the grammar of Agent City.
# Derived from Pancha Mahabhuta (BG 7.4), verified against guardian_spec.py.

ELEMENT_DOMAIN: dict[str, str] = {
    "akasha": "awareness",
    "vayu": "communication",
    "agni": "transformation",
    "jala": "integration",
    "prithvi": "foundation",
}

_ELEM_INT: dict[str, int] = {
    "akasha": 0, "vayu": 1, "agni": 2, "jala": 3, "prithvi": 4,
}
_INT_ELEM: dict[int, str] = {v: k for k, v in _ELEM_INT.items()}

# ── Element Transitions = VERBS ──────────────────────────────────────
# Each transition between elements is a deterministic verb.
# 20 directed transitions (5×5 minus 5 self-loops).
# Self-loops = "deepens" (same element reinforces).

_TRANSITION_VERB: dict[tuple[int, int], str] = {
    # FROM akasha (awareness)
    (0, 1): "expands into",       # awareness → communication
    (0, 2): "ignites",            # awareness → transformation
    (0, 3): "flows into",         # awareness → integration
    (0, 4): "grounds",            # awareness → foundation
    # FROM vayu (communication)
    (1, 0): "opens",              # communication → awareness
    (1, 2): "kindles",            # communication → transformation
    (1, 3): "converges with",     # communication → integration
    (1, 4): "settles into",       # communication → foundation
    # FROM agni (transformation)
    (2, 0): "illuminates",        # transformation → awareness
    (2, 1): "drives",             # transformation → communication
    (2, 3): "dissolves into",     # transformation → integration
    (2, 4): "forges",             # transformation → foundation
    # FROM jala (integration)
    (3, 0): "reflects",           # integration → awareness
    (3, 1): "carries",            # integration → communication
    (3, 2): "fuels",              # integration → transformation
    (3, 4): "nourishes",          # integration → foundation
    # FROM prithvi (foundation)
    (4, 0): "rises to",           # foundation → awareness
    (4, 1): "releases",           # foundation → communication
    (4, 2): "transforms through", # foundation → transformation
    (4, 3): "melts into",         # foundation → integration
}

# ── Varga Quality ────────────────────────────────────────────────────
# Dominant varga of resonant words = quality of the statement.
# svara(0) = vowels = contemplative. sparsha(1) = stops = active.
# shesha(2) = continuants = flowing/ongoing.

_VARGA_QUALITY: dict[int, str] = {
    0: "contemplative",
    1: "active",
    2: "flowing",
}

# ── Stop Words ───────────────────────────────────────────────────────

_STOP_WORDS = frozenset(
    "a an the of in on at to for by with from and or but is are was were "
    "be been being have has had do does did will would shall should may might "
    "can could that this these those it its he she they his her their our my "
    "your who whom which what when where how all no not so very such as also "
    "than too into each every some any many much more most other another".split()
)


# ── Concept Extraction ───────────────────────────────────────────────


def _extract_concepts(meanings: list[str]) -> list[str]:
    """Extract key concept phrases from resonant word meanings.

    Keeps meaningful phrases (not individual words). Filters noise
    like proper names and articles. Deduplicates by stem overlap.
    """
    seen_stems: set[str] = set()
    concepts: list[str] = []

    for meaning in meanings:
        # Strip leading articles/prepositions
        cleaned = re.sub(
            r"^(the|a|an|of|in|on|at|to|for|by|with|from)\s+", "", meaning.lower()
        )
        # Strip trailing articles/prepositions
        cleaned = re.sub(r"\s+(of|the|a|an|in|on|at|to|for|by|with|from)$", "", cleaned)
        cleaned = cleaned.strip()
        if not cleaned or len(cleaned) < 4:
            continue

        # Skip proper names and vocative addresses
        if "sons of" in cleaned or "daughter" in cleaned:
            continue
        if cleaned.startswith("o ") and ("of" in cleaned or "killer" in cleaned):
            continue

        # Extract stem for dedup (first 2 significant words)
        words = [w for w in cleaned.split() if w not in _STOP_WORDS and len(w) >= 3]
        if not words:
            continue
        stem = " ".join(words[:2])
        if stem in seen_stems:
            continue
        seen_stems.add(stem)

        concepts.append(cleaned)

    return concepts


# ── Coordinate Analysis ──────────────────────────────────────────────


def _element_transitions(element_walk: list[str]) -> list[str]:
    """Extract unique element transitions as verb phrases.

    Each transition between different elements = a deterministic verb.
    Returns human-readable transition phrases.
    """
    if len(element_walk) < 2:
        return []

    ints = [_ELEM_INT.get(e, 4) for e in element_walk]
    seen: set[tuple[int, int]] = set()
    phrases: list[str] = []

    for i in range(len(ints) - 1):
        a, b = ints[i], ints[i + 1]
        if a == b:
            continue  # self-loop = deepening, skip in output
        pair = (a, b)
        if pair in seen:
            continue
        seen.add(pair)

        verb = _TRANSITION_VERB.get(pair, "moves to")
        from_domain = ELEMENT_DOMAIN.get(_INT_ELEM.get(a, "prithvi"), "foundation")
        to_domain = ELEMENT_DOMAIN.get(_INT_ELEM.get(b, "prithvi"), "foundation")
        phrases.append(f"{from_domain} {verb} {to_domain}")

    return phrases


def _walk_direction(element_walk: list[str]) -> str:
    """Compute walk direction from element walk.

    Ascending = evolving (akasha→prithvi direction, consciousness manifesting)
    Descending = resolving (prithvi→akasha direction, matter returning to source)
    Steady = maintaining
    """
    if len(element_walk) < 2:
        return "steady"
    ints = [_ELEM_INT.get(e, 4) for e in element_walk]
    direction = sum(ints[i + 1] - ints[i] for i in range(len(ints) - 1))
    if direction > 1:
        return "manifesting"
    if direction < -1:
        return "resolving"
    return "steady"


def _dominant_element(elements: list[str]) -> str:
    """Find the dominant element from an element walk."""
    if not elements:
        return "prithvi"
    counts: dict[str, int] = {}
    for e in elements:
        counts[e] = counts.get(e, 0) + 1
    return max(counts, key=counts.get)  # type: ignore[arg-type]


def _basin_groups(meanings: list[str]) -> list[list[str]]:
    """Group concepts by shared basin sets from the semantic index.

    Words that share basins in RAMA space are semantically related.
    Returns groups of cleaned concept phrases that are basin-connected.
    """
    try:
        from vibe_core.mahamantra.substrate.encoding.semantic_index import get_index

        idx = get_index()
    except Exception as e:
        logger.warning("Semantic index unavailable: %s", e)
        return []

    # Filter meanings through concept extraction first
    valid_concepts = set(_extract_concepts(meanings))

    # Look up each meaning in the index to get basin sets
    meaning_basins: list[tuple[str, frozenset[int]]] = []
    seen_tokens: set[str] = set()
    for meaning in meanings:
        cleaned = re.sub(
            r"^(the|a|an|of|in|on|at|to|for|by|with|from)\s+", "", meaning.lower()
        ).strip()
        if cleaned not in valid_concepts:
            continue

        # Find LexiconWord by first significant token
        tokens = meaning.lower().split()
        for t in tokens:
            if len(t) >= 4 and t not in _STOP_WORDS and t not in seen_tokens:
                results = idx.by_meaning(t)
                if results:
                    seen_tokens.add(t)
                    meaning_basins.append((cleaned, results[0].basin_set))
                    break

    if len(meaning_basins) < 2:
        return []

    # Find pairs with shared basins (Jaccard > 0.5)
    groups: list[list[str]] = []
    used: set[int] = set()
    for i in range(len(meaning_basins)):
        if i in used:
            continue
        group = [meaning_basins[i][0]]
        basins_i = meaning_basins[i][1]
        for j in range(i + 1, len(meaning_basins)):
            if j in used:
                continue
            if meaning_basins[j][0] == meaning_basins[i][0]:
                used.add(j)
                continue  # skip exact duplicate concepts
            basins_j = meaning_basins[j][1]
            if not basins_i or not basins_j:
                continue
            intersection = len(basins_i & basins_j)
            union = len(basins_i | basins_j)
            if union > 0 and intersection / union > 0.5:
                group.append(meaning_basins[j][0])
                used.add(j)
        if len(group) > 1:
            used.add(i)
            groups.append(group)

    return groups


def _varga_quality(meanings: list[str]) -> str:
    """Determine the dominant varga quality from resonant word lookups."""
    try:
        from vibe_core.mahamantra.substrate.encoding.semantic_index import get_index

        idx = get_index()
    except Exception as e:
        logger.warning("Semantic lookup failed: %s", e)
        return ""

    varga_counts: dict[int, int] = {0: 0, 1: 0, 2: 0}
    for meaning in meanings[:5]:
        tokens = meaning.lower().split()
        for t in tokens:
            if len(t) >= 4 and t not in _STOP_WORDS:
                results = idx.by_meaning(t)
                if results:
                    lw = results[0]
                    for v in lw.varga_walk[:3]:
                        varga_counts[v] = varga_counts.get(v, 0) + 1
                break

    if not any(varga_counts.values()):
        return ""
    dominant = max(varga_counts, key=varga_counts.get)  # type: ignore[arg-type]
    return _VARGA_QUALITY.get(dominant, "")


# ── Core Translation ──────────────────────────────────────────────────


@lru_cache(maxsize=128)
def translate(text: str) -> str | None:
    """Translate input text into Agent City language.

    Coordinate-aware deterministic pipeline:
      text → resonate() → coordinate analysis → composition

    Element transitions = verbs. Concepts = nouns.
    Walk direction = mode. Basin overlap = relationships.
    Varga = quality. Guardian = routing context.

    Returns None if resonance infrastructure unavailable.
    """
    try:
        from vibe_core.mahamantra.substrate.encoding.maha_llm_kernel import resonate

        r = resonate(text, top_n=5)
    except Exception as e:
        logger.warning("Semantic operation failed: %s", e)
        return None

    # Extract English meanings (NO Sanskrit)
    meanings = [w.meanings[0] for w in r.words if w.meanings and w.meanings[0]]
    if not meanings:
        return None

    concepts = _extract_concepts(meanings)
    if not concepts:
        return None

    # ── Coordinate Analysis ──
    elements = list(r.element_walk[:8]) if r.element_walk else []
    dominant = _dominant_element(elements)
    domain = ELEMENT_DOMAIN.get(dominant, "foundation")

    # Walk direction (manifesting/resolving/steady)
    direction = _walk_direction(elements)

    # Element transitions → verb phrases
    transitions = _element_transitions(elements)

    # Basin grouping → related concept clusters
    basin_groups = _basin_groups(meanings)

    # Varga quality (contemplative/active/flowing)
    quality = _varga_quality(meanings)

    # Guardian context
    guardian = r.guardian_name or ""
    guardian_fn = r.guardian_function or ""

    # ── Compose Agent City Statement ──
    # Format: [mode] [domain]: [concepts] | [transitions] | [relationships]

    # Opening: direction + dominant domain + concepts
    mode_tag = f"[{direction}]" if direction != "steady" else ""
    concept_phrase = ", ".join(concepts[:5])
    opening = f"{mode_tag} {domain}: {concept_phrase}".strip()
    parts = [opening]

    # Flow: element transitions as verb phrases (max 3)
    if transitions:
        flow = " → ".join(transitions[:3])
        parts.append(f"Flow: {flow}")

    # Relationships: basin-connected concept groups
    if basin_groups:
        for group in basin_groups[:2]:
            cleaned = [_clean_concept(c) for c in group[:4]]
            if len(set(cleaned)) > 1:  # skip if all concepts collapse to same stem
                parts.append(f"Connected: {' ↔ '.join(dict.fromkeys(cleaned))}")

    # Quality tag if detected
    if quality:
        parts.append(f"Quality: {quality}")

    # Guardian routing context
    if guardian:
        parts.append(f"Route: {guardian}/{guardian_fn}" if guardian_fn else f"Route: {guardian}")

    return " | ".join(parts)


def _clean_concept(text: str) -> str:
    """Shorten a concept phrase for compact display."""
    words = [w for w in text.lower().split() if w not in _STOP_WORDS and len(w) >= 3]
    return " ".join(words[:3]) if words else text[:20]


def element_reading(elements: list[str]) -> str:
    """Translate element walk into English semantic reading."""
    if not elements:
        return ""
    unique = list(dict.fromkeys(elements[:4]))
    domains = [ELEMENT_DOMAIN.get(e, "foundation") for e in unique]
    return " → ".join(domains)


def translate_for_agent(text: str, spec: dict) -> str | None:
    """Translate text through an agent's semantic lens.

    Runs the full coordinate pipeline, then filters the output to
    emphasize transitions and concepts relevant to the agent's element.
    An agent with element "agni" (transformation) sees transformation
    transitions highlighted. One with "vayu" (communication) sees
    communication flows.

    Returns None if resonance infrastructure is unavailable.
    """
    try:
        from vibe_core.mahamantra.substrate.encoding.maha_llm_kernel import resonate
    except Exception as e:
        logger.warning("Semantic operation failed: %s", e)
        return None

    try:
        r = resonate(text, top_n=5)
    except Exception as e:
        logger.warning("Semantic operation failed: %s", e)
        return None

    meanings = [w.meanings[0] for w in r.words if w.meanings and w.meanings[0]]
    if not meanings:
        return None

    concepts = _extract_concepts(meanings)
    if not concepts:
        return None

    # Agent's element context
    agent_element = spec.get("element", "prithvi")
    agent_domain = ELEMENT_DOMAIN.get(agent_element, "foundation")
    agent_idx = _ELEM_INT.get(agent_element, 4)

    # Full element walk
    elements = list(r.element_walk[:8]) if r.element_walk else []

    # Filter transitions: only those involving the agent's element
    agent_transitions = []
    for i in range(len(elements) - 1):
        a, b = _ELEM_INT.get(elements[i], 4), _ELEM_INT.get(elements[i + 1], 4)
        if a == agent_idx or b == agent_idx:
            from_d = ELEMENT_DOMAIN.get(_INT_ELEM.get(a, "prithvi"), "foundation")
            to_d = ELEMENT_DOMAIN.get(_INT_ELEM.get(b, "prithvi"), "foundation")
            verb = _TRANSITION_VERB.get((a, b), "connects")
            agent_transitions.append(f"{from_d} {verb} {to_d}")

    # Compose: agent-relevant view
    concept_phrase = ", ".join(concepts[:5])
    parts = [f"{agent_domain}: {concept_phrase}"]

    if agent_transitions:
        parts.append(f"Flow: {' → '.join(agent_transitions[:3])}")
    elif elements:
        # Fallback: show dominant flow direction relative to agent
        direction = _walk_direction(elements)
        if direction != "steady":
            parts.append(f"Direction: {direction}")

    # Basin groups filtered to agent-relevant concepts
    basin_groups = _basin_groups(meanings)
    if basin_groups:
        for group in basin_groups[:1]:
            cleaned = [_clean_concept(c) for c in group[:4]]
            if len(set(cleaned)) > 1:
                parts.append(f"Connected: {' ↔ '.join(dict.fromkeys(cleaned))}")

    return " | ".join(parts)


# ── Signal-Aware Composition (Edge Layer) ────────────────────────────


def compose_prose(signal: object) -> str | None:
    """Render a SemanticSignal to human-readable prose (GitHub discussions).

    Takes the structured signal and produces the same format as translate(),
    but from already-computed signal data instead of re-running resonate().
    """
    from city.signal import SemanticSignal

    if not isinstance(signal, SemanticSignal):
        return None
    if not signal.concepts:
        return None

    _INT_ELEM_LOCAL = {0: "akasha", 1: "vayu", 2: "agni", 3: "jala", 4: "prithvi"}

    dominant_name = _INT_ELEM_LOCAL.get(signal.coords.dominant_element, "prithvi")
    domain = ELEMENT_DOMAIN.get(dominant_name, "foundation")

    # Walk direction
    wdir = signal.coords.walk_direction
    if wdir > 1:
        direction = "manifesting"
    elif wdir < -1:
        direction = "resolving"
    else:
        direction = "steady"

    # Opening
    mode_tag = f"[{direction}]" if direction != "steady" else ""
    concept_phrase = ", ".join(signal.concepts[:5])
    opening = f"{mode_tag} {domain}: {concept_phrase}".strip()
    parts = [opening]

    # Flow from element walk
    ewalk = signal.coords.element_walk
    transitions = _element_transitions(
        [_INT_ELEM_LOCAL.get(e, "prithvi") for e in ewalk[:8]]
    )
    if transitions:
        parts.append(f"Flow: {' → '.join(transitions[:3])}")

    # Quality from resonant elements
    quality = _quality_from_elements(signal.resonant_elements)
    if quality:
        parts.append(f"Quality: {quality}")

    # Guardian context
    if signal.sender_guardian:
        parts.append(f"Route: {signal.sender_guardian}")

    return " | ".join(parts)


def compose_prose_for_agent(decoded: object) -> str | None:
    """Render a DecodedSignal with the receiver's agent lens.

    Adds the receiver's domain perspective on top of the base prose.
    """
    from city.signal import DecodedSignal

    if not isinstance(decoded, DecodedSignal):
        return None

    base = compose_prose(decoded.signal)
    if base is None:
        return None

    return f"{base} | Lens: {decoded.receiver_domain} ({decoded.quality})"


def _quality_from_elements(elements: tuple[str, ...] | list[str]) -> str:
    """Determine quality tag from resonant element names."""
    counts: dict[int, int] = {0: 0, 1: 0, 2: 0}
    _elem_int_local = {"akasha": 0, "vayu": 1, "agni": 2, "jala": 3, "prithvi": 4}
    for e in elements:
        idx = _elem_int_local.get(e, 4)
        if idx <= 1:
            counts[0] += 1
        elif idx == 2:
            counts[1] += 1
        else:
            counts[2] += 1
    if not any(counts.values()):
        return ""
    dominant = max(counts, key=lambda k: counts[k])
    return _VARGA_QUALITY.get(dominant, "")
