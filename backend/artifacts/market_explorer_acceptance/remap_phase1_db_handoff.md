# Market Explorer Remap Phase 1 — DB/Ops handoff

## A. Live rows requiring inspection/remediation

Read-only inspection should identify maintained rows in `pokemon_market_explorer_query_cache`
whose `cache_kind = 'maintained'` and which are `failed`, are `building` past
`build_expires_at`, or have `computed_through` behind the accepted Explorer comparison date.
The production observations supplied with this task (Obtainable failed, another row building,
and stale single-axis rows) were not re-queried or modified by this source-only change.

## B. DB support required for cheap preflight

A single bounded, read-only RPC is required. Proposed contract:

`preflight_pokemon_market_explorer_query(p_set_ids uuid[], p_card_variant_ids uuid[], p_segment_ids text[], p_pokemon_ids bigint[], p_price_segment_ids text[], p_release_age_cohort_ids text[], p_comparison_as_of date)`

It should reuse the predicates owned by `get_pokemon_market_explorer_filtered_cohort_daily`
and return exactly one row: `matched_current_constituent_count`, `matched_set_count`,
`has_current_membership`, `has_usable_history`, and `canonical_through`. It must not return
constituent IDs or compute/chain-link an index. `has_usable_history` must mean enough published
observations/common cohort to construct an index, not merely that current members exist.

Without this DB primitive, application preflight would either duplicate the canonical SQL
filter semantics or run the expensive full cohort query; neither is acceptable. Consequently
the HTTP preflight route and `QUERY_EMPTY_NOW`/`QUERY_NO_HISTORY` classification are deferred.

## C. Expected source contract

Filtered specs never carry explicit IDs semantically. Explicit specs require 1–25 IDs and
canonicalize away scope, peer filters, and ranking. Explorer custom builds resolve through the
minimum of usable source publication and prepared Explorer `marketOverview.marketDate`.

## D. Tables/functions involved

- `pokemon_market_explorer_query_cache`
- `pokemon_explore_set_value_snapshot_latest`
- `pokemon_market_date_quality`
- `pokemon_market_explorer_card_daily_states_v2_shadow`
- `pokemon_market_explorer_card_daily_coverage_v2_shadow`
- `get_pokemon_market_explorer_filtered_cohort_daily`
- cache claim/renew/fail/finalize RPCs

## E. Safety constraints

Inspect with read-only credentials first. Do not clear an unexpired lease, overwrite a ready
payload, alter fingerprints, or rebuild more than the worker's bounded one-cache-per-process
limit. Remediation must use the existing lease/finalization RPC contract.

## F. Migration decision

A migration is required only for the compact preflight RPC above. No cache-state migration or
manual row rewrite is justified by the source audit.

## G. No-write verification

Compare the accepted Explorer date, V2 coverage, and maintained cache status/computed-through;
verify expired versus active leases by server time; run the health checker without a commit flag;
and confirm no DML/RPC mutation appears in the session audit logs.
