# inDex Market Microstructure + Grading Research Program
Date: 2026-09-29

## Decision

Do not re-fit or promote inDex Fair Value yet.

First close the missing market-evidence domains:
1. durable completed-sale history,
2. fixed-panel active offered supply,
3. graded sale pricing,
4. grading population / grading velocity,
5. condition normalization,
6. validated market-microstructure primitives.

Only after those domains have stable, point-in-time-safe authorities should Fair Value research restart.

This program intentionally does not reproduce Collectrics' HYPE score, Demand Pressure formula, thresholds, UI, or ended-listing inference. The Collectrics audit is a prior-art / product benchmark that helps identify useful questions. inDex will use its own data authorities, formulas, names, controls and validation.

Reference:
- docs/research/index_fair_value/EXTERNAL_BENCHMARK_COLLECTRICS_GAP_AUDIT_20260929.md

---

# Current inDex evidence audit

## Raw / canonical pricing

Strong existing authority:
- canonical Near Mint TCGplayer card price history,
- Price Storage V2 ranges/events,
- exact physical variant identity,
- edition-aware First Edition / Unlimited / Shadowless contracts,
- set/root-set identity,
- Collector Appeal V7,
- Pull Scarcity,
- Treatment V3,
- lifecycle / era metadata.

These remain independent authorities.

## PkmnPrices completed sales

Existing DB:
- pkmnprices_ebay_sold_evidence_v1
- pkmnprices_card_identity_v1
- pkmnprices_sold_sync_state_v1
- pkmnprices_sold_runs_v1

Live state at this audit:
- 2,702 completed-sale rows,
- 12 canonical cards,
- sold-date span 2024-05-31 through 2026-09-28,
- all 2,702 current rows are ungraded because the current collector explicitly requests graded=false,
- 12 provider identities.

Provider capability is broader than current code:
- eBay sold endpoint supports graded=true / false / both,
- grader filters,
- grade filters,
- cursor backfill,
- ingested_at incremental checkpointing,
- grade qualifiers distinguish special tiers such as CGC Pristine and BGS Black Label in current provider docs.

Current code gap:
- PkmnPricesClient.ebay_sold_page does not expose grader or grade parameters,
- normalizer does not persist grade_qualifier,
- historical collector intentionally only asks for ungraded rows.

Therefore graded transaction evidence is a code-contract gap, not a new-source gap.

## Active eBay offered supply

Existing DB:
- ebay_pricing_runs_v1
- ebay_card_listing_evidence_v1
- ebay_card_pricing_run_summary_v1
- ebay_active_ask_price_estimates_v1
- multi-source pricing shadow tables

Live state:
- 7 completed evidence runs,
- 4,795 persisted active-listing evidence rows,
- 1,870 per-card run summaries,
- 1,104 distinct cards have at least one evidence row.

Recent scale:
- 2026-09-27: 385 cards / 1,272 stored asks,
- 2026-09-28: 380 cards / 1,278,
- 2026-09-29: 376 cards / 1,315,
- September 29 source run considered 44,888 raw search hits across 494 targets.

Important limitation:
- current production target selection is adaptive/rotating,
- 952 of 1,104 cards have only one observed evidence day,
- only 152 cards have >=2 days,
- only 84 have >=3,
- only 7 have >=5,
- 489 listing identities have been observed on >=2 dates.

Conclusion:
This archive is already useful for point-in-time supply / pricing evidence, but it is not yet a valid general listing-arrival / listing-disappearance panel. Absence can mean "not targeted today," not "listing ended."

## Old graded-card schema

Existing tables:
- grading_companies
- graded_card_variants
- graded_card_variant_price_observations

Live state:
- 5 grading-company rows, including duplicate PSA rows,
- 1 graded_card_variants row,
- 1 graded price observation,
- source = manual_test,
- observation date = 2026-04-07.

Conclusion:
This is scaffolding/test residue, not a usable grading authority. Do not build research conclusions on it. A new normalized grading research authority may reuse compatible identity concepts but should not inherit this table as truth.

---

# External resource audit

## PkmnPrices — use immediately

Current Pro plan already provides:
- 20,000 credits/day,
- individual eBay sold transactions,
- graded + ungraded filtering,
- grader and grade,
- grade qualifier in current sold schema,
- cursor-based retained history,
- TCGplayer live listings,
- Cardmarket live listings,
- exact card/provider identity mapping.

TCGplayer active listing endpoint:
- English listing filters,
- exact condition and printing filters,
- seller metadata,
- quantity,
- item and shipping price,
- snapshot_at freshness,
- up to the 500 cheapest in-stock English listings per product.
- Data are active offers, not sales.

This gives inDex an inexpensive exact-identity supply source without consuming the existing eBay Browse quota.

Recommended use:
- completed-sale ledger,
- graded-sale ledger,
- fixed-panel TCGplayer NM offered-supply snapshot,
- optional Cardmarket cross-market supply snapshot.

Do not reinterpret eBay sold comps as TCGplayer market prices.

## GemRate Partner API — preferred grading-population candidate

Public API documentation states:
- unified PSA, Beckett, SGC and CGC population data,
- 10M+ distinct cards tracked,
- 1.8M+ universally matched cards,
- daily updates,
- card population endpoint with grade distribution and gem rate,
- historical population available at daily granularity beginning 2022-01-01,
- population change feed,
- structured card search,
- bulk catalogs,
- universal GemRate IDs.

Historical/change-feed/catalog access is not included in basic plans.
Commercial pricing is not public; GemRate asks prospective partners to contact them.

Recommended use if commercial terms are acceptable:
- primary normalized grading-population authority,
- grade distribution,
- gem rate,
- population growth / grading velocity,
- cross-grader mappings,
- historical point-in-time population.

Do not start automated production ingestion until API/commercial permission and price are resolved.

## Official grader resources — validation, not scraping authority

PSA:
- official Population Report,
- official PSA Price Guide,
- official Auction Prices Realized / CardFacts.
PSA states population is a count of cards graded and breaks it down by grade, and separately cautions that population must be interpreted in context because submission behavior is selective.

CGC:
- public Population Report with card/set population and grade breakdown.
- CGC explicitly says census/population is informational and not itself an indicator of value or rarity.

Beckett:
- BGS Population Report exists,
- some search functionality is subscription-gated.

Recommended use:
- source semantics,
- manual/spot validation of GemRate mappings and counts,
- not an unapproved scraper.

## PriceCharting — optional independent price validation only

Current Legendary plan:
- $49/month,
- API access and daily bulk CSV,
- current graded price fields,
- cards expose Graded 9 and PSA 10-style price fields,
- no historic prices or historic sales via API.

Decision:
Do not buy initially. PkmnPrices true graded sales are more informative for our planned research. Reconsider only if we need an independent current graded-price reference after the primary pipeline is built.

---

# Research panel design

The microstructure research must use a fixed panel.

## Core Panel V1

Primary panel:
- reuse the deterministic balanced Fair Value sold-signal cohort,
- frozen F1 fingerprint,
- seed 20260929,
- roughly 30 cards per seven price bands (about 207 mapped cards in the prior run),
- fixed canonical + physical variant identity.

Purpose:
- longitudinal supply / sales research,
- direct comparability to prior Fair Value research,
- controlled price-band coverage,
- no daily target-selection drift.

## Diagnostic panels

Keep separate from Core Panel:
- vintage edition panel for First Edition / Unlimited / Shadowless identity stress,
- high-value/chase stress panel,
- optional grading-heavy panel after first graded-sales coverage audit.

Diagnostic panels do not silently enter the main model cohort.

---

# Bucket A — Foundation, identity and fixed-panel contracts

## Objective

Freeze the research universe and make graded/ungraded evidence representable before spending provider credits.

## Work

1. Freeze Core Panel V1 manifest:
   - canonical_card_id,
   - card_variant_id,
   - root_set_id,
   - provider_card_id when resolved,
   - TCGplayer product ID,
   - set/era,
   - price band,
   - source F1 fingerprint,
   - panel fingerprint.

2. Extend PkmnPrices client:
   - grader,
   - grade,
   - graded=None for combined stream where appropriate,
   - preserve grade_qualifier.

3. Migrate sold evidence safely:
   - add grade_qualifier,
   - preserve append-only transaction identity,
   - retain provider_payload,
   - do not change Set Value / NM authority.

4. Define provider-agnostic research schemas for:
   - active supply snapshots,
   - grading-population snapshots,
   - provider identity mappings.

5. Audit / clean duplicate grading-company test identities without treating legacy graded rows as authority.

## Gate

No provider spend beyond tiny smoke tests.
No Fair Value fitting.

---

# Bucket B — Completed transactions + graded pricing

## Objective

Build the durable transaction ledger for raw and graded markets.

## Work

1. Historical backfill Core Panel V1 through PkmnPrices cursor exhaustion.
2. Collect both:
   - raw/ungraded sales,
   - graded sales.
3. Preserve:
   - grader,
   - grade,
   - grade_qualifier,
   - currency,
   - exact/shared/unknown attribution,
   - exact internal variant,
   - sold_at,
   - ingested_at,
   - provider payload.
4. Add daily incremental collector using ingested_at checkpoint.
5. Produce zero-credit card-level shape summaries:
   - transaction count,
   - transaction days,
   - days between sales,
   - 7/30/90/180-day counts,
   - median / MAD / IQR,
   - raw vs graded mix,
   - grader/grade distribution,
   - retained-history span.
6. Hard credit caps and resumable cursor state.

## Pricing role

Graded sale prices are transaction evidence, not a single canonical "graded market price."
Future grade-specific estimates must have minimum depth, recency and dispersion rules.

## Gate

Backfill coverage and costs documented.
No Fair Value fitting.

---

# Bucket C — Fixed-panel offered supply / Market Availability evidence

## Objective

Start genuine longitudinal supply collection.

## Primary source

PkmnPrices TCGplayer live listings:
- English,
- Near Mint,
- exact printing,
- total_asc,
- quantity + seller + shipping,
- snapshot_at.

For each Core Panel card, persist a bounded snapshot daily.

Initial collection contract:
- page 1 / up to 20 offers per card,
- record has_more / truncation state,
- do not pretend first-page depth is total market inventory,
- optionally deepen high-value/thin cards after empirical cost audit.

Expected maximum at 207 cards:
- about 4,140 credits/day for a full 20 listings each,
- actual charge lower for thin cards,
- compatible with current 20k/day Pro allowance.

## Secondary sources

1. Existing eBay active-ask archive:
   - use point-in-time asks now,
   - do not infer disappearances unless the same target was observed on adjacent expected collection dates.

2. Optional Cardmarket:
   - one bounded English-card source snapshot,
   - EUR and native conditions,
   - separate market, never silently currency-blended.

## Derived raw facts

Do not create a composite score yet.

Persist:
- listing count in captured depth,
- summed quantity in captured depth,
- distinct sellers,
- seller concentration,
- lowest landed asks,
- ask dispersion,
- price-depth buckets,
- snapshot freshness,
- truncation/has_more,
- new / continuing / disappeared listing states only when observation continuity is proven.

## Gate

At least 30 consecutive expected panel dates with explicit missing-run flags before arrival/disappearance/turnover is treated as mature research evidence.

No Fair Value fitting.

---

# Bucket D — Grading population, surviving supply and condition normalization

## D1 GemRate procurement

Ask GemRate for:
- commercial Partner API price,
- request/rate limits,
- historical population entitlement,
- change-feed entitlement,
- catalog entitlement,
- storage/redistribution terms,
- whether internal derived analytics and card-level display are permitted.

Preferred endpoints:
- structured search,
- card population,
- card population history,
- population change feed,
- bulk catalog if cost-effective.

## D2 Population mapping

Map exact inDex physical variants to GemRate universal IDs.

Store:
- source identity,
- grader identities/spec IDs,
- population by grade,
- total population,
- gem count / gem rate,
- observed date,
- source timestamp,
- match confidence / reason,
- historical population where licensed.

Never combine First Edition / Unlimited / Shadowless mappings.

## D3 Grading velocity / surviving supply

Research primitives:
- total graded population,
- population by grade,
- gem population,
- gem rate,
- 7/30/90/365-day population growth,
- grading acceleration,
- share by grader,
- population relative to observed transaction velocity.

Important:
Population is submission-selected, not total physical supply.
It must never be called "copies in existence."

## D4 Raw condition normalization

Separate project:
- deterministic title classifier for NM/LP/MP/HP/Damaged/ambiguous/unlabeled,
- reviewed labeled sample,
- precision by class,
- false-positive audit,
- versioned outputs that never mutate raw transaction rows.

Only after validation may condition-adjusted raw sold dollars be considered as valuation features.

## Gate

Population source licensed/approved.
Mapping precision and coverage documented.
Condition classifier validated.
No Fair Value fitting.

---

# Bucket E — Market microstructure research

## Objective

Study primitives separately before creating any higher-level Market State construct.

## Primitive families

### E1 Market Availability
Question:
How much exact variant supply is observable now?

Candidate variables:
- captured active listing depth,
- quantity depth,
- seller depth,
- seller concentration,
- price-depth shape,
- stale inventory share,
- active-supply trend.

### E2 Market Turnover
Question:
How quickly is observable supply clearing?

Use actual completed sales rather than inferred ended listings.

Candidate variables:
- sales per day,
- transaction-day frequency,
- median gap between sales,
- sales relative to observed supply,
- new supply relative to completed sales,
- inventory absorption / replenishment,
- persistence of turnover.

Do not reproduce Collectrics' Demand Pressure formula or thresholds.

### E3 Transaction Quality
Question:
How trustworthy is the clearing-price signal?

Candidate variables:
- transaction count,
- recency,
- robust price median,
- MAD,
- IQR,
- outlier share,
- condition-label coverage,
- graded/raw mix,
- source disagreement.

### E4 Surviving / graded supply
Question:
How much professionally graded supply has accumulated and how is it changing?

Candidate variables:
- total graded pop,
- high-grade pop,
- gem rate,
- population velocity,
- grade mix,
- graded-sale velocity,
- slab liquidity.

### E5 Market Scarcity research construct

Do not define a score first.

Test:
- availability after controlling for Pull Scarcity,
- turnover after controlling for Appeal,
- population after controlling for age / price / set,
- interactions of Appeal × Market Availability,
- Pull Scarcity × Market Availability,
- graded population × graded turnover.

Primary research question:
Does point-in-time Market Scarcity add information about price level or later excess returns after controlling for Pull Scarcity, Collector Appeal, Treatment, lifecycle and prior price behavior?

## Validation

- grouped root-set holdouts,
- price-band stratification,
- era diagnostics,
- exact variant controls,
- point-in-time joins only,
- no target-derived predictors,
- bootstrap/stability tests,
- forward-time validation.

## Gate

No composite Market State score unless individual primitives prove stable and non-redundant.

---

# Bucket F — Fair Value re-entry

Fair Value research may restart only after the following minimum gate:

1. Core Panel identity frozen.
2. Completed-sale backfill materially complete and incremental collector operating.
3. Graded sale schema supports qualifier-safe grade identities.
4. Fixed-panel active supply has >=30 consecutive expected observation dates with >=90% target coverage, or a documented stronger substitute.
5. Grading population source either:
   - integrated with acceptable coverage/history, or
   - explicitly ruled unavailable/uneconomic so the model contract can state the omission.
6. Condition-normalization status explicitly known.
7. Microstructure primitives have independent descriptive/stability reports.
8. No target leakage.
9. Production pricing authority remains unchanged.

## Fair Value restart sequence

Do not simply add every new variable to one model.

Re-run in stages:

A. Existing structural baseline.
B. Existing market-anchored baseline.
C. + transaction liquidity only.
D. + active supply only.
E. + transaction + supply interaction.
F. + graded/surviving-supply variables.
G. + condition-normalized sold-price context, only if validated.

For every step:
- grouped OOF by root set,
- forward-time holdout,
- MAE / RMSE / MdAPE / within bands / dollar R2 / Spearman,
- calibration/range coverage,
- price-band and era breakdowns,
- ablations,
- no post-result feature selection without a new preregistration.

Keep:
- Structural Fair Value,
- Market-Conditional Fair Value,
- Market State diagnostics
as separate conceptual products unless evidence supports a different architecture.

---

# Execution order

1. Bucket A — now.
2. Bucket B and Bucket C can run in parallel after A contracts freeze.
3. Bucket D procurement can begin immediately, while code integration waits for terms/key.
4. Bucket E starts as zero-credit analysis as evidence matures.
5. Bucket F remains blocked until gates pass.

## Cost posture

Current known recurring cost:
- PkmnPrices Pro: $14.99/month, 20k credits/day.

Likely no immediate need:
- PriceCharting Legendary: $49/month.

Unknown / procurement:
- GemRate Partner API.

Provider spend policy:
- hard daily caps,
- persist every purchased row,
- never pay twice for the same research observation if local history can answer the question,
- keep heavy database writes sequenced away from publication jobs.

---

# First agent prompt

Begin Bucket A only.

Do not run a broad provider backfill yet.
Do not fit Fair Value.
Do not create a Market Scarcity/HYPE-like score.
Freeze the panel, close graded schema/client gaps, add tests, and produce a dry-run manifest + migration plan.
