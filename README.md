# AlphaGPT

AlphaGPT is a local A-share autonomous factor research project.

Current scope:

- local historical research only;
- no automatic trading;
- no high-frequency trading;
- no broker connection;
- no automatic order placement;
- no API keys or local market databases in this public repository.

## Current Status

AlphaGPT v2 first-round MVP search did not find any factor suitable for forward observation under the current narrow formula space and strict revalidation path.

This means the current MVP search configuration failed. It does not prove that autonomous A-share factor discovery is impossible.

The project is currently building a public-strategy-driven factor prior library and a trading-operation strategy library. These materials are research seeds only. They have not been validated by AlphaGPT local backtests and must not be used for trading.

## Repository Contents

- `ashare_research/`: A-share research runtime and factor research code.
- `tests/`: unit and integration tests.
- `config/`: non-secret v2 research configuration files.
- `docs/`: current mainline, research boundary, and lightweight reports.
- `research_intel/`: public-source factor prior and trading-operation intelligence.
- `tools/firecrawl/`: lightweight Firecrawl Cloud API wrapper for future public-source collection.

## Security Boundary

This public repository intentionally excludes:

- local SQLite market databases;
- raw market data;
- raw web-crawl page contents;
- `.env` files;
- Tushare tokens;
- Firecrawl API keys;
- broker credentials;
- full copyrighted reports;
- large run artifacts;
- real trading signals or buy/sell recommendations.

Any factor or strategy record in this repository is only a seed candidate for future research. It is not investment advice.
