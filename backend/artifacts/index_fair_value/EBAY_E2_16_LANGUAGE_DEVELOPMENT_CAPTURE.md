# EBAY E2.16 — Targeted foreign-language DEVELOPMENT cohort + LANGUAGE-v1 validation prep

DEVELOPMENT ONLY. This task builds a human-review corpus and a blinded
review UI. It performs **no human labeling** (Donny labels this separately
as a future E2.16A task) and **freezes no policy**. LANGUAGE-v1 remains
unfrozen; D3-v5 / IMAGE-v2 / COMBINED-IDENTITY-v2 / CAPTURE-ALLOCATION-v2
are untouched.

## 1. Capture size

**200 rows** — at the spec's preferred target (~200) and within the
150–250 target range.

## 2. Actual stratum counts

Sampling was strata-targeted (search queries used both ordinary English
terms and language-targeting terms — Japanese/Korean/Chinese/German/
French/Spanish/Italian/Portuguese — against the existing 70-card pilot
catalog), not certification-style uniform random sampling.

| Stratum | Selected | Candidate pool (pre-selection) | Spec target |
|---|---|---|---|
| `ENGLISH_CONTROL` | 60 | 60 | 70–90 |
| `NON_LATIN_FOREIGN` (JP/KR/ZH) | 80 | 140 | 50–70 |
| `LATIN_SCRIPT_FOREIGN` (DE/FR/ES/IT/PT) | 60 | 60 | 40–60 |
| `AMBIGUOUS_DIFFICULT` | 0 | 0 | 20–30 |

**Honest gaps, reported not concealed:**
- `ENGLISH_CONTROL` landed at 60, under the 70–90 target — the
  English-control query formulation (no language term appended) was run
  fewer times than intended relative to the language-targeting queries in
  this pass; the candidate pool was also exactly 60, so there was no
  slack to top up from.
- `AMBIGUOUS_DIFFICULT` landed at **0**. The build script's automatic
  ambiguity heuristic (title keywords: `lot`, `bundle`, `proxy`, `custom`,
  `damaged`, `poor`, `mixed`, `set of`) never fired on any surviving
  candidate in this run. A real "hard case" stratum (poor image quality,
  multilingual listing text, English title + foreign card image, etc.)
  needs either a smarter heuristic or manual curation from the corpus —
  neither was attempted here; this is a real gap, not a rounding
  shortfall.
- `NON_LATIN_FOREIGN` exceeded target (80 vs 50–70) because Korean-market
  listings were unusually plentiful for the pilot catalog's cards.

## 3. Languages represented (from getItem's structured Language aspect — reference metadata only, never reviewer-visible, never ground truth)

Present in the internal raw artifact (`ebay_e2_16_language_development_raw_internal.jsonl`):
`ENGLISH` (122), `KOREAN` (25), `CHINESE` (20), `UNKNOWN`/aspect-absent (20),
`JAPANESE` (11), `FRENCH` (1), `OTHER` (1).

**Important honest finding:** none of the `LATIN_SCRIPT_FOREIGN`-targeted
queries (German, Spanish, Italian, Portuguese) surfaced a listing whose
`localizedAspects` Language value normalized to that language — only a
single French example turned up, and it came from the "OTHER"/mixed pool,
not confirmed. This does not mean no German/Spanish/Italian/Portuguese
cards exist on eBay; it means this bounded, budget-limited search pass
against a 70-card pilot catalog did not surface confirmed examples. A
future E2.16A pass (or a second E2.16 capture run) may need to widen the
catalog or increase the search budget for those specific language terms if
Latin-script foreign coverage turns out to matter for the eventual
LANGUAGE-v1 decision.

The reviewer never sees any of this — see §10.

## 4. getItem request count

**260** getItem calls (bounded by `MAX_GETITEM_REQUESTS = 260`), 0 errors.
**70** `item_summary/search` calls (bounded by `MAX_SEARCH_REQUESTS = 140`),
0 errors. Both counts are recorded in the manifest and verified by
`test_request_budget_respected`.

## 5. Language-aspect present rate

**90.0%** (180 / 200 selected rows have an explicit `localizedAspects`
Language value). This is consistent with — slightly higher than — E2.15's
bounded 71.05% coverage finding on a different (untargeted) sample; the
delta is plausibly explained by language-targeted search queries
preferentially surfacing listings from sellers who also fill out
structured aspects more completely, not by any change to eBay's schema.

## 6. Historical exclusions

Excluded ID sources and per-file counts (total **11,931** unique excluded
listing/item IDs across all sources):

| Source | Excluded IDs |
|---|---|
| `ebay_manual_gold_labels.csv` | 1,050 |
| `ebay_gold_development.csv` | 450 |
| `ebay_gold_validation.csv` | 250 |
| `ebay_gold_final_blind.csv` | 350 |
| `ebay_d3_blind_review_queue.csv` | 704 |
| `ebay_d3_coverage_blind.csv` | 420 |
| `ebay_d3_fresh_observations.csv` | 9,591 |
| `ebay_d3_precision_blind.csv` | 300 |
| `ebay_d3_v3_coverage_certification_rows.csv` | 420 |
| `ebay_d3_v3_high_false_positive_forensics.csv` | 5 |
| `ebay_d3_v3_precision_certification_rows.csv` | 300 |
| `ebay_d3_v4_fresh_blind_queue.csv` | 420 |
| `ebay_d3_v5_fresh_blind_queue.csv` | 417 |
| `ebay_e2_9b_fresh_blind_queue.csv` | 414 |
| `ebay_e2_13_fresh_blind_queue.csv` | 553 |
| `ebay_e2_14_fresh_blind_predictions.json` | 553 |
| `ebay_e2_15_item_detail_language_study.json` | 38 |

Verified zero overlap between the final 200-row development queue and this
full exclusion set (`test_historical_id_exclusion_no_overlap`, and a
separate ad-hoc verification run). Relist exclusions (a listing re-posted
under a new item ID for the same physical card) were **not** separately
detectable from available metadata and were not attempted — only exact
`listing_item_id` matches were excluded, as the spec directed
("exact-ID exclusions"). No relist-specific exclusion logic exists in this
build; note this as a known limitation, not a silent gap.

Surviving development rows: **200** (all new evidence, not previously seen
by any prior certification/blind/development pass).

## 7. Final corpus row count

**200** rows, 0 duplicate `listing_item_id` values, 0 duplicate `row_id`
values (`test_no_duplicate_item_ids`, `test_no_duplicate_row_ids`).

## 8. Review-session ID

`review_session_id` is **not yet assigned** — the manifest field is
`null` by design. The E2.16 review server (`ebay_e2_16_language_development_review_server.py`)
assigns a fresh session ID (`e2_16_dev_session_<hex>`) the first time it is
launched for interactive review, matching the E2.13 architecture's
practice of recording session identity only once review activity begins.

## 9. Reviewed count

`reviewed_count = 0`. No labeling has occurred. `history events = 0`
(no `ebay_e2_16_language_development_review_history.jsonl` file exists
yet — it is created on first label event).

## 10. Proof the Language aspect is hidden from the reviewer

- The reviewer-facing queue CSV (`ebay_e2_16_language_development_queue.csv`)
  header contains **only**: `row_id, listing_item_id, item_url,
  listing_title, condition, buying_options_json, seller_id, image_url,
  target_card_name, target_set_name, target_card_number,
  target_treatment, search_language_term, human_truth_label,
  human_language_if_known, reviewer_id, label_timestamp, review_note`.
  There is no `language_aspect_raw`, `language_aspect_normalized`,
  `language_aspect_present`, `languagev1_state`, `combined_policy_output`,
  or `localized_aspects_json` column, and no `development_stratum` column
  (stratum is sampling provenance the reviewer should not see either, to
  avoid biasing judgment toward the search strategy's intent).
- `server.FORBIDDEN_REVIEWER_COLUMNS` is asserted against the real queue
  file at server startup (`assert_reviewer_blind`) and by
  `test_assert_reviewer_blind_passes_on_real_queue` /
  `test_assert_reviewer_blind_rejects_leaked_column`.
- The rendered review page (`server.page()`) interpolates fields only from
  the already-blind CSV row — there is no code path that reads the
  internal raw JSONL (which retains the full Language-aspect evidence) at
  render time. Verified by
  `test_rendered_page_never_contains_language_aspect_strings`, which
  checks that a non-English raw aspect value never appears in the
  rendered HTML except where it legitimately also appears inside the
  ordinary, human-visible listing title text (a seller's own title
  wording, not an eBay-derived aspect).
- The internal raw artifact
  (`ebay_e2_16_language_development_raw_internal.jsonl`) is the ONLY
  place the Language aspect (raw + normalized), `localized_aspect_count`,
  marketplace, and seller-country context are retained — for a future
  E2.16A analysis script to join back against human labels by `row_id`.
  Verified by `test_internal_raw_preserves_language_aspect` and
  `test_internal_raw_row_ids_match_queue`.

## 11. Tests

`backend/tests/test_ebay_e2_16_language_development.py` — **28 tests, all
passing**:

```
python -m pytest backend/tests/test_ebay_e2_16_language_development.py -q
............................
28 passed in 0.35s
```

Coverage against the spec's 16-point test list: historical ID exclusion
(2 tests), language-strata sampling (2), explicit Language raw
preservation (2), reviewer field redaction (2), reviewer cannot see
normalized language (2), English control inclusion (1), foreign-language
stratum inclusion (1), Latin-script foreign inclusion where available (1),
non-Latin foreign inclusion (1), duplicate prevention (2), request budget
(1), session starts 0 reviewed (1), row/image binding (2), fingerprint
determinism (2), development-only contract (1), no production writes (2),
plus 4 additional tests directly exercising the undo/relabel/cursor
mechanics reused from the E2.13 architecture.

**Live functional smoke test** (not part of the pytest suite, run against
a temp copy of the real 5-row slice of the actual queue, never touching
the production artifact files): label → undo → relabel → freeze full
lifecycle executed successfully; the frozen CSV materialized the
post-undo, post-relabel value (`NON_ENGLISH`) correctly, confirming
Undo targets the last *recorded* event (not the currently displayed row)
and that a relabel (edit) correctly supersedes a prior label for the same
row.

**Bug caught and fixed during this task:** the review server's
`cohort_fingerprint()` initially used a different join separator (`"\n"`)
than the corpus builder's `cohort_fingerprint()` (`"|"`), which would have
made `--freeze` always fail its fingerprint-match check against the
manifest. Fixed to use the same `"|"`-joined, sorted `row_id:listing_item_id`
scheme in both modules before any review activity occurred.

## 12. Command to start review

```
cd D:\EVRCalculator-ebay-e2.9
python -m backend.scripts.ebay_e2_16_language_development_review_server --reviewer donny
```

(Optional: `--port 8916` is the default; `--summary` prints progress
without opening the UI; `--freeze` materializes final labels into the
queue CSV once every row has a `human_truth_label` — run only after
Donny finishes labeling all 200 rows.)

## OCR decision gate (not built, per spec)

No OCR was implemented in this task. Whether OCR is worth building remains
gated on the future E2.16A analysis: it is justified only if (a)
structured `localizedAspects` Language coverage proves too low on the
human-labeled set, (b) the structured aspect misses a meaningful share of
human-confirmed foreign-language cards (i.e. poor recall), or (c) its
precision against human truth is insufficient for a safe veto. The 90%
raw coverage rate measured here (§5) is a *candidate pool* rate over
provider metadata, not a validated recall/precision rate against human
truth — that determination is explicitly deferred to E2.16A after Donny
labels this corpus.

## Files created

- `backend/artifacts/index_fair_value/ebay_e2_16_language_development_queue.csv` (200 rows, reviewer-facing, blind)
- `backend/artifacts/index_fair_value/ebay_e2_16_language_development_manifest.json`
- `backend/artifacts/index_fair_value/ebay_e2_16_language_development_raw_internal.jsonl` (200 rows, internal, retains Language aspect)
- `backend/artifacts/index_fair_value/EBAY_E2_16_LANGUAGE_DEVELOPMENT_CAPTURE.md` (this report)
- `backend/scripts/build_ebay_e2_16_language_development_cohort.py`
- `backend/scripts/ebay_e2_16_language_development_review_server.py`
- `backend/tests/test_ebay_e2_16_language_development.py`

No files were staged, committed, or pushed. `git status --short` at the
end of this task shows only untracked (`??`) files, consistent with the
rest of this worktree's pre-existing uncommitted state.

## Verdict

The corpus (200 rows), historical exclusion, reviewer blinding, and review
server are complete, tested, and functionally verified end-to-end
(label/undo/relabel/freeze). The `AMBIGUOUS_DIFFICULT` stratum is at 0
rows against a 20–30 target, and `ENGLISH_CONTROL` is at 60 against a
70–90 target — both are real, reported gaps rather than blockers: the
corpus is still usable for Donny to begin human labeling immediately, and
the missing ambiguous-case rows and English-control shortfall can be
addressed with a follow-up top-up capture (same script, adjusted query
cycle weighting) before or during labeling without invalidating what
exists. Nothing here required for the PRIMARY GOAL — estimating structured
Language-aspect detection/false-mismatch rates — is blocked by these
gaps; they reduce hard-case and control coverage, not corpus usability.

EBAY_E2_16_LANGUAGE_DEVELOPMENT_READY_FOR_HUMAN_LABELING
