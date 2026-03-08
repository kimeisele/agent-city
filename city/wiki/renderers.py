from __future__ import annotations

import json
import subprocess
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path


def render_world_home(page: dict, context: dict, entity: dict | None = None) -> dict:
    agents = _load_agents(context["root"])
    city_state = _load_json(context["root"] / "data/city_state.json")
    mayor_state = _load_json(context["root"] / "data/mayor_state.json")
    intro = _read_optional(context["root"] / "wiki-src/pages/Home.md")
    top = sorted(agents, key=lambda item: int(item.get("prana", 0)), reverse=True)[:10]
    table = ["## Verified Registry", "| Agent | Status | Prana |", "| :--- | :--- | ---: |"]
    table.extend(f"| [{a['name']}](Agent--{a['slug']}) | {a['status']} | {a['prana']} |" for a in top)
    return {
        "page_meta": f"Generated world home for `{context['origin_id']}`.",
        "world_status": "\n".join([
            intro.strip(),
            "",
            f"- Founded: `{city_state.get('founded', 'unknown')}`",
            f"- Heartbeats observed: `{mayor_state.get('heartbeat_count', 0)}`",
            f"- Last census: `{city_state.get('last_census') or 'unknown'}`",
        ]).strip(),
        "official_registry": "\n".join(table),
        "provenance": _provenance(page, context),
    }


def render_world_map(page: dict, context: dict, entity: dict | None = None) -> str:
    sources = _source_paths(page)
    phases = _phase_names(context["root"])
    service_names = _service_names()
    federation = _federation_summary(context["root"])
    lines = [
        "A live projection of Agent City's main world structure.",
        "",
        "```mermaid",
        "flowchart TD",
        "  Home[World Home] --> Mayor[Mayor Kernel]",
        f"  Mayor --> Phases[{ ' / '.join(phases) }]",
        "  Mayor --> Runtime[City Runtime]",
        f"  Runtime --> Registry[Registry + Pokedex ({len(_load_agents(context['root']))} agents)]",
        f"  Runtime --> Services[Service Mesh ({len(service_names)} services)]",
        f"  Runtime --> Federation[Federation / Nadi ({federation['reports_count']} reports)]",
        "  Federation --> Mothership[Steward Protocol / External Nodes]",
        "```",
        "",
        "## Topology Summary",
        f"- Phases: `{', '.join(phases)}`",
        f"- Registered service types: `{len(service_names)}`",
        f"- Archived federation reports: `{federation['reports_count']}`",
        f"- Pending directives: `{federation['directives_pending']}`",
        f"- Nadi outbox messages on disk: `{federation['outbox_on_disk']}`",
        "",
        "## Source Anchors",
    ]
    lines.extend(f"- `{path}`" for path in sources)
    lines.extend(["", _provenance(page, context)])
    return "\n".join(lines)


def render_doc_projection(page: dict, context: dict, entity: dict | None = None) -> str:
    paths = [context["root"] / source["path"] for source in page.get("sources", []) if source["kind"] in {"authored", "doc"}]
    primary = next((path for path in paths if path.exists()), None)
    body = _read_optional(primary) if primary else ""
    extra = [f"- `{source['path']}`" for source in page.get("sources", [])[1:]]
    if extra:
        body = f"{body.rstrip()}\n\n## Source Anchors\n" + "\n".join(extra)
    return body.rstrip() + "\n\n" + _provenance(page, context)


def render_registry_agents(page: dict, context: dict, entity: dict | None = None) -> str:
    agents = sorted(_load_agents(context["root"]), key=lambda item: item["name"].lower())
    status_counts = Counter(agent["status"] for agent in agents)
    role_counts = Counter(agent["role"] for agent in agents)
    verified_count = sum(1 for agent in agents if agent.get("oath_hash"))
    recent = sorted(agents, key=lambda item: item["name"].lower())[:12]
    lines = [
        f"Total agents discovered: **{len(agents)}**",
        f"- Verified oath-bearing agents: **{verified_count}**",
        "",
        "## Status Breakdown",
    ]
    lines.extend(f"- `{status}`: **{count}**" for status, count in sorted(status_counts.items()))
    lines.extend(["", "## Role Breakdown"])
    lines.extend(f"- `{role}`: **{count}**" for role, count in sorted(role_counts.items()))
    lines.extend(["", "## Registry Table", "| Agent | Status | Role | Prana | Verified |", "| :--- | :--- | :--- | ---: | :--- |"])
    lines.extend(
        f"| [{a['name']}](Agent--{a['slug']}) | {a['status']} | {a['role']} | {a['prana']} | {'yes' if a.get('oath_hash') else 'no'} |"
        for a in agents[:200]
    )
    lines.extend(["", "## First Alphabetical Slice"])
    lines.extend(f"- [{agent['name']}](Agent--{agent['slug']}) — `{agent['status']}` / `{agent['role']}`" for agent in recent)
    lines.extend(["", _provenance(page, context)])
    return "\n".join(lines)


def render_runtime_state(page: dict, context: dict, entity: dict | None = None) -> str:
    city_state = _load_json(context["root"] / "data/city_state.json")
    mayor_state = _load_json(context["root"] / "data/mayor_state.json")
    federation = _federation_summary(context["root"])
    lines = [
        "## Runtime Snapshot",
        f"- Founded: `{city_state.get('founded', 'unknown')}`",
        f"- Mayor heartbeats: `{city_state.get('mayor_heartbeat_count', 0)}`",
        f"- Mayor persisted heartbeat count: `{mayor_state.get('heartbeat_count', 0)}`",
        f"- Total governance actions: `{mayor_state.get('total_governance_actions', 0)}`",
        f"- Total operations: `{mayor_state.get('total_operations', 0)}`",
        f"- Last heartbeat epoch: `{mayor_state.get('last_heartbeat', 'unknown')}`",
        "",
        "## Federation Runtime",
        f"- Reports archived: `{federation['reports_count']}`",
        f"- Pending directives: `{federation['directives_pending']}`",
        f"- Nadi outbox messages on disk: `{federation['outbox_on_disk']}`",
        f"- Nadi inbox messages on disk: `{federation['inbox_on_disk']}`",
        f"- Latest report heartbeat: `{federation['latest_report_heartbeat']}`",
        "",
        _provenance(page, context),
    ]
    return "\n".join(lines)


def render_federation_overview(page: dict, context: dict, entity: dict | None = None) -> str:
    federation = _federation_summary(context["root"])
    latest = federation["latest_report"]
    lines = [
        "## Federation Surface",
        "Agent City exchanges directives and reports through a file-backed federation membrane and Nadi bridge.",
        "",
        f"- Reports archived: `{federation['reports_count']}`",
        f"- Pending directives: `{federation['directives_pending']}`",
        f"- Processed directives: `{federation['directives_done']}`",
        f"- Outbox messages on disk: `{federation['outbox_on_disk']}`",
        f"- Inbox messages on disk: `{federation['inbox_on_disk']}`",
        "",
        "## Latest Report",
        f"- Heartbeat: `{federation['latest_report_heartbeat']}`",
        f"- Population: `{latest.get('population', 0) if latest else 0}`",
        f"- Chain valid: `{latest.get('chain_valid', False) if latest else False}`",
        f"- Active missions: `{len(latest.get('mission_results', [])) if latest else 0}`",
        "",
        "## Source Anchors",
        "- `city/federation.py`",
        "- `city/federation_nadi.py`",
        "- `data/federation/`",
        "",
        _provenance(page, context),
    ]
    return "\n".join(lines)


def render_runtime_active_bridges(page: dict, context: dict, entity: dict | None = None) -> str:
    federation = _federation_summary(context["root"])
    latest = federation["latest_report"]
    missions = latest.get("mission_results", []) if latest else []
    lines = [
        "## Active Bridges",
        "The runtime currently exposes its outward traffic primarily through federation reports and Nadi message files.",
        "",
        "| Bridge | Signal | Current Value |",
        "| :--- | :--- | ---: |",
        f"| Federation relay | Archived reports | {federation['reports_count']} |",
        f"| Federation relay | Pending directives | {federation['directives_pending']} |",
        f"| Federation Nadi | Outbox messages | {federation['outbox_on_disk']} |",
        f"| Federation Nadi | Inbox messages | {federation['inbox_on_disk']} |",
    ]
    if missions:
        lines.extend(["", "## Active Mission Echoes"])
        lines.extend(f"- `{mission.get('id', 'unknown')}` — {mission.get('name', 'Unnamed mission')} ({mission.get('status', 'unknown')})" for mission in missions)
    lines.extend(["", _provenance(page, context)])
    return "\n".join(lines)


def render_agent_page(page: dict, context: dict, entity: dict | None = None) -> dict:
    assert entity is not None
    verification = "CONSTITUTIONAL_OATH_SIGNED" if entity.get("oath_hash") else "UNVERIFIED_DISCOVERY"
    return {
        "page_meta": f"Agent page materialized from `data/agents/{entity['slug']}`.",
        "official_identity": "\n".join([
            f"## Official City Record: {entity['name']}",
            f"- Address: `{entity.get('address', 'unknown')}`",
            f"- Status: `{entity.get('status', 'unknown')}`",
            f"- Role: `{entity.get('role', 'citizen')}`",
            f"- Prana: `{entity.get('prana', 0)}`",
            f"- Verification: `{verification}`",
        ]),
        "provenance": _provenance(page, context, entity_slug=entity["slug"]),
    }


def render_sidebar(page: dict, context: dict, entity: dict | None = None) -> str:
    entries = []
    for section in context["manifest"]["navigation"]["section_order"]:
        section_pages = [p for p in context["manifest"]["pages"] if p.get("section") == section and p.get("visibility", "listed") != "hidden" and "wiki_name" in p]
        if not section_pages:
            continue
        entries.append(f"## {section}")
        entries.extend(f"- [[{p['wiki_name']}|{p['title']}]]" for p in section_pages)
        entries.append("")
    return "\n".join(entries).strip() + "\n"


def render_footer(page: dict, context: dict, entity: dict | None = None) -> str:
    return f"Generated by Agent City World Compiler from `{context['source_sha']}` at `{context['generated_at']}` for `{context['origin_id']}`."


def render_ledger_recent_changes(page: dict, context: dict, entity: dict | None = None) -> str:
    try:
        output = subprocess.check_output(["git", "log", "--oneline", "-n", "10"], cwd=context["root"], text=True)
    except Exception:
        output = "history unavailable"
    return "## Recent Changes\n\n" + "\n".join(f"- `{line}`" for line in output.splitlines() if line.strip()) + "\n\n" + _provenance(page, context)


def _load_agents(root: Path) -> list[dict]:
    agents = []
    for agent_dir in sorted((root / "data/agents").iterdir() if (root / "data/agents").exists() else []):
        if not agent_dir.is_dir():
            continue
        manifest = _load_json(agent_dir / "manifest.json")
        cell = _load_json(agent_dir / "cell.json")
        identity = _load_json(agent_dir / "identity.json")
        agents.append({
            "name": manifest.get("name", agent_dir.name),
            "slug": agent_dir.name,
            "address": manifest.get("address", agent_dir.name),
            "status": manifest.get("status", "unknown"),
            "role": manifest.get("role", "citizen"),
            "prana": cell.get("prana", 0),
            "oath_hash": identity.get("oath_hash"),
        })
    return agents


def _phase_names(root: Path) -> list[str]:
    phases_dir = root / "city/phases"
    return [path.stem.upper() for path in sorted(phases_dir.glob("*.py")) if path.stem != "__init__"]


def _service_names() -> list[str]:
    import city.registry as registry

    return sorted(getattr(registry, name) for name in dir(registry) if name.startswith("SVC_"))


def _federation_summary(root: Path) -> dict:
    federation_dir = root / "data/federation"
    reports = sorted((federation_dir / "reports").glob("report_*.json")) if (federation_dir / "reports").exists() else []
    latest_report = _load_json(reports[-1]) if reports else {}
    outbox = _load_json(federation_dir / "nadi_outbox.json")
    inbox = _load_json(federation_dir / "nadi_inbox.json")
    directives_dir = federation_dir / "directives"
    pending = list(directives_dir.glob("*.json")) if directives_dir.exists() else []
    done = list(directives_dir.glob("*.done")) + list(directives_dir.glob("*.done.json")) if directives_dir.exists() else []
    return {
        "reports_count": len(reports),
        "latest_report": latest_report,
        "latest_report_heartbeat": latest_report.get("heartbeat", "none") if latest_report else "none",
        "outbox_on_disk": len(outbox) if isinstance(outbox, list) else 0,
        "inbox_on_disk": len(inbox) if isinstance(inbox, list) else 0,
        "directives_pending": len([path for path in pending if not path.name.endswith(".done.json")]),
        "directives_done": len(done),
    }


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text()) if path.exists() else {}


def _read_optional(path: Path | None) -> str:
    return path.read_text() if path and path.exists() else ""


def _source_paths(page: dict) -> list[str]:
    return [str(source.get("path")) for source in page.get("sources", []) if source.get("path")]


def _provenance(page: dict, context: dict, **extra: str) -> str:
    fields = {
        "Generated-At": context["generated_at"],
        "Source-SHA": context["source_sha"],
        "Origin-ID": context["origin_id"],
        "Page-ID": page.get("id", "unknown"),
    }
    fields.update({key.replace("_", "-").title(): value for key, value in extra.items()})
    return "\n".join(["## Provenance", *[f"- **{key}**: `{value}`" for key, value in fields.items()]])


def compiler_context(root: Path, manifest: dict) -> dict:
    try:
        source_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    except Exception:
        source_sha = "unknown"
    return {
        "root": root,
        "manifest": manifest,
        "generated_at": datetime.now(UTC).isoformat(),
        "origin_id": manifest["world"]["origin_id"],
        "source_sha": source_sha,
    }
