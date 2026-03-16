from __future__ import annotations

import re


def build_bootstrap_content(*, title: str, template: dict, blocks_config: dict) -> str:
    lines = [title, ""]
    for block_id in template.get("blocks", []):
        lines.extend([_start(block_id, blocks_config), "", _end(block_id, blocks_config), ""])
    return "\n".join(lines).rstrip() + "\n"


def merge_hybrid_content(
    *, existing: str | None, page: dict,
    blocks_config: dict, rendered_blocks: dict[str, str],
) -> str:
    contract = dict(page.get("block_contract", {}))
    template_name = str(contract.get("bootstrap_template", ""))
    content = existing or build_bootstrap_content(
        title=f"# {page.get('title', page.get('wiki_name', 'Page'))}",
        template=dict(blocks_config.get("templates", {}).get(template_name, {})),
        blocks_config=blocks_config,
    )
    required_blocks = list(contract.get("required_blocks", []))
    missing = [
        block_id for block_id in required_blocks
        if not has_block(content, block_id, blocks_config)
    ]
    if missing and existing and bool(contract.get("bootstrap_unmarked_existing", False)):
        present_count = sum(
            1 for block_id in required_blocks
            if has_block(existing, block_id, blocks_config)
        )
        if present_count == 0:
            content = build_bootstrap_content(
                title=f"# {page.get('title', page.get('wiki_name', 'Page'))}",
                template=dict(blocks_config.get("templates", {}).get(template_name, {})),
                blocks_config=blocks_config,
            )
            preserved = list(contract.get("preserved_blocks", []))
            if preserved and existing.strip():
                content = replace_block(content, preserved[0], existing.strip(), blocks_config)
            missing = [
                block_id for block_id in required_blocks
                if not has_block(content, block_id, blocks_config)
            ]
    if missing:
        raise ValueError(f"missing_required_blocks:{page.get('id')}:{','.join(missing)}")
    for block_id, block_value in rendered_blocks.items():
        content = replace_block(content, block_id, block_value, blocks_config)
    return content


def has_block(content: str, block_id: str, blocks_config: dict) -> bool:
    return _pattern(block_id, blocks_config).search(content) is not None


def replace_block(content: str, block_id: str, block_value: str, blocks_config: dict) -> str:
    pattern = _pattern(block_id, blocks_config)
    start = _start(block_id, blocks_config)
    end = _end(block_id, blocks_config)
    wrapped = f"{start}\n{block_value.rstrip()}\n{end}"
    if not pattern.search(content):
        raise ValueError(f"missing_block:{block_id}")
    return pattern.sub(wrapped, content)


def _pattern(block_id: str, blocks_config: dict) -> re.Pattern[str]:
    start = re.escape(_start(block_id, blocks_config))
    end = re.escape(_end(block_id, blocks_config))
    return re.compile(f"{start}.*?{end}", re.DOTALL)


def _start(block_id: str, blocks_config: dict) -> str:
    return str(blocks_config["marker_template"]["start"]).format(block_id=block_id)


def _end(block_id: str, blocks_config: dict) -> str:
    return str(blocks_config["marker_template"]["end"]).format(block_id=block_id)
