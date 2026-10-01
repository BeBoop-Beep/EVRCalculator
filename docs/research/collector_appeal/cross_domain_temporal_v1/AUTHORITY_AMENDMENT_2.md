# Collector Cross-Domain Temporal V1 — Authority Amendment 2

**Frozen before any temporal fold outcome was read.**

Direct execution of the Phase 1 SQL from Amendment 1 was blocked by the VM database role's
table privileges. No privilege changes were made and no temporal fold was evaluated.

The executable research reader is therefore the existing service-role RPC:

`get_pokemon_set_value_canonical_prices_as_of_v2_shadow`

Its current definition retains the pre-drift legacy identity chain used by Phase 1:

1. manual canonical-to-legacy link
2. parent Pokémon TCG API identity
3. variant API fallback
4. name + number fallback
5. TCGPlayer / Near Mint / USD V2 historical state

Unlike the drifted root RPC, it does **not** resolve identity through
`pokemon_canonical_card_market_prices_latest`.

This implementation is accepted for the experiment only if the frozen September 11 baseline
reproduces all 22 Set rhos and all global control statistics exactly at tolerance 1e-12.
If that lock fails, the harness stops before evaluating any temporal fold.

Candidate, dates, cohort, guardrails, bootstrap, and 4-of-5 decision rule remain unchanged.
No production mutation, privilege change, migration, or publication is permitted.
