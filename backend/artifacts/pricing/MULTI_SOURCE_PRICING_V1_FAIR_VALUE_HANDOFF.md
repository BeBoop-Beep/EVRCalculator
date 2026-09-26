# Multi-source pricing V1: handoff contract for the Fair Value workflow

Policy `pokemon_multi_source_card_price_v1`, produced by the P6 daily pipeline. This is the stop boundary for the pricing chat: **nothing here is Fair Value**, and no Fair Value formula, scarcity premium or publication was implemented or wired.

## What may be consumed

Table `public.pokemon_multi_source_card_prices_v1` (service_role read only; RLS on; no anon or authenticated access; insert-only). One row per `(card_variant_id, condition_id, market_date, policy_version)`. Condition is always Near Mint (`4f8d1181-670e-4aea-937c-4d98d2e531a6`).

| Field | Meaning |
|---|---|
| `canonical_card_id`, `card_variant_id`, `condition_id`, `market_date` | Exact identity and America/Phoenix market date. eBay and TCGplayer are only ever compared on the same variant. |
| `selected_price`, `selected_price_source` | Exactly one provider value (`TCGPLAYER` or `EBAY_ACTIVE_ASK`), or null with `UNPRICED`. Never a blend. |
| `decision_state`, `decision_reason`, `policy_version` | Frozen states below. |
| `tcgplayer_price`, `tcgplayer_date`, `tcgplayer_age_days`, `tcgplayer_freshness_state` | Canonical TCGplayer authority read on the market date. FRESH ≤ 1 day, AGING 2–7, STALE ≥ 8, MISSING. |
| `ebay_price`, `ebay_market_date`, `ebay_seller_count`, `ebay_listing_count`, `ebay_depth_state`, `ebay_estimator_version` | Frozen `ebay_active_ask_lower3_seller_median_v1`. `ebay_price` exists only when depth is SUFFICIENT (≥ 5 distinct sellers). Depth is **that day's** depth; nothing is carried forward. |
| `ebay_estimate_id` | FK to `ebay_active_ask_price_estimates_v1`; the estimate carries the three selected asks and contributing evidence ids. |
| `source_ratio`, `source_difference_pct`, `source_agreement_state` | eBay ÷ TCG, (eBay − TCG) ÷ TCG, and AGREE / MODERATE_DISAGREEMENT / SEVERE_DISAGREEMENT / SINGLE_SOURCE_ONLY. |
| `input_fingerprint`, `decision_fingerprint`, `pipeline_run_id` | Provenance. The fingerprints are reproducible from the stored inputs; the run row holds the target manifest and receipt. |

Decision states: `TCGPLAYER_PRIMARY`, `TCGPLAYER_PRIMARY_EBAY_CORROBORATED`, `TCGPLAYER_PRIMARY_EBAY_MODERATE_DISAGREEMENT`, `TCGPLAYER_PRIMARY_SOURCE_DISAGREEMENT`, `TCGPLAYER_AGING_RETAINED`, `TCGPLAYER_STALE_RETAINED`, `EBAY_ACTIVE_ASK_FALLBACK`, `UNPRICED`. These are the frozen P5B names; they differ from the shorter names in the P6 brief and the brief allowed the frozen names to win.

## Semantics that must be respected

1. **eBay is active asks, not completed sales.** The estimate is the median of the three lowest seller-distinct landed asks (item price plus shipping, English, Near-Mint-compatible, fixed price). It is an ask-side quote, and it includes shipping while TCGplayer Market Price does not.
2. **Fresh TCGplayer stays primary.** eBay only corroborates or flags disagreement beside it.
3. **A missing TCGplayer NM price may use a SUFFICIENT eBay fallback** (`EBAY_ACTIVE_ASK_FALLBACK`), for the same resolved variant and only when today's evidence is SUFFICIENT.
4. **Stale and aging TCGplayer is retained, not replaced** (`*_RETAINED`). No stale-replacement rule exists in V1.
5. **No arithmetic blend and no calibration factor.** The table's checks make a blended `selected_price` unrepresentable.
6. **eBay coverage is sparse and fragile.** In the first production run 9 of 21 targets reached SUFFICIENT; the P5B study saw exactly 5 sellers on every sufficient card, so a card can flip SUFFICIENT → THIN → SUFFICIENT day to day. A missing row or a THIN state is not evidence about price.
7. **Disagreement is information, not an error.** Do not auto-correct either source.
8. **The table is sparse by design.** A row exists only for cards the eBay stage evaluated that day (about 20–130 cards per day within the 1,000-request cap). Absence of a row means "not evaluated today", not "no price"; canonical TCGplayer pricing remains the authority for every other card.
9. **This authority is not Fair Value.** Selected prices inherit each source's semantics and are not scarcity-, liquidity- or sale-adjusted.

## Known limits a consumer should plan for

- **Penny cards:** the frozen $1.51 shipping tolerance makes any absolute gap up to $1.51 read AGREE. In the first run a $0.39 TCG card against a $1.65 eBay estimate is labelled `TCGPLAYER_PRIMARY_EBAY_CORROBORATED` (+323%). For sub-$2 cards the agreement state carries little meaning.
- **Fallback prices are low-value so far.** The three fallbacks in the first run were $2.99, $3.49 and $15.00.
- **Identity gaps cannot be repaired.** About 572 of 813 missing canonical prices have no resolvable variant, so no source can price them; the selector never spends requests on them.
- **Six of 25 P5B paired cards have several NM-priced variants** (holo and reverse); eBay evidence is card-level and is attached to the resolver-selected variant.
- **Thresholds are provisional**, derived from 25 paired cards (freshness cut, agreement bands). Re-derive them from accumulated daily pairs before treating them as market truth.
- **History is one day** (2026-09-20) until the daily schedule is running (see the P6 report: the VM schedule is not yet installed).

## Related tables

`ebay_pricing_runs_v1`, `ebay_card_listing_evidence_v1`, `ebay_card_pricing_run_summary_v1` (P3 evidence and per-card depth diagnostics), `ebay_active_ask_price_estimates_v1` (SUFFICIENT estimates only; append-only, select and insert only), `pokemon_multi_source_pricing_runs_v1` (run state, manifest, receipt). Generic Price Storage and `pokemon_canonical_card_market_prices_latest` stay TCGPlayer-only and were not changed.
