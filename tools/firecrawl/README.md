# AlphaGPT Firecrawl Tool

This is a lightweight Firecrawl Cloud API wrapper for the AlphaGPT information
collection phase. It does not self-host Firecrawl and does not store secrets.

Current host status:
- Docker is unavailable.
- Node.js/npm/pnpm are unavailable.
- Python is available.
- `FIRECRAWL_API_KEY` is not set.

Set the API key only in the current shell when live collection is approved:

```powershell
# Set the Firecrawl API key locally for the current shell only.
# Do not write the key into files or commit it to Git.
```

Dry-run:

```powershell
python firecrawl_collect.py --sources D:\alphaGPT_runtime\research_intel\sources\source_registry.jsonl --dry-run --limit 5
```

Live small-batch collection after setting the key:

```powershell
python firecrawl_collect.py --limit 10 --out D:\alphaGPT_runtime\research_intel\raw\firecrawl_raw.jsonl
python prepare_review_queue.py --raw D:\alphaGPT_runtime\research_intel\raw\firecrawl_raw.jsonl --out D:\alphaGPT_runtime\research_intel\parsed\review_queue.jsonl
```

Boundary:
- public pages only;
- no login bypass;
- no paid content;
- no full article or full strategy-code copying;
- no AlphaGPT backtest or factor search is launched by these scripts.
