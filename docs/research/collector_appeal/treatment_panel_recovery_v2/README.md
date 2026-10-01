# Treatment Panel Recovery V2

Status: research-only historical panel recovery.

## Objective

Recover the exact-date Near-Mint historical price panels that blocked the
Set-relative Treatment hierarchy at Round 24 / Treatment Hierarchy V1.

This phase does **not** fit a Treatment estimator. It only asks whether the
already-frozen matched-treatment ladders can now satisfy the frozen shared-date
readiness gates.

## Source authority

The recovery source is PkmnPrices:

- endpoint: `GET /v1/cards/:id/prices/history`
- currency/source: USD / TCGPlayer
- condition: exact `Near Mint`
- period: 180 days
- provider rows: daily `avg/low/high` price aggregates
- no eBay sold rows are used in the primary recovery panel
- no interpolation, nearest-date matching, or forward fill
- source version: `pkmnprices_tcgplayer_nm_history_recovery_v2`

PkmnPrices documents that price history is grouped by exact condition and
printing variant and can return up to 365 days. The research collector requests
Near Mint and retains TCGPlayer/USD rows only.

## Frozen cohort

The first execution is deliberately bounded to:

1. the exact 22-Set simulation cohort from 2026-09-29;
2. Round-24 ladders currently marked `HISTORY_BLOCKED`;
3. ladders whose required canonical cards already have an existing
   `pkmnprices_card_identity_v1` mapping.

No new provider identity is persisted by this pilot.

At preflight on 2026-10-01 this produced:

- 3,644 Round-24 ladders in the 22-Set cohort;
- 193 ladders touching at least one already-mapped canonical card;
- 27 ladders with every required canonical card already mapped;
- those 27 ladders span 15 Sets.

## Frozen readiness classification

The collector reuses the Round-24 thresholds:

- `PANEL_READY_STRONG`: >= 90 exact shared dates;
- `PANEL_READY_MODERATE`: tier-1 ladder with >= 30 exact shared dates;
- otherwise: `HISTORY_BLOCKED`.

No Treatment hierarchy/model fitting occurs in this phase.

## Safety

The script performs:

- read-only Supabase queries;
- bounded provider GET requests;
- local artifact writes only.

It does **not** mutate:

- `card_variant_price_observations`;
- Price Storage authority;
- Collector Appeal;
- Overall RIP;
- Rankings;
- Set-page publications.

The VM execution must acquire `/tmp/pkmnprices-api.lock` before calling the
provider, so it cannot run concurrently with Bucket B5 or another PkmnPrices
consumer.

## Next gate

If this recovery produces enough independent Set-treatment ladders to satisfy
the already-frozen Treatment Hierarchy V1 G1-G4 and era-progression rules, the
existing study may resume at Phase 2.

If not, the next recovery step is identity expansion for additional matched
ladders and/or authoritative metadata repair. The model gates must not be
changed to accommodate the recovered sample.
