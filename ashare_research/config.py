from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_simple_yaml(path: str | Path) -> dict[str, Any]:
    """Tiny YAML subset loader for this repo's smoke config."""
    try:
        import yaml  # type: ignore

        return yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except Exception:
        data: dict[str, Any] = {}
        stack: list[tuple[int, dict[str, Any]]] = [(-1, data)]
        for raw in Path(path).read_text(encoding="utf-8").splitlines():
            line = raw.split("#", 1)[0].rstrip()
            if not line:
                continue
            indent = len(line) - len(line.lstrip(" "))
            key, _, value = line.strip().partition(":")
            while stack and indent <= stack[-1][0]:
                stack.pop()
            parent = stack[-1][1]
            if value.strip() == "":
                child: dict[str, Any] = {}
                parent[key] = child
                stack.append((indent, child))
            else:
                v = value.strip().strip('"').strip("'")
                lower = v.lower()
                if lower == "false":
                    parent[key] = False
                elif lower == "true":
                    parent[key] = True
                elif lower in {"null", "none"}:
                    parent[key] = None
                elif v.startswith("["):
                    parent[key] = json.loads(v.replace("'", '"'))
                else:
                    try:
                        parent[key] = int(v)
                    except ValueError:
                        try:
                            parent[key] = float(v)
                        except ValueError:
                            parent[key] = v
        return data
