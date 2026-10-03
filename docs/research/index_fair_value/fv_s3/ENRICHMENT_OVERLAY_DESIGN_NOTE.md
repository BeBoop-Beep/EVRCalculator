# Future versioned enrichment overlay — design note (NOT built)

Status: design only. Not required for the shadow phase; **required before any production Fair Value promotion.**

## Problem

`PkmnPricesStore.insert_evidence()` freezes first-seen provider enrichment (title, attribution, grader/grade,
variant). If the provider later reclassifies a transaction (ungraded → TAG 9, shared → exact, title corrected), the
economic row is intentionally left alone and only a `provider_metadata_drifts` counter increments. That is right for
audit but wrong as the *effective* view of a sale for a price estimator: a production Fair Value that reads the frozen
row can silently use a stale grade. A counter in a run receipt cannot say *which* comps were affected.

## Shadow-phase policy (what is true today)

* Every publication records `enrichment_policy = FIRST_SEEN_PROVIDER_ENRICHMENT_RESEARCH_ONLY` (and the ledger DDL
  rejects any other value).
* The strict title rule fails closed on obvious grade contamination (322 panel rows are `graded=false` yet carry
  grader/grade evidence in the title and are rejected).
* Drift observed later is surfaced by the increment collector's per-card receipts and run metadata
  (`provider_metadata_drifts`), and members store `grader_at_first_seen` / `graded_at_first_seen` so a later audit can
  compare what the anchor used with what the provider now says.
* No public or production surface reads these rows or the ledger.

## Proposed overlay (future)

Append-only table `pkmnprices_sold_enrichment_observations_v1`:

| column | meaning |
| --- | --- |
| `provider_card_id`, `provider_listing_id` | key of the immutable evidence row (FK to the evidence table) |
| `observed_at` | when we saw this version of the provider's metadata |
| `enrichment_version` | monotonically increasing per listing (unique with the key) |
| `title`, `attribution`, `grader`, `grade`, `grade_qualifier`, `provider_variant` | provider values at `observed_at` |
| `payload_sha256` | hash of the provider payload, for cheap change detection |
| `source_run_id` | run that observed it |

Rules:
1. The economic row (`price`, `currency`, `sold_at`, `provider_listing_id`) is never changed; the overlay never
   overwrites, it appends.
2. The *effective* metadata for evaluation time *T* is the latest overlay row with `observed_at <= T`, else the
   first-seen row. Prospective publications therefore remain reproducible as-known-at the cutoff.
3. Re-observation is only paid for where it matters: comps currently inside a published anchor window, plus a
   rolling sample, so cost is bounded by the shadow's own membership, not the whole ledger.
4. Reclassification that *removes* a comp (now graded, wrong attribution) produces a **new** publication version for
   that card/date (`rule_version` unchanged, `enrichment_basis = OVERLAY_AS_OF_T`), never an edit of the original.
5. A production Fair Value promotion gate must verify: overlay coverage of every comp used, drift rate below a
   pre-registered threshold, and that no stale first-seen state is consumed silently.

## Why it is deferred

The shadow needs only fail-closed title rules and visible drift counts to be *correct as research*; it makes no
production claim. Building the overlay now would add a collection cost and schema without a decision it informs.
The first prospective drift counts (from the shadow's own receipts) are exactly the data needed to size it.
