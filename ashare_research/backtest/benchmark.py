from __future__ import annotations


def benchmark_status(mode: str | None, source: str | None) -> dict[str, object]:
    if not mode or not source:
        return {"benchmark_unavailable": True, "reason": "benchmark mode/source not configured"}
    return {"benchmark_unavailable": True, "reason": "formal CSI800 ex-finance total-return benchmark not confirmed in phase 2"}

