# P5B policy freeze: `pokemon_multi_source_card_price_v1`

The name is unique in tracked files (repo-wide `git grep` found no prior use). Implementation: `backend/scripts/pokemon_multi_source_card_price_v1.py`; contract fingerprint `caf6acbf7e4b4e43b4491ef2b018122bb4cfcb8b254621f8b32c8bb8a70abdb6`. Evidence: [source calibration](MULTI_SOURCE_PRICING_P5B_SOURCE_CALIBRATION.md).

## 1. What is frozen

This is a **selection and fallback authority with no numeric blend**. The selected price is always exactly one provider value or absent.

| Contract | Frozen value | Basis |
|---|---|---|
| TCG freshness | FRESH ≤ 1 day; AGING 2–7; STALE ≥ 8; MISSING when no positive NM price | 99.02% of 19,813 priced cards are ≤ 1 day (daily scrape); 13-card 2–7 shoulder; 181-card ≥ 8 tail. The 8-day cut is a calendar-week judgment, not a natural break |
| eBay depth requirement | SUFFICIENT only (≥ 5 distinct eligible sellers, frozen P4C) with a resolved variant and estimator `ebay_active_ask_lower3_seller_median_v1` | Unchanged; THIN and INSUFFICIENT never price anything |
| Agreement bands | AGREE: \|Δ\| ≤ 8% or ≤ $1.51; MODERATE: ≤ 35%; SEVERE: > 35% | 8% = P75 and 35% = max of the estimator's own leave-one-seller-out shift on 25 cards (0.084, 0.348); $1.51 = P90 of shipping on eligible sub-$5 listings (n=76) |
| SINGLE_SOURCE_ONLY | one source usable | descriptive |
| Variant/condition | exact same `card_variant_id`, Near Mint; mismatch makes eBay unusable, never compared | P5B.2 |
| Numeric blend | **none** (`BLENDED` is not a valid source; enforced in code and by table checks) | §3 |

The agreement bands say *when automatic fusion would be unsafe*, not which source is right. The dollar tolerance means sub-$1.51 differences always read AGREE (e.g. $0.17 vs $0.99); that is a deliberate shipping allowance and blunts detection on penny cards.

## 2. Decision table

| Condition | `decision_state` | Selected |
|---|---|---|
| TCG fresh, no usable eBay | `TCGPLAYER_PRIMARY` | TCGPLAYER |
| TCG fresh, eBay SUFFICIENT, AGREE | `TCGPLAYER_PRIMARY_EBAY_CORROBORATED` | TCGPLAYER |
| TCG fresh, MODERATE | `TCGPLAYER_PRIMARY_EBAY_MODERATE_DISAGREEMENT` | TCGPLAYER |
| TCG fresh, SEVERE | `TCGPLAYER_PRIMARY_SOURCE_DISAGREEMENT` | TCGPLAYER (fusion refused, disagreement exposed) |
| TCG aging | `TCGPLAYER_AGING_RETAINED` | TCGPLAYER, flagged, no eBay override |
| TCG stale | `TCGPLAYER_STALE_RETAINED` | TCGPLAYER, flagged, no eBay override |
| TCG missing, eBay SUFFICIENT, variant resolved | `EBAY_ACTIVE_ASK_FALLBACK` | EBAY_ACTIVE_ASK (landed active-ask semantics) |
| Otherwise | `UNPRICED` | none |

"Fail closed" means eBay never overrides or blends and the disagreement is stored. It does not remove an existing TCGplayer price.

## 3. Candidate policies evaluated (P5B.7)

Evaluated on the 150-target development cohort (25 paired). No external ground truth exists, so "closest to TCGplayer" was not a criterion.

| Policy | Result | Decision |
|---|---|---|
| **A** TCG primary / eBay gap fill | Priced 130 of 150 (baseline 128); +2 eBay fills; 0 existing prices changed. Stale TCG retained (A does not remove prices) | **Adopted as the base** |
| **B** + stale eBay fallback | 4 stale/aging cards have a SUFFICIENT eBay estimate; B would replace 3 existing prices (the 4th is a SEVERE disagreement). Three of the four are under $5, where shipping dominates the comparison. No evidence which price is better | **Not adopted** (n=4, confounded, no ground truth). Stale TCG is retained and flagged instead |
| **C** agreement-gated blend | 11 fresh AGREE pairs; paired n=25 < 30 gate; no weights derivable | **Not evaluated numerically, rejected** (below gate; premium varies by value, so any fixed weight would import a value-dependent bias) |
| **D** calibrated eBay fallback | n=25 < 30; median ratio 1.50 (< $5) vs 1.09 (≥ $5) with non-overlapping IQRs | **Not implemented** (ratio unstable by price band) |

**Holdout (P5B.13): not applicable.** No numeric calibration or blend was proposed, and 25 pairs cannot support a grouped development/holdout split, so none was run. The frozen rules use no fitted parameter beyond the agreement percentiles above, which are themselves small-sample.

## 4. Provenance and derived-data rule

Every decision row stores both source values and dates, freshness, depth and seller counts, estimator version, agreement state, `input_fingerprint` (policy, market date, TCG price/date/variant, eBay price/date/variant/depth/counts/estimator fingerprint, condition) and `decision_fingerprint` (all row fields). Rows are deterministic and idempotent: rebuilding the cohort gives fingerprint `365ea0a9ad33587353bcf2c34597c81bfaf7a466f6d3dcdc4d1daade7eea7395` over 149 persistable rows. The combined result is a **derived authority**; nothing is written into provider observation, event, current or estimate tables, and `pokemon_canonical_card_market_prices_latest` is untouched.

## 5. Shadow authority (P5B.10)

Migration `20260921010000_p5b_multi_source_card_prices_shadow_v1.sql`, byte-identical in `backend/db/migrations` and `supabase/migrations`: table `public.pokemon_multi_source_card_prices_v1`, unique on variant, condition, market date and policy version. Table checks enforce: selected price and source are both null or both set; `UNPRICED` iff no price; the selected price equals the selected provider's price (no blend); eBay fill only when TCG is null and depth is SUFFICIENT; only the frozen states. RLS is on; nothing is granted to anon or authenticated; `service_role` gets select and insert only. No view, function or consumer changes.

**Update (P6): applied to production** after the P6 amendment (adds `pipeline_run_id` and `ebay_estimate_id`); see the P6 report. As of P5B it was not yet applied, and it was validated inside a rolled-back production transaction: 3 valid rows inserted; a blended price, a THIN eBay fallback and a duplicate day were each rejected; anon and authenticated were denied; UPDATE and DELETE were denied for service_role. Production afterwards: table absent, 6 estimate rows, 0 non-TCG current rows, no new migrations. The 149 cohort rows are in `p5b_shadow_authority_cohort_rows.json` and are not persisted. The cohort's 27 SUFFICIENT eBay estimates (8 from P4, 19 from P5B) are local artifacts, not rows in `ebay_active_ask_price_estimates_v1`.

**Finding outside P5B scope (not changed):** Supabase's default privileges gave `service_role` UPDATE and DELETE on the existing `ebay_active_ask_price_estimates_v1` table. The P4C document describes an insert-only grant, but production shows all three privileges. The new migration revokes them explicitly. The P4C table should be fixed by its owner (`revoke update, delete ... from service_role`).

## 6. Gap-fill (P5B.11)

Missing canonical prices (approved `main` and `promo` cards): **813**, of which **572 have no resolvable variant** (513 promos, 59 main) and cannot be priced from any source until identity is fixed. **241 are resolvable** (216 main, 25 promo).

Sample of 22 missing cards (21 with a resolved variant): 2 SUFFICIENT (9.5%, Wilson 95% CI 2.7–28.9%), 1 THIN, 18 with no usable evidence. Indicative recovery on the 241 resolvable cards: about 23 (CI 6–70). That projection is weak: the sample is 21 cards.

- Both recoveries are ME: 30th Celebration Illustration Rares ($14.99 and $12.29, 5 sellers each). That set holds 120 resolvable cards with no TCGplayer price at any condition; 2 of the 3 sampled recovered. This is the main real gap eBay repairs. The dollar values are modest.
- The other 19 sampled cards with resolved variants recovered none: 18 outside ME: 30th Celebration (Skyridge, Aquapolis, Neo Revelation, POP, Holon and similar, mostly vintage) and one ME: 30th card. eBay supply is thin there.
- Missing cards by era (main and promo): Sword and Shield 304 (SWSH Black Star Promos, none resolvable), Other 132, EX 115, DP 56, SM 53, Base/WOTC 53, XY 30. The resolvable main gaps include 58 higher-rarity cards; the only sampled recoveries are two Illustration Rares.
- 50 missing main and 25 missing promo cards do have TCGplayer prices at non-NM conditions; a condition-adjusted fallback is a separate question and is not evaluated.

eBay repairs few meaningful gaps: nearly all the missing count is promo identity, which eBay cannot fix.

## 7. Downstream impact shadow analysis (P5B.12)

Analysis only; no simulation, EV or Set Value was recomputed or published.

- **Newly priceable cards:** 2 of 22 sampled missing cards; about 6–70 of the 241 resolvable gaps. Existing prices change: **0** (fallback fills only).
- **Opening simulation / sealed EV inputs:** 22 sets hold opening-eligible unpriced main cards (155 cards; 59 identity-unresolved, 96 resolvable). The largest are the EX Trainer Kit sets (Minun and Plusle 27 cards each, Latias and Latios 22 each; about half resolvable). Vintage supply is thin, so recovery there is unlikely.
- **Set Value constituents:** ME: 30th Celebration is the set most likely to gain inputs (120 resolvable unpriced cards). The 538 unpriced promos gain almost nothing.
- **Chase cards:** eBay reached SUFFICIENT on only 4 of 38 targets ≥ $50 (10.5% vs 29% below $5), so it will rarely corroborate or fill high-value cards.
- **Material changes from fallback:** none to existing prices. Fallback values are ask-side landed prices and run above sales-based TCG values at low price points; consumers should read `selected_price_source`.
- **Large disagreements on important cards:** Evolving Skies Rare Rainbow $312.61 vs $419.43 (+34.2%, MODERATE, at the SEVERE boundary); Chilling Reign Rare Rainbow $39.48 vs $48.75 (+23.5%); Gym Challenge Rare $19.46 vs $13.35 (−31.4%). No SEVERE case occurred at ≥ $20 in this sample.

## 8. Tests

`backend/tests/unit/scripts/test_pokemon_multi_source_card_price_v1.py`: 29 tests, plus the existing P4C, P4A, P4B and P5A contract suites. Combined run: **41 passed**. Coverage: freshness and agreement classification; fresh-primary; missing plus SUFFICIENT fallback; THIN and INSUFFICIENT never fill; severe and high-value disagreement; stale and aging retained; exact-variant join and mismatch; no numeric blend across a 216-case grid; determinism and fingerprints; idempotent, order-independent shadow build; identity-unresolved not persisted; frozen contract; P4C estimator replay fingerprint unchanged; module never touches the database or provider tables; migration is shadow-only, insert-only, with no view or canonical change; migration trees identical; cohort banding and deterministic selection. Not covered by automated tests: the rolled-back production validation in §5 (manual) and a live daily builder, which does not exist yet.

## 9. P6 readiness

Ready for daily automation on the conservative policy, with these carried-forward conditions:

1. **Sample is small.** 25 pairs (target 40, gate 30). No blend or calibration is claimed; agreement bands and the 8-day stale cut are provisional and should be re-derived from accumulated daily pairs.
2. **Apply the shadow migration and persist P5B eBay estimates** (the estimator table holds 6 rows) before any builder runs; not done here.
3. **SUFFICIENT is fragile.** Every paired card sits at exactly 5 sellers, so eBay coverage will flicker day to day.
4. **Fallback prices are ask-side.** No promotion into public or canonical pricing was made or is implied.
5. **Fix the P4C table grants** (§5).
6. **Identity is the dominant gap.** 572 of 813 missing cards need variant resolution, not more pricing.

No public pricing, canonical pricing, provider table or P4C estimator was changed. No commit or push was made. Git status shows only P5B-owned files, the P5A report edit from the previous task, and a local `ebay_browse_daily_usage.sqlite3` call ledger that should not be committed.

MULTI_SOURCE_PRICING_V1_FROZEN_READY_FOR_DAILY_AUTOMATION
