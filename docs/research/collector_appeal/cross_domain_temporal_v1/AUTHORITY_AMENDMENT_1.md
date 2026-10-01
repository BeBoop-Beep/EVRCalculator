# Collector Cross-Domain Temporal V1 — Authority Amendment 1

**Frozen before any temporal fold outcome was read.**

## Reason

Phase 1 successfully reproduced the 2026-09-11 control with zero error on all 22 Sets using
`get_pokemon_market_root_standard_card_prices_as_of_v2`.

After that successful replay, production migration
`20260929180921_root_standard_history_stable_identity_v3` replaced the implementation behind
the same RPC name. The temporal harness then failed its baseline lock before reading any of the
five preregistered temporal folds:

- 4,331 / 4,331 baseline rows were still priced.
- 21 / 22 Set rhos remained exact.
- Ascended Heroes changed by 0.08590552156590342 rho.
- Therefore the run was correctly classified
  `ANCHOR25_TEMPORAL_VALIDATION_INVALID`.
- No temporal fold metrics were evaluated.

Inspection shows the new RPC resolves a card first through the *current*
`pokemon_canonical_card_market_prices_latest.legacy_card_id`. That means a historical market
date can change when current canonical-to-legacy identity linkage changes. This violates the
temporal experiment's required measurement invariance.

## Corrected frozen outcome authority

For this research experiment only, the historical outcome reader is now pinned to the exact
SQL semantics that produced the successful Phase 1 replay, as committed in:

`supabase/migrations/20260928204424_market_explorer_root_standard_frozen_roster_v2.sql`

Specifically, identity resolution is frozen to:

1. manual canonical-to-legacy identity link, rank -1
2. parent API identity, rank 0
3. variant API identity, rank 1 when parent API identity is absent
4. name + number identity, rank 2 when the prior API identities are absent

and then the same TCGPlayer NM/USD price-event interval selection and printing preference logic
used in Phase 1.

The mutable production RPC is no longer used for the temporal experiment. The SQL is executed
read-only through PostgreSQL and creates no object, table, function, row, or migration.

## What does not change

Nothing else in the preregistration changes:

- candidate remains ANCHOR25 only
- dates remain 2026-09-14, 09-17, 09-20, 09-23, 09-26
- exact 4,331-card / 22-Set cohort remains fixed
- guardrails remain unchanged
- 4-of-5 decision rule remains unchanged
- 1,000 whole-Set bootstrap draws per valid fold remain unchanged
- production mutations remain forbidden

The baseline must again reproduce all 22 frozen September 11 Set rhos exactly before any temporal
fold is evaluated.

This amendment repairs a changed measurement instrument; it does not alter the hypothesis,
candidate, dates, cohort, metric gates, or decision rule.
