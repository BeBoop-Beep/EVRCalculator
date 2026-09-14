# eBay Daily Raw Evidence Collector — Shadow Implementation Report

## 1. Git authority

- Branch: `develop`
- HEAD at start of work: `6305d4c9a5900ffb729666ca52f8093cb3897955`
- No unrelated concurrent work was touched or overwritten.

## 2. Files changed

New files only — nothing existing was modified:

- `backend/scripts/index_fair_value_ebay_evidence_collector.py` — core collector library.
- `backend/scripts/run_index_fair_value_ebay_daily.py` — CLI entrypoint.
- `backend/tests/unit/scripts/test_index_fair_value_ebay_evidence_collector.py` — 19 unit tests, fully mocked, no live eBay dependency.
- `backend/artifacts/index_fair_value/EBAY_EVIDENCE_COLLECTOR_D1_SHADOW.md` — this report.
- One bounded live-smoke run's output artifacts under `backend/artifacts/index_fair_value/ebay_evidence_runs/` (see §11).

## 3. Pre-existing state found by audit (before any edits)

The repo already contains a matcher lineage well beyond the D1/D2 framing:
`ebay_d2m_matcher.py` → `ebay_d2m_matcher_v2.py` → `ebay_d3_matcher_v3.py`, each with its own
development/validation/certification study scripts, plus a fail-closed gold-label access layer
(`ebay_gold_access.py`) guarding `ebay_gold_development.csv` / `ebay_gold_validation.csv` /
`ebay_gold_final_blind.csv` (dual-reviewer + adjudication schema) and D3 blind partitions.
`ebay_d3_v3_freeze_manifest.json` shows the D3 v3 matcher logic is frozen
(`matcher_fingerprint=b5e44641...`) but explicitly `"production_authority": false`. This
collector treats `ebay_d3_matcher_v3.classify_listing` as the current versioned derived
matcher (per user confirmation), and changes nothing about its logic or thresholds.

No `pricing.market_evidence` schema or `PricingAuthority` reader exists yet. The closest
existing writer pattern is `backend/db/services/price_storage_v2_integration.py`
(`publish_isolated_run`/`ScopedRun`), which this collector does not call — it only
produces provider-neutral staging artifacts (JSONL), per the prompt's instruction to avoid
inventing an incompatible schema.

## 4. Architecture implemented

```
select_cohort()  -> generate_queries()  -> BrowseHTTP (paginate via `next`, budget+retry)
                                              |
                                    normalize_listing()  (raw evidence, JSONL, append-only)
                                              |
                                run_matcher_on_listing()  (ebay_d3_matcher_v3, versioned, separate JSONL)
```

`Collector.run()` orchestrates per-target iteration over `generate_queries()`, paginating each
formulation by the Browse response's `next` link only. `RunState` is the checkpoint: it is
saved after every run invocation, tracks per-target status (`pending`/`in_progress`/
`completed`/`deferred`), and is reloadable by `run_id` via `--resume`.

## 5. Raw evidence contract

`normalize_listing()` captures, per listing: eBay item ID, title, item URL, image URL, price
value/currency, shipping value/currency, condition + condition ID (preserved as-is, `None`
when absent — never fabricated), seller username, buying options, item location, the exact
search query and formulation that discovered it, the target instrument's canonical IDs,
retrieval timestamp, collector run ID, page number, collector version, and the raw
`itemSummary` payload (`raw_item_summary`) for future reprocessing. Every row's
`evidence_kind` is hardcoded to `"active_ask"` — there is no code path that can emit
`sold`/`transaction`/`realized_price` from Browse search results.

## 6. Matcher separation

`run_matcher_on_listing()` produces a distinct record referencing `ebay_item_id`,
`target_canonical_card_id`, `matcher_version`, `match_status`, `accepted`, `condition_state`,
`reason`, and `diagnostic_features` — written to a separate JSONL file
(`<run_id>.matches.jsonl`) from the raw evidence (`<run_id>.raw.jsonl`). A raw listing is
written regardless of matcher outcome (verified by test #15), so a future matcher version can
reprocess `*.raw.jsonl` without any new eBay calls. `AMBIGUOUS` never maps to `accepted=True`
(test #17).

## 7. Cohort / query strategy

`select_cohort()` supports the frozen `d1_70` cohort (`ebay_pilot_cohort.json`), an explicit
`--target-file`, and future explicit-ID lists — sorted deterministically by
`canonical_card_id`, with a `cohort_fingerprint` (sha256 of sorted IDs) recorded in every
`RunState`. `generate_queries()` centralizes query construction: a `primary` formulation
(reuses `index_fair_value_ebay_supply.build_query`, unchanged) and a `collector_number_focus`
formulation (name + number + set only, no "Pokemon card"/edition/printing terms) for broader
recall — both always run for every target (allocation is not result-size-dependent), and both
are recorded on every raw evidence row via `search_query`/`search_formulation`. Deduplication
is by `ebay_item_id`, both within a search's pages and across a target's formulations (test #3).

## 8. Request-budget behavior

`CollectorConfig` defaults: `max_requests_per_day=1000`, `max_pages_per_search=3`,
`max_listings_per_target=200`, `retry_budget=5`, bounded exponential backoff
(`min(backoff_max, backoff_base * 2**attempt)`). `BrowseHTTP.get()` raises `BudgetExhausted`
the instant the run-level budget hits zero; `Collector.run()` catches this, marks the
in-flight target `deferred` with reason `budget_exhausted`, persists counts, and returns
`completed=False` cleanly (no partial/corrupt writes — test #6/#7). Retry classification:
`{429,500,502,503,504}` and genuine network errors (`URLError`/`OSError`/`TimeoutError`) retry
with backoff up to `retry_budget`; any other 4xx fails immediately with no retry (test #10-12).
A `401` triggers exactly one forced token refresh before retrying (test #13).

## 9. Checkpoint / resume behavior

Every `RunState` persists `run_id`, `cohort_fingerprint`, `matcher_version`,
`query_strategy_version`, `started_at`, per-target status, and running request/retry/failure
counts to `backend/artifacts/index_fair_value/ebay_evidence_runs/<run_id>.json`. `--resume
<run-id>` reloads this state, skips targets already `completed`, and re-derives the
already-seen item IDs / matcher keys from the existing JSONL files before continuing — so a
rerun of an already-completed run, or a resumed run, never duplicates evidence (tests #19-21).
A fresh daily invocation always mints a new `run_id` (`uuid4`).

## 10. Storage boundary

Output is two append-only JSONL files per run (`*.raw.jsonl`, `*.matches.jsonl`) plus the
JSON run-state manifest — a provider-neutral staging boundary, not a new database schema,
per the instruction to avoid inventing a `pricing.market_evidence`-shaped table before one
exists. Nothing in this collector calls `price_storage_v2_integration.py`,
touches TCGplayer pricing, Set Value, simulations, or any public snapshot.

## 11. Tests / results

19 unit tests, all mocked (no live eBay dependency), covering: deterministic cohort
selection, query generation, cross-page/cross-query dedup, `next`-based pagination
independent of `total`, run-budget enforcement and exhaustion, per-search page cap, per-target
listing cap, retryable 429, bounded 5xx retry, deterministic 4xx failure, 401 token refresh,
unknown-condition preservation, raw evidence surviving matcher rejection, matcher output
versioning/separation, ambiguous-never-accepted, active-ask-only evidence, resume after an
interrupted target, rerun idempotency, and credential redaction.

```
19 passed in 0.10s   (backend/tests/unit/scripts/test_index_fair_value_ebay_evidence_collector.py)
192 passed            (full backend/tests/unit/scripts -k "ebay or fair_value" — no regressions)
```

## 12. Bounded live-smoke result

Run `ce3dabf359bf4ef89e99f486bce494d8`, limits: 2 targets, 2 pages/search, run budget 10.

| Metric | Value |
|---|---|
| Browse calls consumed | **5** (of 10 allowed) |
| Listings captured (deduped) | 314 |
| Targets completed | 2 / 2 |
| Requests failed / retried | 0 / 0 |
| Condition coverage | 314/314 (100%) |
| Price coverage | 308/314 (98.1%) |
| Shipping coverage | 186/314 (59.2%) |
| Matcher: HIGH_CONFIDENCE | 203 |
| Matcher: REJECTED | 107 |
| Matcher: AMBIGUOUS | 4 |
| Matcher: accepted | 203 |

This smoke validates the collector's mechanics only — it does **not** validate matcher
accuracy, and none of these acceptance counts were used to tune anything.

## 13. Exact Browse calls consumed (this task, total)

5 (the single live-smoke run above). No other live calls were made — `--dry-run` used to
validate the full 70-card plan made zero calls.

## 14. D2/D3 human-label status

- Raw `ebay_manual_gold_labels.csv` (1,050-row blinded queue): still `PENDING_INDEPENDENT_HUMAN_REVIEW` per row.
- Downstream lineage **does** contain populated dual-reviewer + adjudication schemas:
  `ebay_gold_development.csv`, `ebay_gold_validation.csv`, `ebay_gold_final_blind.csv` (columns
  include `reviewer_1_label`, `reviewer_2_label`, `adjudicated_label`, `adjudicator_id`,
  gated by `ebay_gold_access.py`). These were **not opened or consumed** by this collector task
  — reported for status only, per instruction not to tune against labeled data here.
- D3 blind partitions (`ebay_d3_precision_blind.csv`, `ebay_d3_coverage_blind.csv`,
  `ebay_d3_blind_review_queue.csv`) are sealed to matcher access (`purpose='human_review'`
  only) by the same access layer, and remain untouched.

## 15. Unresolved matcher-validation gate

`ebay_d3_v3_freeze_manifest.json` records `"production_authority": false` and
`"new_certification_labels_viewed": false`. This collector does not change that. Matcher
output produced here (`accepted`/`match_status`) is diagnostic/derived only — it is not
treated as, and must not be read as, ground truth or Fair Value input.

## 16. Assumptions code cannot prove

- eBay Browse API retention/redistribution rights for stored `raw_item_summary` payloads are
  assumed to follow the same terms already relied on by the existing D1/D2 scripts; this
  collector adds no new retention obligation beyond what those scripts already assumed.
- eBay's documented 5,000 calls/day ceiling and per-account variation are taken as given by the
  prompt; this code enforces a much lower internal ceiling (1,000/day default) but cannot
  verify eBay's own account-side limit programmatically.
- OAuth application-token scope/permissions are assumed unchanged from the D1 script's usage.

## 17. Confirmation

Public prices, Set Value, simulations, and public snapshots were not read from or written to
by any code introduced in this task. No existing file was modified.

## 18. Final decision

**`EBAY_DAILY_RAW_COLLECTOR_READY_FOR_SHADOW_SCHEDULING`**

Recommended next prompt: **eBay E2 — Search Allocation + Evidence Quality Estimator + D2
Matcher Validation Boundary**, using this collector's raw evidence plus the already-populated
`ebay_gold_development.csv`/`ebay_gold_validation.csv`/`ebay_gold_final_blind.csv` dual-reviewer
labels (not yet consumed here) to establish how aggressively eBay evidence may be matched and
summarized before Fair Value methodology is implemented.
