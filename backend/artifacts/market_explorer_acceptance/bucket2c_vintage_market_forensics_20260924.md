# Bucket 2C - Vintage Market Index forensics (2026-09-24)

Base: origin/develop b8e8b121d24ca1fa7bc3c0a673452512de000e80. Production was READ-ONLY (SELECT / catalog only via Supabase MCP). No code, data or index math was changed.
Reproduction SQL: `bucket2c_sql/` (counterfactual_series.sql, daily_history_decomposition.sql, top_moves_and_flip_share.sql). Replace SET_ID / START / END. Window audited: 2026-04-11..2026-09-19 (162 dates per set, 161 daily returns).

## Verdict: D - PHYSICAL IDENTITY DEFECT (in the SQL constituent reader, not the Python map)

Vintage roots with 1st-edition + unlimited variants (Jungle, Fossil, Team Rocket, Gym Heroes, Gym Challenge, Neo Genesis; Neo Discovery/Revelation/Destiny expected, not run) have ONE canonical_card_id but TWO economically distinct priced physical variants (1st-edition holo Snorlax ~$375 vs unlimited ~$153). The reader `get_pokemon_cards_daily_constituents` returns one row per (canonical card, date), and WHICH physical variant supplies that row flips from day to day. The Cards Market Index treats the flip as a price move. ~100% of squared daily index movement in Jungle/Fossil/Team Rocket is variant flips; genuine same-variant movement is at most a few percent per day.

## Exact mechanism
1. Route: `get_pokemon_cards_daily_constituents` -> v6_shadow -> v4_shadow -> `..._v2_hybrid_shadow` -> `..._v2_guarded`. Vintage sets have no row in `pokemon_set_market_constituent_v2_acceptance` (acc = null) and none of the vintage days is a canonical_root_days source, so they are served by `get_pokemon_cards_daily_constituents_legacy_shadow` -> `..._resolved_universe`.
2. `resolved_universe.canonical_variant_links` joins ALL card_variants of the canonical card's legacy card (any edition, holo/non-holo). `validity` is `lead(captured_at) OVER (PARTITION BY pokemon_canonical_card_id ORDER BY captured_at, observation_id)`: the most recently CAPTURED observation of ANY variant supersedes the previous one. Edition is not in the key. Winner = last scraped/inserted variant that day.
3. (Newer engine `v2_shadow` / `get_pokemon_set_value_canonical_prices_as_of_v2_shadow` has the same shape: rank = identity_rank, latest_observed_date desc, special_type, printing pref, pref table, card_variant_id; edition absent. `pokemon_canonical_card_variant_preferences_v2` has only 7 rows, 2 vintage.)
4. Example, Jungle Snorlax canonical 32576156: 2026-09-16 selected 1st-edition variant d374aca8 at $375.66; 2026-09-17 selected unlimited 8459b38e at $153.26. Both variants have identical observation ranges (..09-15, 09-17..); the one inserted last wins.
5. Python `build_constituent_observations` "last row wins" (pokemon_set_cards_market_analytics_service.py:250) is NOT the cause: the RPC returns exactly 1 row per (canonical, date) (10,368 rows = 64 canonical x 162 dates for Jungle), so the dedup is never exercised. The collapse is upstream in SQL.

## Documented contract (not UI copy)
`20260904173530_canonical_market_root_set_universe_v1.sql`: "Vintage roots with strong edition evidence split into first_edition/unlimited ... one preferred physical variant is selected per canonical card PER SCOPE." Live `pokemon_market_root_set_value_daily_history_v2_shadow` follows this and is STABLE (Jungle first_edition 2929-3070, unlimited 1094-1099 over 09-14..09-19). The standard-scope constituent reader does not follow it. Standard Set Value (`pokemon_set_value_daily_history`, value_scope standard) equals the constituent sum exactly (1895.49, 2161.59, 1527.58, 2074.08, 2209.94) so Set Value has the SAME edition-mixing volatility: Set Value, Index and Constituents agree with each other but violate the edition-split contract. Contract mapping: production behaves like neither (A) one representative price per card number (representative flips) nor (B) every distinct printing nor (C) an edition scope.

## Counterfactuals (research only, never published). 161 daily returns
A = production identity (reproduces prepared min/max/last exactly). B = card_variant_id of prod-selected row as identity. C_1st / C_unl = fixed edition variant per canonical card priced as-of from events (NM, USD, TCGPlayer). C_unl has 147 returns because unlimited prices begin later.

| Set | Series | max abs 1D % | sd % | >10% days | >20% days | end idx |
|---|---|---|---|---|---|---|
| Jungle | A | 43.54 | 13.63 | 62 | 21 | 87.17 |
| Jungle | B | 8.47 | 0.96 | 0 | 0 | 116.90 |
| Jungle | C_1st | 4.31 | 0.63 | 0 | 0 | 121.08 |
| Jungle | C_unl | 1.64 | 0.35 | 0 | 0 | 115.46 |
| Fossil | A | 72.76 | 15.89 | 73 | 37 | 95.16 |
| Fossil | B | 15.94 | 1.50 | 1 | 0 | 135.67 |
| Fossil | C_1st | 9.96 | 1.27 | 0 | 0 | 129.01 |
| Fossil | C_unl | 1.30 | 0.29 | 0 | 0 | 119.99 |
| Team Rocket | A | 36.45 | 10.91 | 55 | 15 | 89.06 |
| Team Rocket | B | 26.57 | 2.35 | 1 | 1 | 106.99 |
| Team Rocket | C_1st | 14.45 | 1.47 | 1 | 0 | 112.35 |
| Team Rocket | C_unl | 0.89 | 0.19 | 0 | 0 | 118.24 |
| Gym Heroes (control, affected) | A | 42.48 | 11.38 | 54 | 14 | 77.78 |
| Gym Heroes | B / C_1st / C_unl | 5.10 / 5.10 / 2.30 | 0.79 / 0.76 / 0.35 | 0 | 0 | 120.39 / 123.66 / 129.47 |
| Base (single variant per canonical) | A = B | 3.37 | 0.67 | 0 | 0 | 137.27 |

Prod A is not merely noisy: it ends 87 while every stable identity ends 106-135, i.e. the direction of the vintage indices is wrong, not only their volatility. (D) source-exclusion and (E) churn-exclusion counterfactuals are moot: source changes = 0 and membership is static (below). C_1st for Fossil/Team Rocket still shows 10-14% single days; those are same-edition price events and should be examined separately (not explained here).

Controls run 2026-06-01..09-19: Neo Genesis A max 47.76%, sd 12.3, 5243 flips (affected); Gym Challenge max 23.51%, sd 8.07, 6522 flips (affected); Base Set 2 max 2.94%, 0 flips; Obsidian Flames (modern) max 1.90%, 0 flips. The artifact is limited to canonical cards with several priced variants, not all vintage sets and not modern sets.

## Per-set findings (A series)
| Set | canonical / variants selected over window | days with flips | first flip | flip share of sum of squared returns | source changes | max abs move when 0 flips | max same-variant contribution (pp) |
|---|---|---|---|---|---|---|---|
| Jungle | 64 / 128 | 141 of 161 | 2026-04-25 | 1.001 | 0 | 0.34% | 4.10 |
| Fossil | 62 / 124 | 140 of 161 | 2026-04-25 | 0.996 | 0 | 3.16% | 4.16 |
| Team Rocket | 83 / 166 | 141 of 161 | 2026-04-25 | 1.011 | 0 | 0.14% | 17.83 (2026-06-21 example; see note) |

Before 2026-04-25 all selected rows are 1st-edition and the Jungle index is flat 100.0-100.8. From 2026-04-25 unlimited observations begin and the last-captured tiebreak starts alternating (34 of 64 Jungle cards flip that day: -35.6%). Days with 0 flips are exactly the days the index barely moves (carried prices age 1-2 days).

## Extreme move classification (top 10 per set; flips = canonical cards whose card_variant_id changed vs D-1, f2u = 1st->unlimited, u2f = unlimited->1st; contribution in index percentage points)
Allowed labels only. Real market movement? No for all. Authority artifact? Yes for all. Confidence: high (arithmetic decomposition exact; flip pp + same-variant pp = total).

| Set | Date | Move % | flips (f2u/u2f) | flip pp | same-variant pp | Primary | Secondary |
|---|---|---|---|---|---|---|---|
| Jungle | 2026-07-16 | +43.54 | 28 (13/15) | +43.50 | +0.04 | VARIANT_SWITCH | none |
| Jungle | 2026-07-02 | +38.04 | 36 (16/20) | +37.85 | +0.19 | VARIANT_SWITCH | none |
| Jungle | 2026-09-08 | +37.88 | 31 (12/19) | +38.14 | -0.25 | VARIANT_SWITCH | none |
| Jungle | 2026-04-29 | +37.22 | 36 (14/22) | +37.24 | -0.02 | VARIANT_SWITCH | none |
| Jungle | 2026-09-18 | +35.78 | 36 (16/20) | +35.78 | 0.00 | VARIANT_SWITCH | none |
| Jungle | 2026-04-25 | -35.63 | 34 (34/0) | -35.34 | -0.28 | VARIANT_SWITCH | none |
| Jungle | 2026-07-11 | +31.96 | 35 (14/21) | +31.90 | +0.07 | VARIANT_SWITCH | none |
| Jungle | 2026-06-08 | +30.13 | 37 (15/22) | +30.16 | -0.03 | VARIANT_SWITCH | none |
| Jungle | 2026-09-17 | -29.33 | 39 (21/18) | -29.26 | -0.07 | VARIANT_SWITCH | none |
| Jungle | 2026-05-31 | +27.86 | 26 (9/17) | +27.53 | +0.33 | VARIANT_SWITCH | none |
| Fossil | 2026-09-07 | +72.76 | 34 (16/18) | +72.65 | +0.11 | VARIANT_SWITCH | none |
| Fossil | 2026-09-06 | -41.12 | 32 (16/16) | -41.16 | +0.04 | VARIANT_SWITCH | none |
| Fossil | 2026-06-23 | +40.09 | 32 (16/16) | +39.87 | +0.22 | VARIANT_SWITCH | none |
| Fossil | 2026-05-03 | +36.86 | 38 (14/24) | +36.94 | -0.07 | VARIANT_SWITCH | none |
| Fossil | 2026-08-14 | +36.50 | 27 (11/16) | +36.45 | +0.05 | VARIANT_SWITCH | none |
| Fossil | 2026-07-06 | +36.20 | 41 (15/26) | +36.36 | -0.16 | VARIANT_SWITCH | none |
| Fossil | 2026-06-04 | +33.48 | 33 (10/23) | +33.22 | +0.26 | VARIANT_SWITCH | none |
| Fossil | 2026-07-10 | +31.95 | 32 (13/19) | +31.92 | +0.03 | VARIANT_SWITCH | none |
| Fossil | 2026-09-02 | -31.48 | 35 (17/18) | -31.49 | 0.00 | VARIANT_SWITCH | none |
| Fossil | 2026-09-03 | +29.53 | 29 (11/18) | +29.48 | +0.05 | VARIANT_SWITCH | none |
| Team Rocket | 2026-05-25 | +36.45 | 36 (18/18) | +36.40 | +0.05 | VARIANT_SWITCH | none |
| Team Rocket | 2026-05-12 | +33.68 | 46 (21/25) | +33.69 | 0.00 | VARIANT_SWITCH | none |
| Team Rocket | 2026-08-21 | +25.39 | 38 (20/18) | +25.18 | +0.22 | VARIANT_SWITCH | none |
| Team Rocket | 2026-08-26 | +24.66 | 40 (16/24) | +24.58 | +0.09 | VARIANT_SWITCH | none |
| Team Rocket | 2026-08-24 | +24.24 | 45 (25/20) | +24.27 | -0.02 | VARIANT_SWITCH | none |
| Team Rocket | 2026-08-09 | -24.11 | 41 (25/16) | -24.04 | -0.06 | VARIANT_SWITCH | none |
| Team Rocket | 2026-06-18 | +21.99 | 44 (19/25) | +22.01 | -0.02 | VARIANT_SWITCH | none |
| Team Rocket | 2026-05-24 | -21.64 | 39 (20/19) | -21.65 | +0.02 | VARIANT_SWITCH | none |
| Team Rocket | 2026-06-21 | +21.37 | 40 (15/25) | +23.08 | -1.71 | VARIANT_SWITCH | none |
| Team Rocket | 2026-08-16 | +21.36 | 35 (14/21) | +21.32 | +0.04 | VARIANT_SWITCH | none |
| Base | 2026-04-16 | +3.37 | 0 | - | +3.37 | REAL_PRICE_MOVE (unverified beyond zero flips/zero source change) | none |
Base other listed moves (06-03 +2.69, 07-14 +2.48, 07-18 +2.24, 07-17 -2.19) are the same class: single variant per canonical, 0 flips.

Note: Team Rocket "max same-variant contribution 17.83pp" is a same-variant price event on some day that this pass did not isolate (not in top-10 dates). It is a candidate real/stale-to-fresh repricing and is listed as UNKNOWN pending a follow-up query.

## Other candidate causes
- B/C/D (edition and holo switching): B = PROVEN mechanism (1st-edition <-> unlimited). C Shadowless: not applicable to Base root (Base has one edition=null variant per canonical; Base Shadowless is a separate set "Base Set (Shadowless)", 102 cards, 1st/unlimited variants; not audited). D Holo/Non-Holo: each canonical here has one printing type; not the driver in these sets.
- E source switching: DISPROVED. TCGPlayer is the only source (sources per date = 1; changes vs D-1 = 0).
- F membership churn: DISPROVED. Row count/canonical count constant every date (64/62/83); common cohort always 100%; no entrants/exits.
- G root/subset expansion: not a factor (no cohort change).
- H canonical identity collision in the Python map: DISPROVED as direct cause (1 row/canonical/date already).
- I card_variant_id instability: this IS the mechanism (selected id changes daily), but ids themselves are stable.
- J chain reset: DISPROVED. chain_segment_id = 0 for every prepared row; the cohort never breaks so no reset is possible.
- K missing/returned observations: only carried-forward days (0 flips, ~0% move, age 1-2 days), e.g. Jungle 06-25/26, 07-01, 07-08.
- L reconstruction error: prepared history equals independent recomputation from the live reader.

## Prepared-vs-Set-page parity
Prepared `pokemon_market_explorer_prepared_serving_history_v1` vs an independent recomputation of the Set-page algorithm (same RPC + chain-linked common-cohort math, build_chain_linked_history) for the four primary sets: 162/162 matching dates each, 0 prepared-only, 0 recomputed-only, max abs index diff 0.0000, chain segments all 0. Not a prepared publication defect. (The Set-page HTTP endpoint itself was NOT called - no servers started; parity is at algorithm+constituent level, the same code path.)

## NULL tracked_value root cause (separate)
`pokemon_market_root_set_value_daily_history_v2_shadow` has no market_scope='standard' rows for edition-split roots. Jungle/Fossil/Team Rocket/Gym Heroes have scopes first_edition (avg coverage 97.5%) and unlimited (88.8%), 161 dates each 2026-04-07..09-22. Base has first_edition/shadowless/unlimited with coverage ~0.3/0/0% because Base's variants are edition=NULL (fail-closed by design). Base Set 2 has standard, 100% coverage, and a tracked value. Classification: wrong market_scope / root-edition mismatch by design (edition_split profile), not a publication join or retention bug. No fix attempted: choosing which edition scope defines "tracked value" is a basket-semantics decision.

## Blocked / not done
- Nothing was blocked by the permission classifier. No production writes attempted.
- Not run: Neo Discovery/Revelation/Destiny, full daily CSVs saved to files (inspected in-session for Jungle; Fossil/Team Rocket inspected via top-10/aggregates), per-date variant-switch rows with old/new price for every switch (counts reported; queryable with daily_history_decomposition.sql), Set-page HTTP parity, Base Shadowless set audit, isolation of Team Rocket's 17.83pp same-variant day.
- No regression tests added: the fix is not implemented (basket semantics), and tests must not pin the defective behavior.

## Remediation proposal (REVIEW REQUIRED - changes what constitutes the vintage basket; NOT implemented)
1. Contract: an edition-split vintage Market Index constituent is (canonical_card_id, market_scope) with one fixed physical edition per scope, consistent with the 20260904173530 root universe. Decide product default for the "Team Rocket Market Index" (likely unlimited/standard scope, with 1st-edition as its own market) - owner decision.
2. Fix in SQL (`resolved_universe` legacy path and `v2_shadow` ranking): filter canonical_variant_links to the scope's edition (or make edition the leading rank key) before the `lead(captured_at)` partition; partition validity by card_variant_id or (canonical, scope).
3. Affected: Jungle, Fossil, Team Rocket, Gym x2, Neo x4 (any canonical with >1 priced edition variant). Base, Base Set 2, modern unaffected. Current data affected too (latest 4 Jungle rows swing 85 -> 60 -> 82).
4. Historical reconstruction REQUIRED for prepared history (all vintage-affected market keys), Set Value 'standard' history for these sets, Breadth, Explorer snapshot/rankings that read them. Blast radius: Set Value, Market Index, Breadth, Explorer, market snapshot, rankings.
5. Validation oracle: recomputed C_* series above (max 1D < 5% Jungle, sd < 1%) and equality with root_set_value_daily_history_v2_shadow scope values per date.
6. Rollback: keep current reader as a shadow function, publish a new prepared generation, cut over via generation pointer.
