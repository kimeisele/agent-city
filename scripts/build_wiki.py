#!/usr/bin/env python3

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from city.wiki.compiler import build_wiki


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the local Agent City wiki manifestation")
    parser.add_argument("--output-dir", default=".vibe/wiki-build", help="Where to materialize wiki markdown files")
    args = parser.parse_args()
    built = build_wiki(root=ROOT, output_dir=ROOT / args.output_dir)
    print(f"built {len(built)} pages into {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
