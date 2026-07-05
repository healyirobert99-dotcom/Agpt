from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib import request
from urllib.error import HTTPError, URLError


DEFAULT_OUT = Path(r"D:\alphaGPT_runtime\research_intel\raw\firecrawl_raw.jsonl")


DEFAULT_QUERIES = [
    "site:joinquant.com/community 多因子 选股 策略 回测 调仓 风控",
    "site:ricequant.com 多因子 因子 选股 回测 调仓",
    "site:bigquant.com 多因子 选股 策略 因子 回测",
    "site:github.com A股 多因子 选股 回测 Python",
    "site:github.com China A share multi factor stock selection",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def post_json(url: str, payload: dict[str, Any], api_key: str, timeout: int) -> dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = request.Request(
        url,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "AlphaGPT-Research-Intel/1.0",
        },
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Firecrawl HTTP {exc.code}: {detail[:500]}") from exc
    except URLError as exc:
        raise RuntimeError(f"Firecrawl network error: {exc}") from exc


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Small-batch public strategy collection with Firecrawl.")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--firecrawl-url", default=os.environ.get("FIRECRAWL_API_URL", "https://api.firecrawl.dev/v2"))
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    api_key = os.environ.get("FIRECRAWL_API_KEY", "")
    if not args.dry_run and not api_key:
        print("FIRECRAWL_API_KEY is required for live collection. No key was printed or stored.", file=sys.stderr)
        return 2

    rows: list[dict[str, Any]] = []
    for query in DEFAULT_QUERIES:
        if len(rows) >= args.limit:
            break
        payload = {
            "query": query,
            "limit": min(5, max(1, args.limit - len(rows))),
            "scrapeOptions": {
                "formats": ["markdown"],
                "onlyMainContent": True
            }
        }
        row = {
            "record_type": "firecrawl_search",
            "query": query,
            "collected_at": utc_now(),
            "payload": payload,
            "dry_run": bool(args.dry_run),
        }
        if not args.dry_run:
            row["response"] = post_json(f"{args.firecrawl_url.rstrip('/')}/search", payload, api_key, args.timeout)
        rows.append(row)
        time.sleep(0.2)

    write_jsonl(args.out, rows)
    print(json.dumps({
        "out": str(args.out),
        "records_written": len(rows),
        "dry_run": bool(args.dry_run),
        "live_collection": not args.dry_run,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
