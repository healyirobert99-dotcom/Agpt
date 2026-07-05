from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


DEFAULT_RAW = Path(r"D:\alphaGPT_runtime\research_intel\raw\firecrawl_raw.jsonl")
DEFAULT_OUT = Path(r"D:\alphaGPT_runtime\research_intel\parsed\review_queue.jsonl")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def stable_id(prefix: str, parts: Iterable[str]) -> str:
    digest = hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"


def snippet(text: str, limit: int = 500) -> str:
    return re.sub(r"\s+", " ", text or "").strip()[:limit]


def iter_items(response: Any) -> Iterable[dict[str, Any]]:
    if isinstance(response, list):
        for item in response:
            if isinstance(item, dict):
                yield item
    elif isinstance(response, dict):
        for key in ("data", "results", "items"):
            value = response.get(key)
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        yield item
                return
        if any(k in response for k in ("url", "title", "markdown", "content")):
            yield response


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare review queue from Firecrawl raw JSONL.")
    parser.add_argument("--raw", type=Path, default=DEFAULT_RAW)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    queue = []
    seen = set()
    for raw in read_jsonl(args.raw):
        for item in iter_items(raw.get("response")):
            url = item.get("url") or item.get("sourceURL") or ""
            title = item.get("title") or item.get("metadata", {}).get("title") or ""
            text = item.get("markdown") or item.get("content") or item.get("description") or ""
            record_id = stable_id("review", [url, title, snippet(text)])
            if record_id in seen:
                continue
            seen.add(record_id)
            queue.append({
                "record_id": record_id,
                "review_status": "needs_review",
                "source_url": url,
                "title": title,
                "summary_hint": snippet(text),
                "queued_at": datetime.now(timezone.utc).isoformat(),
                "instructions": "Extract factor logic and trading operation rules only if the source is public and allowed.",
            })

    write_jsonl(args.out, queue)
    print(json.dumps({"raw_records": len(read_jsonl(args.raw)), "review_queue_records": len(queue), "out": str(args.out)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
