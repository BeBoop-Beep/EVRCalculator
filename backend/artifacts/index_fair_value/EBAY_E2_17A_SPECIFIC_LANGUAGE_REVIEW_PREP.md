# EBAY E2.17A — Japanese-Specific Human Language Review UI (PREP)

## Starting state

E2.17 verdict: `EBAY_OCR_V1_NOT_READY_INSUFFICIENT_AUTHORITATIVE_JAPANESE_SPECIFIC_HUMAN_TRUTH`.
Queue: `backend/artifacts/index_fair_value/ebay_e2_17_japanese_specific_language_review_queue.csv`
(25 rows). Every row already carries a frozen NON_ENGLISH parent human label
from the E2.16 / E2.16B development corpora (rows were selected because they
were already labeled NON_ENGLISH there). Only `specific_language_if_known` is
blank and needs collecting. This task builds the review UI/tooling only — no
OCR analysis was run, and no human labeling was performed.

## What was built

- `backend/scripts/ebay_e2_17a_specific_language_review_server.py` — new,
  dedicated review server (does not touch or reuse E2.16/E2.16B session
  files). Reuses the proven architecture: stable row cursor, row/image
  binding, no-store cache headers, Previous, Undo, edit/relabel, append-only
  JSONL history, explicit reviewer ID, reviewed-count separated from row
  position, `--summary`/`--freeze` CLI flags, session invalidation via
  `labels_frozen`.
- Human label options (additive, on top of the frozen NON_ENGLISH parent
  truth — no ENGLISH option, per spec): `JAPANESE`, `KOREAN`, `CHINESE`,
  `OTHER_NON_ENGLISH`, `UNCERTAIN`.
- Reviewer sees only: row ID (`queue_row_id`), target card identity
  (`canonical_card_id`), and the listing image. The `REVIEWER_VISIBLE_COLUMNS`
  allow-list in the server is the sole mechanism populating the page — the
  `listing_title_DO_NOT_USE_AS_EVIDENCE` column is loaded (kept present in
  the CSV) but is never in that allow-list and is never rendered. No provider
  `Language` aspect, OCR output, OCR character counts/confidence, sampling
  stratum, or policy output exist in the queue CSV at all (verified — see
  integrity checks), so there is no code path for those to leak.
- In-page guidance text reproduces the exact JAPANESE/KOREAN/CHINESE/
  OTHER_NON_ENGLISH/UNCERTAIN decision criteria from the task spec.
- Freeze support records: corpus fingerprint (order-independent hash of
  `queue_row_id:source_row_id:source_corpus:canonical_card_id`), specific-
  language label fingerprint, reviewer ID, row count (25), label counts,
  `development_only=true`, `production_authority=false`. Freeze asserts
  `PARENT_TRUTH_IDENTITY_COLUMNS` (`queue_row_id`, `source_row_id`,
  `source_corpus`, `canonical_card_id`) are byte-identical before/after —
  refuses (`FreezeRefused`) if the frozen NON_ENGLISH parent-truth linkage
  would be mutated.
- New artifact paths (created fresh on first real run, currently absent —
  initial state is reviewed=0/labels blank/history empty):
  `backend/artifacts/index_fair_value/ebay_e2_17a_specific_language_review_manifest.json`
  `backend/artifacts/index_fair_value/ebay_e2_17a_specific_language_review_history.jsonl`

## Command to start review

```
python backend/scripts/ebay_e2_17a_specific_language_review_server.py --reviewer donny
```

Progress check: `--summary`. Freeze after all 25 rows are labeled:
`--freeze`.

## Integrity checks (automated, executed for real)

`backend/tests/test_ebay_e2_17a_specific_language_review.py` — 34 pytest
tests, **all passing** (`python -m pytest
backend/tests/test_ebay_e2_17a_specific_language_review.py -v` → `34 passed`).
Plus a live-server smoke check run against a real `ThreadingHTTPServer`
instance on `127.0.0.1` (label/previous/undo exercised over real HTTP), then
the resulting manifest/history test artifacts were deleted so the real queue
stays at initial state.

| # | Check | Result |
|---|---|---|
| 1 | Exactly 25 rows | PASS — `test_exactly_25_rows` |
| 2 | Parent NON_ENGLISH truth unchanged | PASS — `test_freeze_does_not_mutate_identity_columns`, `test_assert_parent_truth_identity_unchanged_detects_mutation` |
| 3 | Specific-language labels blank initially | PASS — `test_specific_language_blank_initially`, `test_fresh_sandbox_has_zero_reviewed` |
| 4 | Provider Language hidden | PASS — `test_no_forbidden_columns_in_real_queue`, `test_assert_reviewer_blind_raises_on_leak` |
| 5 | OCR evidence hidden | PASS — `test_rendered_page_has_no_forbidden_evidence` |
| 6 | Title not rendered | PASS — `test_title_column_not_in_allowlist`, `test_title_never_appears_in_any_rendered_row` |
| 7 | All available images render | PASS — `test_image_url_renders_for_every_row`; live HTTP check confirmed `<img>` present |
| 8 | First/middle/last row navigation | PASS — `test_first_middle_last_navigation`, `test_next_unreviewed_index_walks_all_rows`; live `?row=` nav confirmed |
| 9 | Previous works | PASS — `test_previous_moves_index_back`, `test_previous_clamps_at_zero`; live `/previous` confirmed position moved 10→9 (row index) |
| 10 | Undo works | PASS — `test_undo_reverts_last_label`, `test_undo_with_no_labels_returns_none`; live `/undo` confirmed REVIEWED count 1→0 |
| 11 | Relabel works | PASS — `test_relabel_overwrites_effective_label` |
| 12 | Fingerprint deterministic | PASS — `test_corpus_fingerprint_deterministic` (order-independent), `test_label_fingerprint_deterministic` (independent sandbox reproduces same fingerprint) |
| 13 | No frozen OCR/policy artifact modified | PASS — `test_feasibility_report_not_modified_by_import`, `test_real_queue_csv_not_mutated_by_test_suite` |
| 14 | `development_only` remains true | PASS — `test_summary_development_only_true`, `test_freeze_manifest_development_only_true` |

Additional freeze-safety coverage exercised: refuses freeze when rows
incomplete, refuses double-freeze, refuses further history writes once
frozen (`ReviewFrozen`).

## Confirmed unchanged

Real queue CSV re-verified after all testing: 25 rows,
`specific_language_if_known` blank on every row, identical to the
pre-task copy. No E2.16/E2.16B/E2.17 frozen artifact was modified.
Test-run manifest/history files created by the live-server smoke check
were deleted; on Donny's first real invocation these will be created
fresh with `reviewed=0`, blank labels, empty history.

EBAY_E2_17A_SPECIFIC_LANGUAGE_REVIEW_READY
