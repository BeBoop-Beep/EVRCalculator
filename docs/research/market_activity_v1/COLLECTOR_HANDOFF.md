# FMA V1 — collector handoff (receipt gaps for the adjacent workstream)

FMA-0 changes no collector, no watermark, no cron, no credential and no
provider budget. It also does not broaden collection or alter the frozen Core
Panel V1 (fingerprint
`9e3068ffb2e644e3dab2f5c237271afa4efe061ed8f3139187dc9e8331bd1d1f`).

Issue #480 owns the next 180-day transaction-horizon calibration and its
approved budget. This document lists the **receipts** that activity V1 needs
before a window can become `PROVEN`. It does not add a second collector.

## 1. Sold-history walk receipts (needed by window readiness)

**Current state (repo audit and read-only DB check, 2026-09-29/30).**
- `pkmnprices_sold_sync_state_v1` stores a status, a cursor inside `metadata`,
  and `last_ingested_at`. There is no per-page receipt table.
- Bucket B2 run metadata stores per-card input and output cursor hashes, but
  not per page.
- None of these record:
  - the filter fingerprint;
  - per-page sold-date bounds;
  - a head proof;
  - a right-edge reconciliation.
- The sync states are 22 rows: 13 `CURRENT` and 9 `PARTIAL`.
  - 12 of the `CURRENT` rows come from the legacy vintage collector
    (`run_pkmnprices_sold_evidence.py`). That collector walked `graded=False`,
    which is a raw-only stream, and its metadata has **no stream label**. For
    those rows, `CURRENT` proves nothing about graded tiers.
  - 1 `CURRENT` and 9 `PARTIAL` rows are `combined_raw_graded` Bucket B
    cursors.

Under the V1 contract, none of these states is proof on its own.
`readiness_from_sync_state` returns `SYNC_STATUS_NOT_PROOF`.

**Needed (additive; proposed names).**
```
pkmnprices_sold_walk_receipts_v1
  walk_id uuid pk, provider_card_id bigint, run_id uuid,
  stream text check (stream in ('RAW_ONLY','COMBINED','GRADE_FILTERED')),
  grader_filter text, grade_filter text, filter_fingerprint text not null,
  sort text not null check (sort = 'date_desc'), started_from_head boolean not null,
  combined_semantics_verified boolean not null, started_at, finished_at, exhausted boolean
pkmnprices_sold_walk_pages_v1
  walk_id uuid, page_index int, input_cursor_hash text, output_cursor_hash text,
  has_more boolean, row_count int, min_sold_at date, max_sold_at date,
  min_ingested_at timestamptz, max_ingested_at timestamptz, fetched_at timestamptz,
  primary key (walk_id, page_index)
pkmnprices_sold_right_edge_receipts_v1
  provider_card_id bigint, stream text, head_walk_id uuid, reconciled_through timestamptz,
  completed boolean, primary key (provider_card_id, stream, reconciled_through)
```

**Receipt rules.**
- Write receipts in the same unit of work as the evidence insert.
- Store cursor values only as hashes. This matches the Bucket B2 practice.

**Resumed walks.** A resumed walk that did not start from the head is still
useful for the lower-boundary proof. It must be linked, through
`input_cursor_hash`, to a walk whose first page came from the head. Otherwise
it is `WALK_HEAD_UNKNOWN`.

## 2. Watermark and checkpoint gaps (audit; no change made)

These findings come from repo evidence. Nothing was modified.

1. **Legacy incremental mode.** In `run_pkmnprices_sold_evidence.py`,
   incremental sync sets `status=CURRENT` and advances `last_ingested_at` to
   the maximum observed ingestion, **even when the bounded walk returned
   `has_more=true`**. That walk is sorted by sold date, with a `since` filter
   on ingestion. Rows ingested after the previous watermark but sitting on
   unread later pages can therefore be skipped on the next run. Frozen rule:
   `checkpoint_advance_decision(order="sold_desc")` advances only after the
   filtered walk drains.
2. **Boundary semantics of `since`.** It is not documented whether the
   provider applies `ingested_at >= since` or `> since`. If the comparison is
   strict (`>`), then rows that share the exact watermark timestamp and sit on
   an unread page are lost. Same-timestamp pages must drain before any
   advance. For ingestion-ordered walks, the frozen rule allows advancing only
   to a timestamp strictly below the last page's maximum.
3. **Timestamp comparison.** The watermark maximum is computed on ISO strings
   (`max(observed_ingested)`). This is safe only while the provider emits a
   single fixed format. Compare parsed UTC timestamps instead
   (`market_activity.parse_timestamp`).
4. **Bucket B/B2 advance rule.** Bucket B/B2 advance `last_ingested_at` only
   when `has_more=false`. This matches the frozen rule. The first-page maximum
   is held as `core_panel_incremental_watermark` until then. Keep it.

## 3. Identity gaps (audit; stored rows not rewritten)

**One-candidate EXACT shortcut.** Bucket B `_normalize` passes only the
panel's target variant to `resolve_internal_variant`. As a result, any
non-contradicting label, including an **empty** one, resolves as `EXACT`.

Read-only DB check (5-second timeout, aggregate counts only):

| Group | Rows | Assessment |
|---|---:|---|
| `identity_state=EXACT` with attribution `exact`, USD | 3,003 | |
| – "Holofoil" on single-variant modern cards | 2,759 | sound under the full-set rule |
| – "Holofoil" on a card with holo + reverse-holo siblings | 173 | sound: printing stated |
| – "1st Edition Holofoil" / "Unlimited Holofoil" | 68 | sound |
| – **"Holofoil" resolved to an Unlimited variant with a 1st Edition sibling** | **3** | edition never stated; V1 excludes them as `IDENTITY_EDITION_UNPROVEN` |
| `provider_variant IS NULL` resolved EXACT | 185 | attribution `unknown`, so already excluded; the shortcut still fired |

These rows are **not** rewritten. `evaluate_legacy_sold_row` reports the
disagreement at build time.

**Collector fix to hand off.** Pass the full sibling variant set of the card
to the resolver, and persist the resolver's candidate scope.

**Holo-before-Non-Holo.** The legacy `_PRINTING_ALIASES` order parses
"Non-Holo" and "Non Holo" as `holo`. A read-only DB check found **no stored
"Non-Holo" or "Normal" labels**. All labels are Holofoil, Unlimited Holofoil,
1st Edition Holofoil or Reverse Holofoil, so there is no evidence that stored
rows are wrong. The strict parser in `market_activity.py` fixes the order for
activity. The collector should adopt the same order before it collects any
Non-Holo card.

**Grading.** 8 graded rows are missing a grader, and none is missing a grade.
31 rows carry a qualifier. V1 excludes incomplete slabs from both raw and
graded tiers. No collector change is needed, but keep persisting the
`grade_qualifier` column.

## 4. Supply provenance gaps

**Current state (read-only DB check).**
- 10 observed snapshots, 190 offers across 10 variants.
- All 10 snapshots are truncated (`has_more=true`).
- Provider confirmations run from 2026-09-23 20:12Z to 2026-09-24 02:06Z,
  while collection ran on 2026-09-29 at 22:08Z. Under the 24-hour policy every
  snapshot is `STALE`, even though collection is one day old.
- The only supply run is the 10-target smoke
  (`13d1cbfc-d2ed-4310-93ba-7ab16e66d232`). **No 207-target daily run exists.**
  PR #477 is merged, but it is not activated at runtime; C2 remains blocked on
  VM host-key verification.

**Normalizer defaults (`active_supply.normalize_listing`).**
- A missing `shipping_price` is stored as `0.00`, which makes it identical to
  explicit free shipping. 64 of the 190 stored offers have shipping `0.00`, and
  they cannot be told apart.
- A missing **or zero** `quantity` becomes `1`. 169 of the 190 offers have
  quantity 1, and it is unknown how many of those were defaulted.

**Needed from the collector.** Persist
`source_payload.shipping_provenance ∈ {EXPLICIT, UNKNOWN}` and
`source_payload.quantity_provenance ∈ {EXPLICIT, DEFAULTED}` for each new
offer, using the rule in `classify_offer_provenance`.
- Keep `shipping_price` `NULL` when it is unknown. The column is already
  nullable.
- Reject quantity `0` instead of coercing it.
- Existing rows stay `LEGACY_UNVERIFIED`. Do not backfill provenance.

**Empty results.** Persist the provider's own freshness for an empty page
(`sourceConfirmedAt`), if the provider exposes one. Without it, an empty
response is `ZERO_UNPROVEN`.

## 5. What remains out of scope for this handoff

- Increasing the depth past 19 offers, requesting page 2, collecting outside
  the panel, and any turnover/disappearance inference.
- Any change to the Issue #480 collector or its budget.
