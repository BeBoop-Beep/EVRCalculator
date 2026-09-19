# EBAY E2.16B -- Japanese Language-Aspect DEVELOPMENT Extension

**Status: corpus + review tooling built. NO human labeling performed. NO frozen policy (LANGUAGE-v1, COMBINED-IDENTITY-v3) modified.**

Locked starting state: E2.16A froze LANGUAGE-v1's authoritative non-English mismatch vocabulary to `{KOREAN, CHINESE}` only. Japanese and French were excluded because each had exactly one human-confirmed-ENGLISH development row carrying an explicit non-English provider `Language` aspect (a false mismatch). This task investigates whether Japanese specifically can be supported by a larger, dedicated development sample. It performs **corpus construction and review-UI setup only** -- it does not label anything and does not decide the Japanese question.

---

## 1. Forensics on the existing Japanese false positive

Row: `e2_16_dev_0153` (E2.16 development corpus, adjudicated in E2.16A).

| Field | Value |
|---|---|
| `listing_item_id` | `v1\|317094720076\|0` |
| `item_url` | https://www.ebay.com/itm/317094720076 |
| Target identity | Reshiram ex, White Flare #166, `special_illustration_rare` |
| Listing title | "Reshiram ex 158/086 White Flare" |
| Condition | Ungraded |
| Seller | `raflo-1416` |
| Image (captured) | `https://i.ebayimg.com/images/g/o9UAAeSwXLFoenHp/s-l1600.jpg` (single image URL preserved by the E2.16 capture; E2.16's raw-internal schema stored only `image_url`, not a full image array) |
| `search_language_term` (query that surfaced this row) | `German` |
| `development_stratum` | `LATIN_SCRIPT_FOREIGN` |
| Provider `language_aspect_raw` | `"Japanese"` |
| `language_aspect_normalized` | `JAPANESE` |
| `localized_aspect_count` | 25 (full raw `localizedAspects` array was **not** preserved in the E2.16 raw-internal artifact -- only the extracted Language field and a count; E2.16's builder discarded the rest) |
| Human truth label (E2.16 review, frozen, not touched here) | `ENGLISH` |
| Sampling stratum interpretation | Card was surfaced via a **German**-language search query, yet the getItem aspect said **Japanese** -- itself a signal the aspect is inconsistent with the search context that found the listing |

**Multiple cards / stock-photo / variant conflict:** cannot be independently re-verified beyond what E2.16A already recorded, because the E2.16 raw-internal record for this row retains only a single `image_url`, not the full listing image set or the full `localizedAspects` array. This is a real limitation of the prior capture, not something this task can retroactively fix without re-fetching the (possibly now-sold/removed) original listing. E2.16A's own analysis (Section 11 of `EBAY_E2_16A_LANGUAGE_ASPECT_VALIDATION.md`) already reached the strongest supportable conclusion from the same available evidence: *"Title and reviewer both say the physical card/photo is English; seller's structured Language aspect says Japanese. Most likely explanation: seller aspect metadata error (a bulk-lister mis-tagging or copy-pasting the aspect from a different SKU/variant listing template) -- the title explicitly names an English-language product line ('White Flare' is a real EN-market set), which argues against a genuine Japanese physical card being mislabeled by the human reviewer."*

**Root-cause classification: `PROVIDER_ASPECT_WRONG`** (seller-side structured-metadata error, most likely a copy/boilerplate mistake from a different SKU or variant listing template within the same seller's inventory -- e.g. the seller also lists a genuine Japanese-market printing of a similar card and the Language aspect field defaulted or was copy-pasted across listings). This is consistent with, and does not override, E2.16A's own findings; no frozen human label was changed.

This row's `listing_item_id` (`v1|317094720076|0`) is explicitly excluded from the new E2.16B corpus (verified by test `test_historical_exclusion_specifically_covers_known_bad_rows`), so E2.16B cannot re-sample the exact same listing.

## 2. Historical exclusions applied

E2.16B's builder (`backend/scripts/build_ebay_e2_16b_japanese_language_development_cohort.py`) reuses the E2.16 builder's full `HISTORICAL_FILES` list unchanged (covering D2, D3 v3/v4/v5, V4, V5, E2.9B, E2.13) and adds three more sources:

| Source | File | IDs contributed |
|---|---|---|
| D2 | `ebay_manual_gold_labels.csv`, `ebay_gold_development/validation/final_blind.csv` | 1,050 + 450 + 250 + 350 |
| D3 v3/v4/v5 | `ebay_d3_*_blind_queue/coverage/precision/forensics.csv` | 704 + 420 + 9,591 + 300 + 420 + 5 + 300 + 420 |
| V4 | (covered by D2 gold files above) | -- |
| V5 | `ebay_d3_v5_fresh_blind_queue.csv` | 417 |
| E2.9B | `ebay_e2_9b_fresh_blind_queue.csv` | 414 |
| E2.13/E2.14 | `ebay_e2_13_fresh_blind_queue.csv` + `ebay_e2_14_fresh_blind_predictions.json` | 553 + 553 (includes the E2.14 catastrophic `WRONG_LANGUAGE` row **E13-0127** / `v1\|407215142815\|0`) |
| E2.15 | `ebay_e2_15_item_detail_language_study.json` | 38 |
| E2.16/E2.16A | `ebay_e2_16_language_development_queue.csv` (E2.16A analyzed this same corpus without adding new listings, so excluding it transitively covers E2.16A) | 200 (includes the Japanese false-positive row `e2_16_dev_0153` / `v1\|317094720076\|0`) |

**Total unique excluded listing IDs: 12,131.** Both specifically-named known-bad rows (E13-0127 and e2_16_dev_0153) are confirmed members of the exclusion set and confirmed absent from the new E2.16B queue (test `test_historical_exclusion_specifically_covers_known_bad_rows`, passing).

## 3. New capture size

**150 rows** selected (within the requested 120-180 range, hit the preferred ~150 target exactly). Candidate pool before selection: 320 getItem-resolved listings.

## 4-6. Stratum counts

| Stratum | Selected | Candidate pool |
|---|---|---|
| A. `JAPANESE_ASPECT_PRIMARY` (getItem Language == Japanese) | **92** | 92 |
| B. `ENGLISH_ASPECT_CONTROL` (getItem Language == English) | **30** | 192 (quota-capped at 30 per spec's ~20-30 target) |
| C. `JAPANESE_QUERY_HARD_CASE` (Japanese-targeted search hit, Language aspect missing) | **25** | 25 |
| Leftover/other (unclassified, topped up to reach 150) | 3 | 11 |

Stratum A landed below the 100-120 target midpoint (92 vs. requested ~100-120) because the live search-then-getItem pipeline's actual Japanese-tagged-listing yield, within the request budget, produced exactly 92 qualifying candidates -- reported honestly rather than padded. Strata B and C both hit their targets fully. No rows were fabricated to fill quotas.

## 7. Historical exclusion mechanism verified

Confirmed via `test_historical_id_exclusion_no_overlap` (zero overlap between the 12,131-ID exclusion set and the 150 new rows) and `test_historical_id_exclusion_covers_expected_files` (all expected source files present and counted).

## 8. getItem request count

**320 getItem calls, 140 search calls, 0 search errors, 0 getItem errors** (well within the builder's budget caps of `MAX_GETITEM_REQUESTS=320` and `MAX_SEARCH_REQUESTS=160`). All calls were live eBay Browse API calls (token acquired via the existing `TokenProvider`/`load_ebay_env` in `backend/scripts/index_fair_value_ebay_evidence_collector.py`); no responses were fabricated or mocked.

## 9. Image availability

132 of 150 rows (88%) carry more than one listing image (`image_urls_json`), captured via a new `_all_image_urls()` helper that reads `item["image"]` plus `item["additionalImages"]` from the live getItem response -- an improvement over E2.16's single-`image_url` schema, specifically to support the task's multi-image/variant-conflict reviewer requirement. All 150 rows have at least one image.

## 10. Reviewer-blinding proof

The reviewer-facing queue CSV (`ebay_e2_16b_japanese_language_development_queue.csv`) contains only: `row_id, listing_item_id, item_url, listing_title, condition, buying_options_json, seller_id, image_url, image_urls_json, target_card_name, target_set_name, target_card_number, target_treatment, human_truth_label, human_language_if_known, reviewer_id, label_timestamp, review_note`. It contains **no** `language_aspect_raw`, `language_aspect_normalized`, `language_aspect_present`, `development_stratum`, `search_language_term`, or any policy-output column. This is enforced, not just documented, via `assert_reviewer_blind()` in the review server, which raises `FreezeRefused` if any of `FORBIDDEN_REVIEWER_COLUMNS` is present, called at server startup and at `--freeze`. Tests confirm: the real queue passes blinding (`test_assert_reviewer_blind_passes_on_real_queue`), a poisoned copy with a leaked `language_aspect_raw` or `development_stratum` column is rejected (`test_assert_reviewer_blind_rejects_leaked_column`, `test_assert_reviewer_blind_rejects_leaked_stratum`), and the rendered HTML page never contains the strings `language_aspect`, `development_stratum`, or any of the three stratum names (`test_rendered_page_never_contains_forbidden_evidence`). The hidden Language aspect, full `raw_localized_aspects`, and sampling stratum are retained only in the internal-only `ebay_e2_16b_japanese_language_development_raw_internal.jsonl`.

## 11. Review session id

Not yet created -- `review_session_id` is `null` in the manifest and is assigned on first server launch (matches the E2.16 pattern: idempotent, set once).

## 12. Reviewed count

`reviewed_count: 0`, `labels_frozen` absent (unset), confirmed by `--summary`:
```
{"total_rows": 150, "reviewed_rows": 0, "remaining_rows": 150, "frozen": false, "development_only": true, "production_authority": false}
```

## 13. Tests

`backend/tests/test_ebay_e2_16b_japanese_language_development.py` -- **32 tests, all passing** (`python -m pytest backend/tests/test_ebay_e2_16b_japanese_language_development.py -q` -> `32 passed`). Coverage: historical ID exclusion (general + the two specifically named bad rows), Japanese-primary/English-control/hard-case stratum sampling, reviewer blinding (columns + rendered page + leaked-column rejection), raw internal evidence preservation (including `raw_localized_aspects`), duplicate prevention (item IDs and row IDs), session starts at 0 reviewed, row/image binding (including multi-image rendering), fingerprint determinism, development-only contract (`development_only`, `production_authority`, `modifies_frozen_language_v1`, `modifies_frozen_combined_v3` all correctly `True`/`False`/`False`/`False`), no production-module imports, and that the E2.16B builder/server never open E2.16/E2.16A's own artifact files in write mode.

## 14. Exact review command

```
python -m backend.scripts.ebay_e2_16b_japanese_language_development_review_server --reviewer donny --port 8917
```

(`--summary` prints progress without opening the browser; `--freeze` materializes final labels once all 150 rows are reviewed -- not run in this task.)

---

## Files created

- `backend/artifacts/index_fair_value/ebay_e2_16b_japanese_language_development_queue.csv` (150 rows, reviewer-facing, blind)
- `backend/artifacts/index_fair_value/ebay_e2_16b_japanese_language_development_manifest.json`
- `backend/artifacts/index_fair_value/ebay_e2_16b_japanese_language_development_raw_internal.jsonl` (150 rows, full hidden evidence: Language aspect, `raw_localized_aspects`, stratum, all image URLs)
- `backend/scripts/build_ebay_e2_16b_japanese_language_development_cohort.py`
- `backend/scripts/ebay_e2_16b_japanese_language_development_review_server.py`
- `backend/tests/test_ebay_e2_16b_japanese_language_development.py`

## Explicit non-actions (per spec)

- No human labeling performed (this is Donny's task, E2.16C).
- LANGUAGE-v1 (`{KOREAN, CHINESE}`) and COMBINED-IDENTITY-v3 remain frozen and unmodified.
- No certification blind captured.
- French remains unexpanded/UNVERIFIED.
- No OCR built.
- No writes to Fair Value, Market Explorer, or any production/public-price surface.
- E2.16 and E2.16A's own artifacts were read-only inputs (historical exclusion source) and were never opened in write mode by any new E2.16B code (verified by test).

---

EBAY_E2_16B_JAPANESE_DEVELOPMENT_READY_FOR_HUMAN_LABELING
