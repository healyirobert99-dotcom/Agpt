from __future__ import annotations

from typing import Any

import pandas as pd


def deduplicate_by_correlation(rows: list[dict[str, Any]], outputs: dict[str, pd.Series], threshold: float, max_rows: int = 20000) -> tuple[list[dict[str, Any]], dict]:
    passed = [r for r in rows if r.get("fast_screen_status") == "passed" and r["formula_hash"] in outputs]
    kept: list[dict[str, Any]] = []
    clusters: list[dict] = []
    for row in sorted(passed, key=lambda r: (-(abs(r.get("rank_ic_mean") or 0.0)), -float(r.get("coverage") or 0.0), int(len(str(r.get("canonical_formula", "")))))):
        h = row["formula_hash"]
        duplicate_of = None
        for existing in kept:
            corr = _aligned_corr(outputs[h], outputs[existing["formula_hash"]], max_rows=max_rows)
            if corr is not None and abs(corr) >= threshold:
                duplicate_of = existing["formula_hash"]
                clusters.append({"representative": duplicate_of, "member": h, "correlation": corr})
                break
        if duplicate_of is None:
            kept.append(row)
    return {"threshold": threshold, "max_rows": max_rows, "clusters": clusters, "kept_count": len(kept), "input_count": len(passed)}, kept


def _aligned_corr(a: pd.Series, b: pd.Series, max_rows: int = 20000) -> float | None:
    frame = pd.concat([a.rename("a"), b.rename("b")], axis=1).dropna()
    if len(frame) < 10 or frame["a"].nunique() <= 1 or frame["b"].nunique() <= 1:
        return None
    if len(frame) > max_rows:
        step = max(1, len(frame) // max_rows)
        frame = frame.iloc[::step].head(max_rows)
    return float(frame["a"].rank().corr(frame["b"].rank()))
