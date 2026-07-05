from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


DEFAULT_ROOT = Path(r"D:\alphaGPT_runtime\research_intel")
FIRECRAWL_ENDPOINT = "https://api.firecrawl.dev/v2/scrape"


FACTOR_KEYWORDS = {
    "value": ["value", "valuation", "PE", "PB", "book-to-market", "earnings yield"],
    "momentum": ["momentum", "return", "reversal"],
    "quality": ["quality", "ROE", "ROA", "profitability"],
    "volatility": ["volatility", "risk", "drawdown"],
    "liquidity": ["liquidity", "turnover", "volume"],
    "price_volume": ["price-volume", "price volume", "volume", "technical"],
    "alpha158": ["Alpha158", "feature", "factor"],
}

STRATEGY_KEYWORDS = {
    "ranking": ["rank", "ranking", "top", "selection"],
    "rebalance": ["rebalance", "monthly", "quarterly"],
    "risk_control": ["risk", "neutral", "drawdown", "volatility"],
    "portfolio": ["portfolio", "position", "weight"],
    "execution": ["execution", "order", "cost"],
}


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8-sig") as fh:
        for line_no, line in enumerate(fh, 1):
            text = line.strip()
            if not text:
                continue
            try:
                rows.append(json.loads(text))
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"{path}:{line_no}: invalid JSON: {exc}") from exc
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=False) + "\n")


def append_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=False) + "\n")


def compact_text(text: str, limit: int = 360) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0] + "..."


def detect_keywords(text: str, groups: dict[str, list[str]]) -> list[str]:
    haystack = text.lower()
    hits: list[str] = []
    for group, needles in groups.items():
        if any(needle.lower() in haystack for needle in needles):
            hits.append(group)
    return hits


def source_url(row: dict[str, Any]) -> str:
    return str(row.get("source_url_or_path") or row.get("source_url") or "").strip()


def select_sources(rows: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    preferred = [
        "qlib_github",
        "qlib_alpha158_config",
        "qlib_paper",
        "smart_beta_public",
        "stockformer_paper",
        "multifactor_market_neutral_paper",
        "a_share_multi_agent_fundamental_paper",
    ]
    by_id = {str(row.get("source_id")): row for row in rows}
    selected: list[dict[str, Any]] = []
    for source_id in preferred:
        row = by_id.get(source_id)
        if row and str(source_url(row)).startswith("http"):
            selected.append(row)
        if len(selected) >= limit:
            return selected
    for row in rows:
        if len(selected) >= limit:
            break
        if row in selected:
            continue
        if str(source_url(row)).startswith("http"):
            selected.append(row)
    return selected


def firecrawl_scrape(api_key: str, url: str, timeout: int) -> dict[str, Any]:
    payload = {
        "url": url,
        "formats": ["markdown"],
        "onlyMainContent": True,
        "timeout": timeout * 1000,
    }
    req = urllib.request.Request(
        FIRECRAWL_ENDPOINT,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout + 10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def extract_markdown(result: dict[str, Any]) -> tuple[str, str]:
    data = result.get("data") if isinstance(result.get("data"), dict) else result
    title = ""
    markdown = ""
    if isinstance(data, dict):
        markdown = str(data.get("markdown") or data.get("content") or "")
        metadata = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
        title = str(metadata.get("title") or data.get("title") or "")
    return title, markdown


def update_rows_with_source_verification(
    rows: list[dict[str, Any]],
    verified_urls: set[str],
    checked_at: str,
) -> list[dict[str, Any]]:
    updated: list[dict[str, Any]] = []
    for row in rows:
        new_row = dict(row)
        urls = [part.strip() for part in str(new_row.get("source_url_or_path", "")).split(";")]
        matched = [url for url in urls if url in verified_urls]
        new_row.setdefault("source_verified_by_firecrawl", bool(matched))
        if matched:
            new_row["source_verified_by_firecrawl"] = True
            new_row["firecrawl_verified_at"] = checked_at
            new_row["firecrawl_verified_urls"] = matched
        else:
            new_row.setdefault("source_verified_by_firecrawl", False)
        updated.append(new_row)
    return updated


def count_verified_factor(rows: list[dict[str, Any]]) -> int:
    count = 0
    for row in rows:
        if not row.get("source_verified_by_firecrawl"):
            continue
        if row.get("can_alphaGPT_current_data_support") != "yes":
            continue
        if row.get("curation_status") not in {"usable_as_seed", "candidate"}:
            continue
        required = ["factor_id", "factor_name_en", "factor_category", "raw_formula_or_logic_summary"]
        if all(row.get(key) for key in required):
            count += 1
    return count


def count_verified_strategy(rows: list[dict[str, Any]]) -> int:
    count = 0
    for row in rows:
        if not row.get("source_verified_by_firecrawl"):
            continue
        if row.get("curation_status") not in {"useful_reference", "candidate"}:
            continue
        required = ["strategy_id", "strategy_type", "selection_logic", "rebalance_frequency", "risk_control"]
        if all(row.get(key) for key in required):
            count += 1
    return count


def write_markdown_summaries(root: Path, factors: list[dict[str, Any]], strategies: list[dict[str, Any]]) -> None:
    factor_path = root / "library" / "factor_prior_library.md"
    strategy_path = root / "library" / "trading_strategy_library.md"
    verified_factors = [row for row in factors if row.get("source_verified_by_firecrawl")]
    verified_strategies = [row for row in strategies if row.get("source_verified_by_firecrawl")]

    factor_lines = [
        "# Factor Prior Library",
        "",
        "This summary is generated from structured JSONL records. Firecrawl verification confirms public source reachability only; it is not an AlphaGPT backtest result.",
        "",
        f"- total_records: {len(factors)}",
        f"- source_verified_by_firecrawl: {len(verified_factors)}",
        "",
    ]
    for row in factors:
        factor_lines.append(
            f"- {row.get('factor_id')}: {row.get('factor_name_en')} | support={row.get('can_alphaGPT_current_data_support')} | firecrawl={row.get('source_verified_by_firecrawl', False)}"
        )
    factor_path.write_text("\n".join(factor_lines) + "\n", encoding="utf-8")

    strategy_lines = [
        "# Trading Strategy Library",
        "",
        "This summary is generated from structured JSONL records. Firecrawl verification confirms public source reachability only; it is not trading advice.",
        "",
        f"- total_records: {len(strategies)}",
        f"- source_verified_by_firecrawl: {len(verified_strategies)}",
        "",
    ]
    for row in strategies:
        strategy_lines.append(
            f"- {row.get('strategy_id')}: {row.get('strategy_type')} | simulate_later={row.get('can_alphaGPT_simulate_later')} | firecrawl={row.get('source_verified_by_firecrawl', False)}"
        )
    strategy_path.write_text("\n".join(strategy_lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--limit", type=int, default=7)
    parser.add_argument("--timeout", type=int, default=45)
    args = parser.parse_args()

    api_key = os.environ.get("FIRECRAWL_API_KEY")
    if not api_key:
        print("FIRECRAWL_API_KEY_PRESENT=false")
        return 2
    print("FIRECRAWL_API_KEY_PRESENT=true")

    root = args.root
    checked_at = now_iso()
    source_path = root / "sources" / "source_registry.jsonl"
    factor_path = root / "library" / "factor_prior_library.jsonl"
    strategy_path = root / "library" / "trading_strategy_library.jsonl"

    sources = read_jsonl(source_path)
    factors_before = read_jsonl(factor_path)
    strategies_before = read_jsonl(strategy_path)
    selected = select_sources(sources, args.limit)

    verified_urls: set[str] = set()
    factor_notes: list[dict[str, Any]] = []
    strategy_notes: list[dict[str, Any]] = []
    source_results: dict[str, dict[str, Any]] = {}

    for index, source in enumerate(selected, 1):
        sid = str(source.get("source_id") or f"source_{index}")
        url = source_url(source)
        print(f"scrape {index}/{len(selected)}: {sid}")
        result_row = {
            "source_id": sid,
            "source_url": url,
            "checked_at": checked_at,
            "source_verified_by_firecrawl": False,
            "public_readable": False,
            "failure_reason": "",
        }
        try:
            response = firecrawl_scrape(api_key, url, args.timeout)
            title, markdown = extract_markdown(response)
            success = bool(response.get("success", True)) and bool(markdown.strip())
            result_row.update(
                {
                    "source_verified_by_firecrawl": success,
                    "public_readable": success,
                    "title": title or source.get("source_title"),
                    "content_chars_observed": len(markdown),
                    "factor_keyword_groups": detect_keywords(markdown, FACTOR_KEYWORDS),
                    "strategy_keyword_groups": detect_keywords(markdown, STRATEGY_KEYWORDS),
                    "summary_excerpt": compact_text(markdown),
                    "restrictions": "public scrape only; full page content not stored",
                }
            )
            if success:
                verified_urls.add(url)
                factor_notes.append(
                    {
                        "source_id": sid,
                        "source_url": url,
                        "source_title": result_row["title"],
                        "checked_at": checked_at,
                        "source_verified_by_firecrawl": True,
                        "factor_keyword_groups": result_row["factor_keyword_groups"],
                        "brief_summary": result_row["summary_excerpt"],
                    }
                )
                strategy_notes.append(
                    {
                        "source_id": sid,
                        "source_url": url,
                        "source_title": result_row["title"],
                        "checked_at": checked_at,
                        "source_verified_by_firecrawl": True,
                        "strategy_keyword_groups": result_row["strategy_keyword_groups"],
                        "brief_summary": result_row["summary_excerpt"],
                    }
                )
        except urllib.error.HTTPError as exc:
            result_row["failure_reason"] = f"http_error_{exc.code}"
        except urllib.error.URLError as exc:
            result_row["failure_reason"] = f"url_error_{exc.reason}"
        except Exception as exc:  # noqa: BLE001
            result_row["failure_reason"] = f"{type(exc).__name__}: {exc}"
        source_results[sid] = result_row
        time.sleep(0.5)

    updated_sources: list[dict[str, Any]] = []
    for row in sources:
        new_row = dict(row)
        sid = str(new_row.get("source_id"))
        if sid in source_results:
            result = source_results[sid]
            new_row["firecrawl_last_checked_at"] = checked_at
            new_row["firecrawl_public_readable"] = result.get("public_readable", False)
            new_row["source_verified_by_firecrawl"] = result.get("source_verified_by_firecrawl", False)
            new_row["firecrawl_failure_reason"] = result.get("failure_reason", "")
        else:
            new_row.setdefault("source_verified_by_firecrawl", False)
        updated_sources.append(new_row)

    factors_after = update_rows_with_source_verification(factors_before, verified_urls, checked_at)
    strategies_after = update_rows_with_source_verification(strategies_before, verified_urls, checked_at)

    write_jsonl(source_path, updated_sources)
    write_jsonl(factor_path, factors_after)
    write_jsonl(strategy_path, strategies_after)
    append_jsonl(root / "parsed" / "firecrawl_extracted_factor_notes.jsonl", factor_notes)
    append_jsonl(root / "parsed" / "firecrawl_extracted_strategy_notes.jsonl", strategy_notes)
    write_markdown_summaries(root, factors_after, strategies_after)

    success_count = sum(1 for row in source_results.values() if row.get("source_verified_by_firecrawl"))
    failure_rows = [row for row in source_results.values() if not row.get("source_verified_by_firecrawl")]
    report_lines = [
        "# Firecrawl Live Collection Report",
        "",
        f"- generated_at: {checked_at}",
        "- api_key_source: environment variable only",
        "- api_key_printed_or_saved: false",
        f"- selected_url_count: {len(selected)}",
        f"- success_count: {success_count}",
        f"- failure_count: {len(failure_rows)}",
        f"- factor_records_total: {len(factors_after)}",
        f"- factor_records_source_verified_by_firecrawl: {sum(1 for row in factors_after if row.get('source_verified_by_firecrawl'))}",
        f"- factor_records_ready_for_calculability_mapping: {count_verified_factor(factors_after)}",
        f"- strategy_records_total: {len(strategies_after)}",
        f"- strategy_records_source_verified_by_firecrawl: {sum(1 for row in strategies_after if row.get('source_verified_by_firecrawl'))}",
        f"- strategy_records_ready_for_calculability_mapping: {count_verified_strategy(strategies_after)}",
        "- full_webpage_content_saved: false",
        "- alphaGPT_backtest_or_search_started: false",
        "- alphaGPT_main_logic_modified: false",
        "- forward_data_accessed: false",
        "",
        "## Source Results",
        "",
    ]
    for row in source_results.values():
        report_lines.append(
            f"- {row['source_id']}: success={row.get('source_verified_by_firecrawl', False)} url={row['source_url']} reason={row.get('failure_reason', '')}"
        )
    (root / "reports" / "firecrawl_live_collection_report.md").write_text(
        "\n".join(report_lines) + "\n", encoding="utf-8"
    )

    print(f"selected_url_count={len(selected)}")
    print(f"success_count={success_count}")
    print(f"failure_count={len(failure_rows)}")
    print(f"factor_records_source_verified_by_firecrawl={sum(1 for row in factors_after if row.get('source_verified_by_firecrawl'))}")
    print(f"factor_records_ready_for_calculability_mapping={count_verified_factor(factors_after)}")
    print(f"strategy_records_source_verified_by_firecrawl={sum(1 for row in strategies_after if row.get('source_verified_by_firecrawl'))}")
    print(f"strategy_records_ready_for_calculability_mapping={count_verified_strategy(strategies_after)}")
    return 0 if success_count else 1


if __name__ == "__main__":
    raise SystemExit(main())
