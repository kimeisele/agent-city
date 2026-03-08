from __future__ import annotations

from importlib import import_module
from pathlib import Path

from city.wiki.blocks import merge_hybrid_content
from city.wiki.renderers import compiler_context
from city.wiki.yamlio import load_yaml


def build_wiki(*, root: Path, output_dir: Path) -> list[Path]:
    manifest = load_yaml(root / "wiki-src/manifest.yaml")
    blocks = load_yaml(root / str(manifest["publication"]["blocks_registry"]))
    context = compiler_context(root, manifest)
    output_dir.mkdir(parents=True, exist_ok=True)
    built: list[Path] = []
    for page in manifest["pages"]:
        if "wiki_name_pattern" in page:
            built.extend(_build_entity_family(page=page, context=context, blocks=blocks, output_dir=output_dir))
        else:
            built.append(_build_page(page=page, context=context, blocks=blocks, output_dir=output_dir))
    return built


def _build_entity_family(*, page: dict, context: dict, blocks: dict, output_dir: Path) -> list[Path]:
    agents_dir = context["root"] / page["source_collection"]["path"]
    built = []
    for agent_dir in sorted(agents_dir.iterdir() if agents_dir.exists() else []):
        if not agent_dir.is_dir():
            continue
        entity = {"slug": agent_dir.name}
        manifest_path = agent_dir / "manifest.json"
        if manifest_path.exists():
            entity.update(_load_yaml_or_json(manifest_path))
        entity["slug"] = agent_dir.name
        identity_path = agent_dir / "identity.json"
        if identity_path.exists():
            entity.update(_load_yaml_or_json(identity_path))
        cell_path = agent_dir / "cell.json"
        if cell_path.exists():
            entity.update(_load_yaml_or_json(cell_path))
        entity_page = dict(page)
        entity_page["wiki_name"] = str(page["wiki_name_pattern"]).format(slug=entity["slug"])
        entity_page["title"] = str(page["title_pattern"]).format(name=entity.get("name", entity["slug"]))
        built.append(_build_page(page=entity_page, context=context, blocks=blocks, output_dir=output_dir, entity=entity))
    return built


def _build_page(*, page: dict, context: dict, blocks: dict, output_dir: Path, entity: dict | None = None) -> Path:
    renderer = _resolve_renderer(page["renderer"], context["manifest"])
    output_path = output_dir / f"{page['wiki_name']}.md"
    if page["mode"] == "hybrid":
        rendered_blocks = renderer(page, context, entity)
        existing = output_path.read_text() if output_path.exists() else None
        content = merge_hybrid_content(existing=existing, page=page, blocks_config=blocks, rendered_blocks=rendered_blocks)
    else:
        body = renderer(page, context, entity)
        content = f"# {page['title']}\n\n{body.rstrip()}\n"
    output_path.write_text(content)
    return output_path


def _resolve_renderer(name: str, manifest: dict):
    module_name, func_name = dict(manifest.get("renderers", {}))[name].split(":", 1)
    return getattr(import_module(module_name), func_name)


def _load_yaml_or_json(path: Path) -> dict:
    if path.suffix == ".json":
        import json

        return json.loads(path.read_text())
    return load_yaml(path)
