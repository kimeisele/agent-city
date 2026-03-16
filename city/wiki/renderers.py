from __future__ import annotations

import json
import os
import shutil
import subprocess
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from city.wiki.repo_graph_client import (
    load_mothership_repo_graph_context,
    load_mothership_repo_graph_neighbors,
    load_mothership_repo_graph_snapshot,
)


def render_world_home(page: dict, context: dict, entity: dict | None = None) -> dict:
    agents = _load_agents(context["root"])
    city_state = _load_json(context["root"] / "data/city_state.json")
    mayor_state = _load_json(context["root"] / "data/mayor_state.json")
    intro = _read_optional(context["root"] / "wiki-src/pages/Home.md")
    top = sorted(agents, key=lambda item: int(item.get("prana", 0)), reverse=True)[:10]
    table = ["## Verified Registry", "| Agent | Status | Prana |", "| :--- | :--- | ---: |"]
    table.extend(
        f"| [{a['name']}](Agent--{a['slug']}) | {a['status']} | {a['prana']} |"
        for a in top
    )
    return {
        "page_meta": f"Generated city home for `{context['origin_id']}`.",
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
    mothership = load_mothership_repo_graph_snapshot(context["root"], limit=5)
    lines = [
        "A live projection of Agent City's main city structure.",
        "",
        "```mermaid",
        "flowchart TD",
        "  Home[City Home] --> Mayor[Mayor Kernel]",
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
        "## Mothership Graph",
    ]
    if mothership["available"]:
        summary = mothership["snapshot"]["summary"]
        lines.extend([
            f"- Repo graph nodes: `{summary['node_count']}`",
            f"- Repo graph edges: `{summary['edge_count']}`",
            f"- Repo graph constraints: `{summary['constraint_count']}`",
        ])
    else:
        lines.append(f"- Mothership repo graph unavailable: `{mothership['error']}`")
    lines.extend([
        "",
        "## Source Anchors",
    ])
    lines.extend(f"- `{path}`" for path in sources)
    lines.extend(["", _provenance(page, context)])
    return "\n".join(lines)


def render_doc_projection(page: dict, context: dict, entity: dict | None = None) -> str:
    paths = [
        context["root"] / source["path"]
        for source in page.get("sources", [])
        if source["kind"] in {"authored", "doc"}
    ]
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
    lines.extend([
        "",
        "## Registry Table",
        "| Agent | Status | Role | Prana | Verified |",
        "| :--- | :--- | :--- | ---: | :--- |",
    ])
    lines.extend(
        f"| [{a['name']}](Agent--{a['slug']}) | {a['status']} "
        f"| {a['role']} | {a['prana']} "
        f"| {'yes' if a.get('oath_hash') else 'no'} |"
        for a in agents[:200]
    )
    lines.extend(["", "## First Alphabetical Slice"])
    lines.extend(
        f"- [{agent['name']}](Agent--{agent['slug']}) "
        f"— `{agent['status']}` / `{agent['role']}`"
        for agent in recent
    )
    lines.extend(["", _provenance(page, context)])
    return "\n".join(lines)


def render_registry_services(page: dict, context: dict, entity: dict | None = None) -> str:
    services = _service_names()
    bridge_services = [
        service for service in services
        if "bridge" in service
        or "nadi" in service
        or "federation" in service
    ]
    lines = [
        f"Total registered service types: **{len(services)}**",
        "",
        "## Bridge / Federation-Oriented Services",
    ]
    lines.extend(f"- `{service}`" for service in bridge_services)
    lines.extend(["", "## Full Service Table", "| Service | Class |", "| :--- | :--- |"])
    lines.extend(f"| `{service}` | `CityServiceRegistry` key |" for service in services)
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


def render_runtime_heartbeat_summary(page: dict, context: dict, entity: dict | None = None) -> str:
    snapshot = _heartbeat_snapshot(context["root"])
    lines = [
        "## Heartbeat Summary",
        f"- Local heartbeat count: `{snapshot['local_heartbeat_count']}`",
        f"- Seconds since local heartbeat: `{snapshot['seconds_since_local_heartbeat']}`",
        f"- Observation mode: `{snapshot['mode']}`",
        f"- Health: `{snapshot['health']}`",
        f"- Summary: `{snapshot['summary']}`",
    ]
    if snapshot["anomalies"]:
        lines.extend(["", "## Anomalies"])
        lines.extend(f"- `{anomaly}`" for anomaly in snapshot["anomalies"])
    if snapshot["observer_error"]:
        lines.extend(["", "## Observer Notes", f"- `{snapshot['observer_error']}`"])
    lines.extend(["", _provenance(page, context)])
    return "\n".join(lines)


def render_federation_overview(page: dict, context: dict, entity: dict | None = None) -> str:
    federation = _federation_summary(context["root"])
    latest = federation["latest_report"]
    lines = [
        "## Federation Surface",
        "Agent City exchanges directives and reports through"
        " a file-backed federation membrane and Nadi bridge.",
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


def render_mothership_repo_graph(page: dict, context: dict, entity: dict | None = None) -> str:
    mothership = load_mothership_repo_graph_snapshot(context["root"], limit=8)
    concept = load_mothership_repo_graph_context(context["root"], concept="governance")
    lines = [
        "## Mothership Repo Graph",
        "This page consumes the published repo-graph surface"
        " from `agent-internet`, pointed at the sibling"
        " `steward-protocol` mothership repository.",
        "",
    ]
    if not mothership["available"]:
        lines.extend([
            "- Status: `unavailable`",
            f"- Repo root: `{mothership['repo_root']}`",
            f"- Error: `{mothership['error']}`",
            "",
            _provenance(page, context),
        ])
        return "\n".join(lines)
    snapshot = mothership["snapshot"]
    summary = snapshot["summary"]
    lines.extend([
        f"- Source repo: `{snapshot['source']['repo_slug']}`",
        f"- Nodes: `{summary['node_count']}`",
        f"- Edges: `{summary['edge_count']}`",
        f"- Constraints: `{summary['constraint_count']}`",
        f"- Metrics: `{summary['metric_count']}`",
        "",
        "## Domain Breakdown",
    ])
    lines.extend(
        f"- `{domain}`: **{count}**"
        for domain, count in summary.get("domain_counts", {}).items()
    )
    lines.extend([
        "",
        "## Selected Nodes",
        "| Node | Type | Domain | Description |",
        "| :--- | :--- | :--- | :--- |",
    ])
    lines.extend(
        f"| `{node['node_id']}` | `{node['type']}` | `{node['domain']}` | {node['description']} |"
        for node in snapshot.get("nodes", [])
    )
    lines.extend(["", "## Relation Mix"])
    lines.extend(
        f"- `{relation}`: **{count}**"
        for relation, count in summary.get("relation_counts", {}).items()
    )
    lines.extend(["", "## Governance Context Probe"])
    if concept["available"]:
        lines.append(concept["context"]["context"] or "No context returned.")
    else:
        lines.append(f"Repo-graph context unavailable: `{concept['error']}`")
    lines.extend(["", _provenance(page, context)])
    return "\n".join(lines)


def render_mothership_governance_map(page: dict, context: dict, entity: dict | None = None) -> str:
    mothership = load_mothership_repo_graph_snapshot(context["root"], domain="governance", limit=8)
    concept = load_mothership_repo_graph_context(context["root"], concept="governance")
    lines = [
        "## Mothership Governance Map",
        "Governance-facing nodes projected from the"
        " steward-protocol repo graph through the published"
        " agent-internet membrane.",
        "",
    ]
    if not mothership["available"]:
        lines.extend([
            f"- Status: `unavailable`",
            f"- Error: `{mothership['error']}`",
            "",
            _provenance(page, context),
        ])
        return "\n".join(lines)
    snapshot = mothership["snapshot"]
    lines.extend([
        "| Node | Type | Description |",
        "| :--- | :--- | :--- |",
    ])
    lines.extend(
        f"| `{node['node_id']}` | `{node['type']}` | {node['description']} |"
        for node in snapshot.get("nodes", [])
    )
    lines.extend(["", "## Governance Neighbor Echoes"])
    for node in snapshot.get("nodes", [])[:3]:
        neighbor_payload = load_mothership_repo_graph_neighbors(
            context["root"], node_id=node["node_id"],
            depth=1, limit=6,
        )
        lines.append(f"### `{node['node_id']}`")
        if neighbor_payload["available"]:
            neighbors = neighbor_payload["neighbors"].get("neighbors", [])
            if neighbors:
                lines.extend(
                    f"- `{neighbor['node_id']}` — {neighbor['description']}"
                    for neighbor in neighbors
                )
            else:
                lines.append("- No neighbors returned.")
        else:
            lines.append(
                f"- Neighbor lookup unavailable: `{neighbor_payload['error']}`"
            )
        lines.append("")
    lines.append("## Governance Context Probe")
    if concept["available"]:
        lines.append(concept["context"]["context"])
    else:
        lines.append(
            f"Repo-graph context unavailable: `{concept['error']}`"
        )
    lines.extend(["", _provenance(page, context)])
    return "\n".join(lines)


def render_mothership_agent_constellation(
    page: dict, context: dict, entity: dict | None = None,
) -> str:
    mothership = load_mothership_repo_graph_snapshot(context["root"], node_type="agent", limit=10)
    lines = [
        "## Mothership Agent Constellation",
        "The highest-signal agent nodes currently exposed by the steward-protocol repo graph.",
        "",
    ]
    if not mothership["available"]:
        lines.extend([
            f"- Status: `unavailable`",
            f"- Error: `{mothership['error']}`",
            "",
            _provenance(page, context),
        ])
        return "\n".join(lines)
    snapshot = mothership["snapshot"]
    lines.extend([
        "| Agent Node | Domain | Critical | Varsha | Description |",
        "| :--- | :--- | :--- | :--- | :--- |",
    ])
    lines.extend(
        f"| `{node['node_id']}` | `{node['domain']}` "
        f"| {'yes' if node['properties'].get('critical') else 'no'} "
        f"| `{node['properties'].get('varsha', 'unknown')}` "
        f"| {node['description']} |"
        for node in snapshot.get("nodes", [])
    )
    lines.extend(["", "## Constellation Links"])
    for node in snapshot.get("nodes", [])[:4]:
        neighbor_payload = load_mothership_repo_graph_neighbors(
            context["root"], node_id=node["node_id"],
            depth=1, limit=6,
        )
        lines.append(f"### `{node['node_id']}`")
        if neighbor_payload["available"]:
            edges = neighbor_payload["neighbors"].get("edges", [])[:6]
            if edges:
                lines.extend(
                    f"- `{edge['source_id']}` "
                    f"-[{edge['relation']}]-> "
                    f"`{edge['target_id']}`"
                    for edge in edges
                )
            else:
                lines.append("- No constellation edges returned.")
        else:
            lines.append(
                f"- Neighbor lookup unavailable:"
                f" `{neighbor_payload['error']}`"
            )
        lines.append("")
    lines.extend(["", _provenance(page, context)])
    return "\n".join(lines)


def render_federation_recent_reports(page: dict, context: dict, entity: dict | None = None) -> str:
    federation = _federation_summary(context["root"])
    reports = federation["recent_reports"]
    lines = [
        "## Recent Federation Reports",
        f"- Total archived reports: `{federation['reports_count']}`",
        "",
        "| Heartbeat | Population | Alive | Chain Valid | Missions | Contracts |",
        "| ---: | ---: | ---: | :--- | ---: | :--- |",
    ]
    lines.extend(
        f"| {report.get('heartbeat', 0)} "
        f"| {report.get('population', 0)} "
        f"| {report.get('alive', 0)} "
        f"| {'yes' if report.get('chain_valid', False) else 'no'} "
        f"| {len(report.get('mission_results', []))} "
        f"| {report.get('contract_status', {}).get('passing', 0)}"
        f"/{report.get('contract_status', {}).get('total', 0)} |"
        for report in reports
    )
    latest = federation["latest_report"]
    missions = latest.get("mission_results", []) if latest else []
    if missions:
        lines.extend(["", "## Latest Mission Echoes"])
        lines.extend(
            f"- `{mission.get('id', 'unknown')}` "
            f"— {mission.get('name', 'Unnamed mission')} "
            f"/ owner `{mission.get('owner', 'unknown')}` "
            f"/ priority `{mission.get('priority', 'unknown')}`"
            for mission in missions
        )
    lines.extend(["", _provenance(page, context)])
    return "\n".join(lines)


def render_runtime_active_bridges(page: dict, context: dict, entity: dict | None = None) -> str:
    federation = _federation_summary(context["root"])
    latest = federation["latest_report"]
    missions = latest.get("mission_results", []) if latest else []
    lines = [
        "## Active Bridges",
        "The runtime currently exposes its outward traffic"
        " primarily through federation reports"
        " and Nadi message files.",
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
        lines.extend(
            f"- `{mission.get('id', 'unknown')}` "
            f"— {mission.get('name', 'Unnamed mission')} "
            f"({mission.get('status', 'unknown')})"
            for mission in missions
        )
    lines.extend(["", _provenance(page, context)])
    return "\n".join(lines)


def render_agent_page(page: dict, context: dict, entity: dict | None = None) -> dict:
    assert entity is not None
    verification = (
        "CONSTITUTIONAL_OATH_SIGNED"
        if entity.get("oath_hash")
        else "UNVERIFIED_DISCOVERY"
    )
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
        section_pages = [
            p for p in context["manifest"]["pages"]
            if p.get("section") == section
            and p.get("visibility", "listed") != "hidden"
            and "wiki_name" in p
        ]
        if not section_pages:
            continue
        entries.append(f"## {section}")
        entries.extend(f"- [[{p['wiki_name']}|{p['title']}]]" for p in section_pages)
        entries.append("")
    return "\n".join(entries).strip() + "\n"


def render_footer(page: dict, context: dict, entity: dict | None = None) -> str:
    return (
        f"Generated by Agent City wiki compiler"
        f" from `{context['source_sha']}`"
        f" at `{context['generated_at']}`"
        f" for `{context['origin_id']}`."
    )


def render_ledger_recent_changes(page: dict, context: dict, entity: dict | None = None) -> str:
    try:
        output = subprocess.check_output(
            ["git", "log", "--oneline", "-n", "10"],
            cwd=context["root"], text=True,
        )
    except Exception:
        output = "history unavailable"
    change_lines = "\n".join(
        f"- `{line}`"
        for line in output.splitlines() if line.strip()
    )
    return (
        "## Recent Changes\n\n"
        + change_lines
        + "\n\n"
        + _provenance(page, context)
    )


def _load_agents(root: Path) -> list[dict]:
    agents = []
    agents_path = root / "data/agents"
    agent_dirs = sorted(agents_path.iterdir()) if agents_path.exists() else []
    for agent_dir in agent_dirs:
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
    return [
        path.stem.upper()
        for path in sorted(phases_dir.glob("*.py"))
        if path.stem != "__init__"
    ]


def _service_names() -> list[str]:
    import city.registry as registry

    return sorted(getattr(registry, name) for name in dir(registry) if name.startswith("SVC_"))


def _heartbeat_snapshot(root: Path) -> dict:
    mayor_state = _load_json(root / "data/mayor_state.json")
    last_heartbeat = float(mayor_state.get("last_heartbeat", 0) or 0)
    if last_heartbeat:
        elapsed = datetime.now(UTC).timestamp() - last_heartbeat
        seconds_since = max(0, int(elapsed))
    else:
        seconds_since = -1
    snapshot = {
        "mode": "local_fallback",
        "health": "unknown",
        "summary": "local runtime snapshot only",
        "anomalies": [],
        "observer_error": "",
        "local_heartbeat_count": int(mayor_state.get("heartbeat_count", 0) or 0),
        "seconds_since_local_heartbeat": seconds_since,
    }
    if last_heartbeat:
        snapshot["health"] = "fresh" if seconds_since <= 3600 else "stale"
        if seconds_since > 3600:
            snapshot["anomalies"].append(f"local_heartbeat_stale:{seconds_since}s")
    if not _should_run_live_observer():
        return snapshot
    try:
        owner, repo = _github_origin_parts(root)
        if not owner or not repo:
            snapshot["observer_error"] = "origin repo unavailable"
            return snapshot
        from city.heartbeat_observer import HeartbeatObserver

        diagnosis = HeartbeatObserver(_owner=owner, _repo=repo).observe()
        snapshot.update(
            {
                "mode": "live_observer",
                "health": "healthy" if diagnosis.healthy else "degraded",
                "summary": diagnosis.summary(),
                "anomalies": list(diagnosis.anomalies),
                "observer_error": diagnosis.observer_error,
            }
        )
        return snapshot
    except Exception as exc:
        snapshot["observer_error"] = str(exc)
        return snapshot


def _should_run_live_observer() -> bool:
    has_env = bool(
        os.environ.get("AGENT_CITY_WIKI_OBSERVE")
        or os.environ.get("GITHUB_ACTIONS")
    )
    return has_env and shutil.which("gh") is not None


def _github_origin_parts(root: Path) -> tuple[str, str]:
    try:
        origin = subprocess.check_output(
            ["git", "remote", "get-url", "origin"],
            cwd=root, text=True,
        ).strip()
    except Exception:
        return "", ""
    trimmed = origin[:-4] if origin.endswith(".git") else origin
    if trimmed.startswith("git@github.com:"):
        slug = trimmed.split(":", 1)[1]
    elif "github.com/" in trimmed:
        slug = trimmed.split("github.com/", 1)[1]
    else:
        return "", ""
    parts = slug.split("/")
    return (parts[0], parts[1]) if len(parts) >= 2 else ("", "")


def _federation_summary(root: Path) -> dict:
    federation_dir = root / "data/federation"
    reports_dir = federation_dir / "reports"
    reports = (
        sorted(reports_dir.glob("report_*.json"))
        if reports_dir.exists() else []
    )
    recent_reports = [_load_json(path) for path in reports[-10:]]
    latest_report = recent_reports[-1] if recent_reports else {}
    outbox = _load_json(federation_dir / "nadi_outbox.json")
    inbox = _load_json(federation_dir / "nadi_inbox.json")
    directives_dir = federation_dir / "directives"
    pending = list(directives_dir.glob("*.json")) if directives_dir.exists() else []
    if directives_dir.exists():
        done = (
            list(directives_dir.glob("*.done"))
            + list(directives_dir.glob("*.done.json"))
        )
    else:
        done = []
    return {
        "reports_count": len(reports),
        "recent_reports": recent_reports,
        "latest_report": latest_report,
        "latest_report_heartbeat": (
            latest_report.get("heartbeat", "none")
            if latest_report else "none"
        ),
        "outbox_on_disk": len(outbox) if isinstance(outbox, list) else 0,
        "inbox_on_disk": len(inbox) if isinstance(inbox, list) else 0,
        "directives_pending": len([
            path for path in pending
            if not path.name.endswith(".done.json")
        ]),
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
    fields.update({
        key.replace("_", "-").title(): value
        for key, value in extra.items()
    })
    items = [f"- **{key}**: `{value}`" for key, value in fields.items()]
    return "\n".join(["## Provenance", *items])


def compiler_context(root: Path, manifest: dict) -> dict:
    manifest_scope = manifest.get("city") or manifest.get("world") or {}
    try:
        source_sha = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, text=True,
        ).strip()
    except Exception:
        source_sha = "unknown"
    return {
        "root": root,
        "manifest": manifest,
        "generated_at": datetime.now(UTC).isoformat(),
        "origin_id": str(manifest_scope.get("origin_id") or "city://unknown"),
        "source_sha": source_sha,
    }
