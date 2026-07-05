# AlphaGPT Project Status

Updated: 2026-07-05

## Current Mainline

AlphaGPT v2 first-round MVP search configuration, under the current narrow formula space and strict revalidation path, did not find any factor suitable for forward observation.

This shows the current MVP search configuration failed. It does not mean the direction of autonomous A-share factor discovery has been disproved.

Current restrictions:

- second-batch search is not started;
- no new formulas are generated;
- no backtest is running;
- forward data is not accessed;
- no trading advice is generated;
- no broker connection or automatic trading is enabled.

Current work:

- building a public-material-driven factor prior library;
- building a trading-operation strategy library;
- auditing source traceability before any seed factor can be considered for future research design.

## First-Round v2 Revalidation Summary

```text
fixed_formula_count: 94
development_passed_count: 94
selection_passed_count: 0
grade_a_count: 0
grade_b_count: 0
grade_c_count: 0
rejected_count: 94
final_shortlist_count: 0
recommended_factors: []
```

The previous B-rated full-history candidates did not survive the stricter segmented revalidation. They are not recommended for forward observation.

## Research Intelligence Summary

The initial public-source intelligence library is an unvalidated prior library, not an effective factor library.

Latest traceability audit:

```text
factor_prior_library_total: 20
factor_verified_source_candidate: 7
strategy_library_total: 20
strategy_verified_source_candidate: 8
firecrawl_live_collection_count: 0
```

Because Firecrawl live collection has not yet run and major community sources such as JoinQuant, RiceQuant, and BigQuant have not been actually collected, the next step should be source collection or seed-to-feature mapping design only. It must not automatically start a new AlphaGPT search.
