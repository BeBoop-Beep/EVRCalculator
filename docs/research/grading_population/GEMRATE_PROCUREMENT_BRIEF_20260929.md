# GemRate Partner API procurement brief

Date: 2026-09-29

## Intended use

inDex is evaluating GemRate as a normalized **population** provider, not as primary
graded-price authority. Proposed use covers exact Pokémon physical variants, population
by grader/grade/qualifier, dated internal snapshots, historical deltas and derived
research analytics. Population will be described as observed graded submissions, never
copies in existence.

No live ingestion should begin until commercial access and rights are approved in writing.

## Message to send

Subject: Partner API commercial terms and Pokémon population-data rights

Hello GemRate team,

We are evaluating the GemRate Partner API for an internal Pokémon grading-population
research program. We would use grader-normalized population data and stable identity
mappings; graded transaction pricing comes from a separate provider. Please answer the
following for the proposed commercial use:

1. What are the monthly and annual Partner API prices, including setup/minimum fees?
2. What request, burst and concurrency limits apply, and how are overages handled?
3. What limits or credit costs apply specifically to structured/simple card search?
4. Is the current card-population endpoint included, for which graders and fields?
5. Is daily population history included, or which plan/entitlement adds it?
6. Is 2022-01-01 the earliest history for every grader/card, and how are coverage gaps represented?
7. Is the population change feed included, and what retention/checkpoint guarantees apply?
8. Is bulk catalog access included, including the Pokémon catalog, and how often is it refreshed?
9. Does licensed coverage include PSA, Beckett/BGS, CGC and SGC with grade/qualifier detail?
10. What is current Pokémon-specific coverage by grader, era and language/edition, especially First Edition, Unlimited and Shadowless?
11. May we retain raw API responses and build an internal longitudinal history after termination?
12. May we create internal derived analytics (growth, deltas, gem rates and validation diagnostics)?
13. May we publicly display derived card-level population statistics, and at what granularity?
14. What raw-data redistribution, caching, retention or user-download restrictions apply?
15. What commercial attribution, linking, logo or “powered by” requirements apply?
16. Are universal and grader-scoped GemRate IDs stable for a card definition; how are merges, splits and corrections communicated?
17. What SLA, support, correction process and expected daily update window/cadence apply?

Please also provide the governing Partner API agreement/DPA and a sample response or
sandbox key if available. We will not ingest commercial data until terms are approved.

Thank you.

## Acceptance gates

- predictable cost under bounded Core Panel collection;
- explicit current/history/change-feed/catalog entitlements;
- exact-edition mapping coverage and correction semantics;
- internal response retention and historical storage permitted;
- internal derived analytics permitted;
- public display of derived statistics either permitted with clear limits or explicitly excluded;
- raw redistribution restrictions understood and enforceable;
- attribution, SLA, rate limits and ID stability documented.

## Decision

**NEED_MORE_INFORMATION** pending GemRate’s written commercial and rights response.
