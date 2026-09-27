# EBAY_E2_13 — CAPTURE-ALLOCATION-v2 Fresh Blind Capture + Review Prep

**Final result:** `EBAY_CAPTURE_ALLOCATION_V2_FRESH_BLIND_READY_FOR_HUMAN_LABELING`

Worktree `D:\EVRCalculator-ebay-e2.9`, branch `feature/ebay-e2.9-image-veto-tiered-identity`, HEAD unchanged. All work uncommitted. D3-v5, IMAGE-v2, COMBINED-IDENTITY-v2, and CAPTURE-ALLOCATION-v2 were not modified. D3-v6 remains unfrozen. No scoring, no certification.

## 1. Frozen authority fingerprints (Phase 1 — verified before any provider call)

| Authority | Current | Frozen | Match |
|---|---|---|---|
| D3-v5 (`rule_fingerprint()`) | `93301e5d...4581c69` | same | ✓ |
| IMAGE-v2 (`source_sha256()`) | `bf50ee1f...4c680ea1` | same | ✓ |
| COMBINED-IDENTITY-v2 (`policy_source_hash()`) | `59e32c0a...9954abf07` | same | ✓ |
| Canonical-resolution manifest (SHA256 of durable copy) | `9fc36d8d...ab295d446` | same | ✓ |
| CAPTURE-ALLOCATION-v2 (`allocation_fingerprint`) | recomputed from live manifest | `8f297bf0...9e70d6261c79e95f81ae0e8b071578650ea3c4f93` | ✓ |

All five matched. No `EBAY_E2_13_CAPTURE_BLOCKED_FROZEN_AUTHORITY_MISMATCH` condition occurred.

## 2. Allocation-v2 fingerprint

`8f297bf07a0b891225705c39e70d6261c79e95f81ae0e8b071578650ea3c4f93` — used exactly as frozen: `rows_per_card=8`, `max_requests_per_run=1000`, `max_pages_per_search=3`, `max_listings_per_target=200`, unchanged query generation (`index_fair_value_ebay_evidence_collector.generate_queries`) and unchanged stratified sampling.

## 3. Capture timing

`capture_started_at`: **2026-09-16T02:34:45Z**
`capture_finished_at`: **2026-09-16T02:37:34Z** (~2m49s)

## 4. Request count

**226 Browse requests, 226 successful, 0 failed, 0 retries.** All 70 targets in `d1_70` completed (`--no-match`, policy-blind collection by construction).

## 5. Raw candidate count

**11,756** raw (deduplicated-within-run) listing records across all 70 targets.

## 6. Exclusion counts (Phase 2)

Exclusion authority verified to explicitly include `ebay_e2_9b_fresh_blind_queue.csv` (the E2.12-identified and -corrected gap) alongside every earlier evidence source (D2/D3/V4/V5/E2.6–E2.11 queue and gold files).

| Metric | Value |
|---|---|
| Prior exact item IDs loaded (pool size) | **11,134** (unchanged pool — E2.9B's queue was already folded into this count by the E2.12-frozen file list) |
| Prior URLs loaded | tracked (`historical_url_pool_size` in manifest) for completeness; exact-ID matching remains the primary exclusion mechanism, as in E2.9B |
| Prior relist fingerprints | derived from the same 14-file pool (title+seller+card+price-bucket hash) |
| Exclusion-set fingerprint | `capture_allocation_fingerprint` ties this run to the frozen contract; the historical-exclusion source itself is fingerprinted (`historical_exclusion_source_fingerprint` in the E2.12 freeze manifest, reused unmodified) |
| Excluded — exact historical item ID | **8,932** |
| Excluded — likely relist fingerprint | **71** |
| Excluded — duplicate within this run | **0** |
| Eligible after dedup | **2,753** |

## 7. Final row count

**553 rows** — matches the E2.12 projection (~552) almost exactly.

## 8. Represented-card count

**70 / 70** — every target card is represented, including Pecharunt ex (see Section 10; it was fully exhausted at E2.9B capture time but a genuinely new listing has since appeared on the live market).

## 9. Per-card distribution

| Rows selected | Number of cards |
|---|---|
| 8 (full allocation) | **69** |
| 1 (shortfall) | **1** (Pecharunt ex) |

## 10. Exhausted/shortfall cards

**Pecharunt ex** (`640cd931-d97f-4173-ad9d-3ab86f91d92c`) — `surviving_candidates: 1, selected: 1`. Honestly reported as a shortfall, not compensated by taking extra rows from any other card (verified directly — every other card received exactly its earned share, never more than the frozen cap of 8). No historical exclusion was weakened to reach a row-count target. This is a real, current measurement: at E2.9B's capture time this same card had **zero** surviving candidates (fully exhausted); a new market listing has genuinely appeared since — this reflects real-world eBay inventory turnover between the two capture runs, not a change in method.

## 11. Proof E2.9B (and all prior cohorts) excluded (Phase 5 — cohort novelty)

| Check | Result |
|---|---|
| Overlap with E2.9B `listing_item_id` | **0** |
| Overlap with E2.9B `benchmark_row_id` | **0** |
| Overlap with V4 `listing_item_id` | **0** |
| Overlap with V5 `listing_item_id` | **0** |
| Known historical relists surviving in final cohort | **0** (all caught by the frozen relist-fingerprint check pre-sampling) |
| Duplicate `listing_item_id` within the 553-row cohort | **0** |
| Duplicate `benchmark_row_id` within the 553-row cohort | **0** |

No historical leak was found, so no remediation was needed.

## 12. Image infrastructure availability (Phase 7 — infrastructure only, no IMAGE-v2 classification run)

- Listing `image_url` present: **553 / 553** (100%)
- Random 15-row sample: real HTTP fetch + magic-byte decode — **15 / 15 succeeded**
- Canonical target image resolution: all **70 / 70** cards represented in this cohort already have a `found: true` entry in the durable canonical-resolution manifest — zero gaps, zero new resolution performed.
- IMAGE-v2 was **not** executed against any row — confirmed structurally: `capture_ebay_e2_13_fresh_blind.py` imports neither `ebay_image_retrieval_verifier` nor either combined-identity policy module (verified by AST import inspection in the test suite).

## 13. Queue schema

`ebay_e2_13_fresh_blind_queue.csv` — byte-identical column set to E2.9B's proven schema (kept for review-server compatibility, per the E2.9B lesson):

```
benchmark_row_id, listing_item_id, item_url, listing_title, condition, condition_id,
category_id, buying_options_json, seller_id, image_url, canonical_card_id, card_variant_id,
target_card_name, target_set_name, target_card_number, target_treatment,
exact_match_yes_no_uncertain, single_card_or_lot, raw_or_graded, card_or_sealed_nonshcard,
collector_number_consistency, set_consistency, language, variant_treatment,
reviewer_id, label_timestamp, review_note, adjudicated_result
```

Row IDs: `E13-0000` … `E13-0552`.

## 14. Proof no model-output leakage

- `assert_no_forbidden_columns()` run against the live 553-row queue: **passes**.
- `capture_ebay_e2_13_fresh_blind.py`'s imports were AST-inspected (not just string-grepped, to avoid false positives from unrelated label strings): it imports **none** of `ebay_d3_matcher_v5`, `ebay_d3_matcher_v6`, `ebay_image_retrieval_verifier`, `ebay_combined_identity_policy_v1`, or `ebay_combined_identity_policy_v2`.
- All 553 `exact_match_yes_no_uncertain` values are blank.

## 15. Review-session ID

**`e2_13_session_1`** — a brand-new session, recorded as `active_review_session_id` in `ebay_e2_13_fresh_blind_manifest.json`. `backend/scripts/ebay_e2_13_blind_review_server.py` uses exclusively E2.13-named paths (`QUEUE_PATH`, `MANIFEST_PATH`, `HISTORY_PATH`, `CORRECTION_HISTORY_PATH`) — no cross-path fallback to E2.9B/V5/V4 exists (verified by direct inspection: every path constant was mechanically retargeted from the E2.9B server, and `LEGACY_SESSION_ID` is `e2_13_session_1` itself, not V5/E2.9B's).

## 16. reviewed_count = 0

Confirmed: `ebay_e2_13_fresh_blind_manifest.json` → `"reviewed_count": 0`, `"labels_exist": false`, `"labels_frozen": false`. `session_history_path(get_active_session_id()).exists()` → `False` — no history file exists yet.

## 17. UX validation

Reused the proven E2.9B/V5 review-server architecture verbatim (only path constants, `EXPECTED_ROW_COUNT=553`, and session-ID strings changed — the same low-risk adaptation pattern already validated in E2.9B). Validated:

- Adapted the full 99-test E2.9B server test suite (`test_ebay_e2_13_blind_review_server.py`) against the real `ebay_e2_13_blind_review_server.py` module: **99 passed** — covering append-only history, undo (including the exact "undo targets most recent row, not the displayed row" class of bug the V5 session-1 defect was), full undo→relabel→restart cycles, freeze refusal on incomplete/mismatched/forbidden-column cohorts, all 9 NO-reason mappings, correction-queue audit flow, and page-rendering checks.
- Direct checks against the **real** 553-row queue: first (`E13-0000`), middle (`E13-0276`), and last (`E13-0552`) rows all render with their own row ID and image URL correctly bound.
- Row IDs unique (553/553), listing IDs unique (553/553), all labels blank (553/553).
- Cohort fingerprint recomputes identically via `srv.cohort_fingerprint()` vs. the manifest's recorded value.

## 18. Cohort fingerprint

**`5dd9062951fd134400d466c4b2489222a7b8573902a69d5d56b4c02a1b769c74`** — computed at capture time and independently reconfirmed by the review server reading the written CSV back.

## 19. Tests

```
python -m pytest backend/tests/unit/scripts/test_ebay_e2_13_fresh_blind_capture.py backend/tests/unit/scripts/test_ebay_e2_13_blind_review_server.py -q
117 passed

python -m pytest backend/tests/unit/scripts/test_ebay*.py -q
807 passed, 1 failed (pre-existing, unrelated CRLF byte-hash artifact,
already documented in E2.9.x/E2.10/E2.11/E2.12 reports)
```

`test_ebay_e2_13_fresh_blind_capture.py` (18 tests) covers all 14 required areas: E2.9B exclusion (declared + measured zero-overlap), all-prior-cohort exclusion scope, 8-row cap determinism, no-compensation-for-shortfall (both the direct Pecharunt-ex check and a global "no card exceeds the cap" check), policy-independent sampling (AST-verified no identity-stack imports), duplicate-ID prevention, relist exclusion, fixed 70-card universe, new-session-starts-empty, no-model-outputs, row/image binding, fingerprint reproducibility, request-budget-matches-frozen-allocation, and authority-fingerprint immutability.

## 20. Exact command Donny should run to start human review

```
cd D:\EVRCalculator-ebay-e2.9
python -m backend.scripts.ebay_e2_13_blind_review_server
```

Opens a local server at row 1 of 553, session `e2_13_session_1`, reviewed 0/553.

## What did NOT happen (per explicit instruction)

- D3-v5 was **not** re-scored against this new cohort.
- IMAGE-v2 was **not** run against this new cohort.
- COMBINED-IDENTITY-v2 was **not** run against this new cohort.
- No certification metric was calculated.
- E2.9B was **not** recertified or reused for labels.
- Identity logic, CAPTURE-ALLOCATION-v2, Fair Value, and Explorer were untouched. No prices published.
- Nothing staged, committed, or pushed.

---

## Final result

**`EBAY_CAPTURE_ALLOCATION_V2_FRESH_BLIND_READY_FOR_HUMAN_LABELING`**

A genuinely new, real, policy-blind 553-row cohort (70/70 target cards, 8 rows each except the one honestly-reported shortfall card) was captured live from eBay after CAPTURE-ALLOCATION-v2's freeze, using the durably-preserved canonical-resolution manifest and excluding every prior cohort including E2.9B (0 overlap, independently proven). The review session (`e2_13_session_1`, reviewed_count=0) reuses the corrected V5/E2.9B review UX verbatim, validated by 99 adapted passing tests plus 18 new E2.13-specific tests, all against the real captured queue. No model, image, or policy output exists anywhere in the reviewer-facing data. Human labeling has not begun.
