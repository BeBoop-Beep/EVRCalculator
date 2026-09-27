# RIP Benchmark V1 — Sitewide Closure

## Public contract

- Public scale: 0–10, with 5.0 as the modeled benchmark baseline.
- Canonical Set reference: Pokémon-wide eligible Set cohort.
- Product Overall and Financial reference: exact product-family mean.
- Era reference: Pokémon-wide Set benchmark.
- Rank identifies ordering; rank #1 identifies the leader. A score of 10.0 is only the upper presentation endpoint.
- Public Set headlines are an anonymous-safe, current-only narrow contract.
- Detailed Benchmark current and history are Index Plus.
- Product Benchmark is Index Plus.
- Card Collector Appeal, Chase Efficiency, scarcity, and treatment/prestige are separate card intelligence constructs.
- Active model family at closure: Financial RIP V4 / Overall RIP V12. Financial V5 and Overall V14 remain inactive.

## Homepage authority

The public Homepage summary joins its existing narrow Set identity and opening-economics projection to the current published Set Benchmark Overall rows on the server. Canonical Benchmark rank determines ordering. It does not use `setRipV1`, legacy tiers, or rounded-score ordering, and it performs no per-Set requests.

- Before: `setRipV1` score/rank/tier selected and described the Homepage winner.
- After: current published Set Benchmark Overall rank selects the winner; its score is shown as `X.X / 10` with Above/At/Below Pokémon benchmark language.
- Request architecture: one public, session-invariant Homepage summary request; the server performs one existing narrow snapshot read and one bounded Set Overall-row read. The frontend retains only concurrent in-flight joining, so a completed request cannot keep an older Benchmark generation warm.

## Production read-only acceptance

Checked against production-backed reads on 2026-09-27 without writes:

- Current Benchmark publication: `b4c0cd59-50bf-5caf-a744-9db22e5fce86`.
- Benchmark market/source date: `2026-09-25`.
- Current Rankings publication: `f17135e9-57c0-4720-955c-0e5e8637662b`; source market date `2026-09-26` (simulation source `2026-09-25`).
- Active authority: Financial RIP V4 / Overall RIP V12; Financial V5 / Overall V14 inactive.
- Homepage-selected #1: Temporal Forces, matching public Set-headline Overall rank #1 (score 7.338773636363636, cohort 22).

## Residual legacy audit

- `ACTIVE_BENCHMARK_CORRECT`: current Rankings, Homepage, Set detail, Set Analysis, Overview/Insights, Era Rankings, Product Rankings, and Product detail presentations.
- `LEGACY_ROLLBACK_ONLY`: compatibility projections, old score formatters, tier primitives, and retained model identifiers used for rollback/audit support.
- `DEAD_UNREACHABLE`: alternate landing components not imported by `frontend/app/page.js`.
- `SEPARATE_NON_BENCHMARK_CONSTRUCT`: card-level intelligence and deeper diagnostic/economic measurements.
- `STILL_USER_VISIBLE_GAP`: none at closure.

`PublicRipTierInfo` remains compatibility infrastructure only. No active Benchmark V1 headline invokes it, and no new Benchmark tier system was introduced.
