# Safe Sync Audit

Generated: 2026-07-05

Target repository:

```text
https://github.com/healyirobert99-dotcom/Agpt
```

## Local Tooling

- `git`: unavailable on this host.
- `gh`: unavailable on this host.
- GitHub repository status checked through the GitHub connector: repository is empty.

Because `git` and `gh` are unavailable, the safe first push was not executed from this host.

## Prepared Sync Root

```text
D:\alphaGPT\github_safe_sync
```

This directory is a curated public-sync package. It is not a full copy of the local workspace.

## Included Scope

- README and project status documents.
- A-share research runtime under `ashare_research/`.
- Tests under `tests/`.
- Non-secret v2 configs under `config/`.
- Current mainline and research boundary documents.
- Lightweight v2 report summaries under `docs/reports/`.
- Public research intelligence summaries under `research_intel/`.
- Firecrawl wrapper code under `tools/firecrawl/`.

## Excluded Scope

- `.venv/`
- `.pytest_cache/`
- `stock-data/`
- local SQLite databases
- raw crawl data
- raw market data
- full run directories
- daily equity/order/trade/position artifacts
- `.env`
- API keys
- cookies
- broker credentials
- large files over 20MB

## Safety Scan

Large-file scan of the sync package:

```text
no files over 20MB
```

Database/raw/local-artifact scan of the sync package:

```text
no sqlite/db/parquet/pickle/h5 files
no .env files
no .venv files
no stock-data directory
no raw directory
no runs directory
```

Sensitive-word scan findings are explainable:

- formula `token` terminology in AlphaGPT code/tests;
- `TUSHARE_TOKEN` and `FIRECRAWL_API_KEY` environment variable names only;
- `.env.example` contains empty placeholders only;
- Firecrawl wrapper reads API key from the shell environment and does not write it to files.

No real token, password, cookie, broker credential, or API key was identified in the sync package.

## Push Status

```text
push_executed: false
reason: git and gh are unavailable on this host
```

After Git and GitHub CLI are installed/authenticated, the intended push path is:

```powershell
Set-Location D:\alphaGPT\github_safe_sync
git init
git branch -M main
git remote add origin https://github.com/healyirobert99-dotcom/Agpt.git
git add .
git status --short
git diff --stat --cached
git commit -m "Initial safe sync of AlphaGPT research project"
git push -u origin main
```

Do not use `git add .` from `C:\Users\Admin\alphaGPT`; use the curated sync package unless a new safety audit is performed.
