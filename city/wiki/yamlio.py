from __future__ import annotations

import json
import subprocess
from pathlib import Path


def load_yaml(path: Path) -> dict:
    try:
        import yaml  # type: ignore

        return yaml.safe_load(path.read_text())
    except Exception:
        output = subprocess.check_output(
            [
                "ruby",
                "-e",
                "require 'yaml'; require 'json'; print JSON.generate(YAML.load_file(ARGV[0]))",
                str(path),
            ],
            text=True,
        )
        return json.loads(output)
