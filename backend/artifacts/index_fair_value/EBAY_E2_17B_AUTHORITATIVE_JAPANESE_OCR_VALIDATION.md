# EBAY E2.17B — Authoritative Japanese OCR Validation + OCR-v1 Freeze Decision

Status: DEVELOPMENT RESEARCH ONLY. Does not certify, does not write to production, does not touch Fair Value / Explorer / prices / Capture-Allocation. Nothing in this task was staged, committed, or pushed (worktree `feature/ebay-e2.9-image-veto-tiered-identity`, branch left untouched — verified with `git status --short` at the end of this report).

## 1. Preconditions

- OCR-v1 candidate: `backend/scripts/ebay_e2_17_ocr_v1_japanese_language_feasibility.py`
- Original E2.17 split: `backend/artifacts/index_fair_value/ebay_e2_17_combined_corpus_split.json` (350 rows, 272 DESIGN / 78 HELDOUT)
- Original E2.17 OCR results: `backend/artifacts/index_fair_value/ebay_e2_17_ocr_results.json` (139 rows, 138 successfully OCR'd)
- Frozen specific-language queue: `backend/artifacts/index_fair_value/ebay_e2_17_japanese_specific_language_review_queue.csv` (25 rows)
- Freeze manifest: `backend/artifacts/index_fair_value/ebay_e2_17a_specific_language_review_manifest.json`

## 2. OCR Candidate Provenance (no-retuning verification)

The exact source file that produced the E2.17 results was re-hashed before anything else was read:

- File: `backend/scripts/ebay_e2_17_ocr_v1_japanese_language_feasibility.py`
- SHA-256: `54ad9bf1b33a7247e2a7db52e0e5806c827271cbb0271e96737e0573b9de8212`
- OCR engine: EasyOCR 1.7.2 equivalent runtime already installed in this worktree (`easyocr.Reader(["ja", "en"], gpu=False, verbose=False)`), CPU-only — identical invocation to E2.17.
- Script-rule parameters unchanged (verified by re-reading the source, and by unit-testing the imported constants): `HIRAGANA=(0x3040,0x309F)`, `KATAKANA=(0x30A0,0x30FF)`, `CJK_UNIFIED=(0x4E00,0x9FFF)`, `HANGUL=(0xAC00,0xD7A3)`; `ocr_v1_decision()` thresholds (`high_conf_kana_count>=4` + `distinct_regions_with_kana>=2`, or `high_conf_kana_count>=6` dense-single-region; Hangul guard `korean_hangul_count>=2`; English-match arm `latin_char_count>=8` and `mean_region_conf>=0.35` and `num_regions>=2` with zero kana/CJK) — all identical to the E2.17 listing.
- Original E2.17 split fingerprint: the split file (350 rows, DESIGN/HELDOUT already assigned by canonical-card-id grouping) was **read, not recomputed or reshuffled**. All 25 specific-language rows resolve unambiguously by `source_row_id` into this pre-existing split.
- Original E2.17 OCR results fingerprint: 139 rows, matches the `EBAY_E2_17_OCR_V1_JAPANESE_LANGUAGE_FEASIBILITY.md` reported numbers exactly (see §8 below): 65 ENGLISH rows / 0 false mismatches, 70 NON_ENGLISH rows / 36 mismatches / 34 unverified, 4 UNCERTAIN rows / 4 unverified.

**No character thresholds, confidence thresholds, crop rules, Unicode rules, row-specific exceptions, or OCR engine were changed.** The candidate module was `importlib.import_module`'d and its `run_ocr()` / `ocr_v1_decision()` functions were called unmodified — never reimplemented — including for the 11 of 25 rows that required a first-time OCR pass (§3). Provenance is proven unchanged: **not blocked.**

## 3. Original Split Membership for the 25 Rows

14 of the 25 specific-language rows already had OCR output in the original 139-row `ebay_e2_17_ocr_results.json` file. The other 11 rows had never been OCR'd before (they existed in the split but were outside the original E2.17 sampled/fetched subset). Per the working notes, running the **unchanged** candidate on new rows is evaluation, not retuning — so the unchanged rule was applied to those 11 rows for the first time, using the identical imported `run_ocr`/`ocr_v1_decision` functions, fetching the same eBay image URLs already present in the queue/split files. Output: `backend/artifacts/index_fair_value/ebay_e2_17b_supplemental_ocr_results.json` (includes the source SHA-256 for auditability). All 11 of these newly-OCR'd rows happen to be **DESIGN**-split rows; no HELDOUT row required a fresh OCR pass.

Split membership of the 25 authoritative rows, by specific language:

| Specific language | DESIGN | HELDOUT | Total |
|---|---|---|---|
| JAPANESE | 12 | **4** | 16 |
| CHINESE | 4 | 1 | 5 |
| KOREAN | 2 | 2 | 4 |
| **Total** | 18 | 7 | 25 |

The original card-identity-grouped DESIGN/HELDOUT assignment was **not reshuffled** after seeing the specific-language labels — every row's split is exactly what the (label-blind) `ebay_e2_17_combined_corpus_split.json` file already recorded.

## 4. Authoritative Label Counts (Phase A)

Independently recomputed from the frozen CSV using the exact fingerprint formulas in `ebay_e2_17a_specific_language_review_server.py`:

- Row count: **25** (matches `EXPECTED_ROW_COUNT`)
- Corpus fingerprint (recomputed): `4a5607b94dbdfb7c5123316c2855a181903f0089b5bf66015491febc3e9e4333` — **MATCHES** manifest.
- Specific-language label fingerprint (recomputed): `3dc900663abc939c64564383fe79234aea01b7abd7d252e5f1c3ce562ba0dda9` — **MATCHES** manifest.
- Label counts: JAPANESE=16, CHINESE=5, KOREAN=4, UNCERTAIN/OTHER=0 — **matches** task statement.
- Manifest: `labels_frozen=true`, `reviewer_protocol=SINGLE_REVIEWER_BLIND_DEVELOPMENT_E2_17A`, `development_only=true`, `production_authority=false`. Freeze timestamp `2026-09-17T04:01:16Z`, session `e2_17a_dev_session_8889bd6b19e0`.
- Parent NON_ENGLISH labels: every row's identity columns (`queue_row_id`, `source_row_id`, `source_corpus`, `canonical_card_id`) were verified unchanged by the freeze routine itself (`assert_parent_truth_identity_unchanged`), and cross-checked here by re-joining each `source_row_id` back to its E2.17 split row — all 25 rows still carry `human_truth_label = NON_ENGLISH` in the split file. No post-freeze mutation is possible: the review server raises `ReviewFrozen` on any further history write once `labels_frozen=true`, and this task made none.
- Reviewer metadata valid: 25 append-only `label` events in `ebay_e2_17a_specific_language_review_history.jsonl`, one `reviewer_id="donny"` per row, single-reviewer blind protocol, no leaked language-evidence columns in the reviewer-visible CSV.

## 5. Heldout Japanese Results (unbiased primary evidence, Phase C)

Unchanged OCR-v1 candidate applied to the 4 HELDOUT-split human-JAPANESE rows:

| Metric | Value |
|---|---|
| Japanese rows (HELDOUT) | 4 |
| OCR LANGUAGE_MISMATCH (TP) | 3 |
| OCR LANGUAGE_UNVERIFIED (FN) | 1 |
| OCR LANGUAGE_MATCH (FN, unsafe) | 0 |
| Recall | 3/4 = 0.75 |

Chinese/Korean hard negatives, HELDOUT only: CHINESE n=1, Japanese false-mismatch=0. KOREAN n=2, Japanese false-mismatch=0.

**This is the primary, unbiased freeze evidence** — and it is a 4-row sample. See §10.

## 6. All-25 Results (post-hoc development characterization, Phase C)

Unchanged OCR-v1 candidate applied to all 16 human-JAPANESE rows (DESIGN+HELDOUT combined; DESIGN rows may have participated in E2.17 binary-language development, so this is characterization, **not** independent heldout evidence):

| Metric | Value |
|---|---|
| Japanese rows (all 25 universe) | 16 |
| OCR LANGUAGE_MISMATCH (TP) | 12 |
| OCR LANGUAGE_UNVERIFIED (FN) | 4 |
| OCR LANGUAGE_MATCH (FN, unsafe) | 0 |
| Recall | 12/16 = 0.75 |

(Recall is identical, 0.75, in both the heldout-only and all-25 views — coincidental given the small heldout N, not a sign of stability by itself.)

## 7. Chinese/Korean Hard Negatives (Phase F)

All 25 rows, both splits combined:

| Specific language | n | OCR Japanese false-mismatch |
|---|---|---|
| CHINESE | 5 | **0** |
| KOREAN | 4 | **0** |

Raw script evidence (`japanese_kana_count` / `cjk_shared_count` / `korean_hangul_count`):

- CHINESE rows: kana counts {1, 2, 3, 10, 7} — all far below the strong-Japanese threshold; `cjk_shared_count` is high (21–88, expected — shared Han glyphs) but the rule correctly treats CJK-shared count as ambiguous and never triggers mismatch on it alone. All 5 rows resolved `LANGUAGE_UNVERIFIED`.
- KOREAN rows: kana counts {17, 27, 20, 11}; `cjk_shared_count` 39–114 (again shared-Han ambiguity, correctly not treated as Japanese evidence). All 4 rows resolved `LANGUAGE_UNVERIFIED`.
- **Important finding:** `korean_hangul_count == 0` on **every one of the 4 real Korean rows**, in both splits. The reader is loaded as `easyocr.Reader(["ja", "en"], ...)` — it has no Korean model — so it structurally cannot recognize Hangul glyphs as Hangul text; the `korean_hangul_count >= 2` hard-negative guard in `ocr_v1_decision()` **never fires on real data** in this corpus. Korean safety in practice comes entirely from the "kana evidence must clear the high-confidence threshold" arm (none of the 4 Korean rows produced enough `high_conf_kana_count`), not from the documented Hangul-suppression mechanism. This is a real property of the frozen candidate, not something this task is permitted to fix — reported as-is per Phase F/G.
- Confirmed: no isolated shared-CJK glyph, and no Han-only Chinese card, ever triggered the veto in this data; Hangul (when present) never became Japanese either — it just never got a chance to exercise its guard.

## 8. English Safety Reconfirmation (Phase D)

Re-run against the exact frozen 139-row E2.17 OCR results population (same candidate, same rows, no reshuffle after seeing new results):

| Metric | Value |
|---|---|
| Human ENGLISH rows | 65 |
| False JAPANESE mismatches | **0** |
| False-mismatch rate | 0.0 |
| Wilson 95% CI | [0.0, 0.0558] |

Full 139-row truth × decision matrix (unchanged from E2.17, independently recomputed here):

| human_truth_label | ocr_v1_decision | count |
|---|---|---|
| ENGLISH | LANGUAGE_MATCH | 1 |
| ENGLISH | LANGUAGE_UNVERIFIED | 64 |
| NON_ENGLISH | LANGUAGE_MISMATCH | 36 |
| NON_ENGLISH | LANGUAGE_UNVERIFIED | 34 |
| UNCERTAIN | LANGUAGE_UNVERIFIED | 4 |

This exactly reproduces the E2.17 headline numbers (0/65 false English mismatches; mismatch precision 36/36=1.0 vs binary NON_ENGLISH truth; recall 36/70=0.514). English safety is fully preserved — the population was not altered after seeing results.

## 9. OCR Miss Forensics (Phase E)

Script evidence for all 16 human-JAPANESE rows (queue_row_id, split, decision, kana/high-conf-kana/regions-with-kana, cjk, hangul, latin, num_regions, mean_conf):

| row | split | decision | kana | hi-conf kana | regions w/ kana | cjk | hangul | latin | regions | mean conf |
|---|---|---|---|---|---|---|---|---|---|---|
| review_0001 | HELDOUT | MISMATCH | 110 | 37 | 20 | 31 | 0 | 42 | 33 | 0.425 |
| review_0002 | HELDOUT | MISMATCH | 37 | 13 | 8 | 41 | 0 | 13 | 11 | 0.257 |
| review_0004 | DESIGN | MISMATCH | 118 | 63 | 18 | 28 | 0 | 65 | 33 | 0.598 |
| review_0005 | DESIGN | MISMATCH | 72 | 13 | 12 | 24 | 0 | 33 | 19 | 0.265 |
| review_0006 | DESIGN | MISMATCH | 162 | 26 | 26 | 41 | 0 | 63 | 37 | 0.370 |
| review_0007 | DESIGN | **UNVERIFIED (FN)** | 22 | 0 | 4 | 0 | 0 | 2 | 8 | 0.188 |
| review_0008 | DESIGN | MISMATCH | 95 | 15 | 10 | 25 | 0 | 25 | 18 | 0.207 |
| review_0010 | DESIGN | MISMATCH | 102 | 5 | 13 | 32 | 0 | 56 | 26 | 0.294 |
| review_0011 | DESIGN | **UNVERIFIED (FN)** | 28 | 1 | 13 | 27 | 0 | 73 | 24 | 0.130 |
| review_0013 | DESIGN | **UNVERIFIED (FN)** | 43 | 2 | 9 | 36 | 0 | 57 | 21 | 0.213 |
| review_0014 | DESIGN | MISMATCH | 123 | 30 | 24 | 43 | 0 | 69 | 34 | 0.324 |
| review_0015 | HELDOUT | MISMATCH | 126 | 15 | 21 | 56 | 0 | 32 | 36 | 0.298 |
| review_0016 | DESIGN | MISMATCH | 34 | 5 | 13 | 27 | 0 | 47 | 25 | 0.147 |
| review_0020 | HELDOUT | **UNVERIFIED (FN)** | 72 | 0 | 18 | 22 | 0 | 8 | 24 | 0.076 |
| review_0021 | DESIGN | MISMATCH | 31 | 6 | 12 | 25 | 0 | 60 | 24 | 0.249 |
| review_0022 | DESIGN | MISMATCH | 102 | 43 | 16 | 29 | 0 | 31 | 28 | 0.500 |

The 4 misses (all fail-safe to UNVERIFIED, never a false MATCH):

- **review_0007** ("Chaos Rising Mega Greninja EX..."): 22 raw kana chars recognized but `high_conf_kana_count=0` — mean region confidence only 0.188. Cause: low OCR confidence (glare/print sheen or a stylized/full-art layout depressing per-region confidence), not an unreadable image — text was read, just not with enough confidence to clear the conservative threshold. Classified as **conservative rule + low-confidence OCR**.
- **review_0011** ("Victini AR 097/086 SV11B Black Bolt..."): 28 raw kana, `high_conf_kana_count=1`, mean conf 0.130 — the lowest-confidence row in the set. Cause: **low-confidence OCR** (likely glare/small dense text on a full-art holo card), correctly refused by the conservative rule rather than guessed.
- **review_0013** ("Gouging Fire ex 093/071 SV5K..."): 43 raw kana, `high_conf_kana_count=2`, mean conf 0.213. Same pattern — **low-confidence OCR / conservative rule**, not an engine failure (`ocr_ok=True`, 21 regions recognized).
- **review_0020** (HELDOUT; "Archen Archeops AR set 129 130/086..."): 72 raw kana chars recognized (highest raw kana count among the misses) but `high_conf_kana_count=0`, mean conf **0.076** — by far the lowest confidence in the entire Japanese subset. Cause: **severely low OCR confidence**, consistent with glare/perspective/stylized full-art card text, not a crop failure (24 regions were still recognized) and not an engine exception (`ocr_ok=True`).

No miss was caused by unreadable/crop-failed/tiny-text-undetected images (`ocr_ok=True` and `num_regions>0` on all 4), and none by an OCR engine exception. All 4 misses are the conservative high-confidence-kana threshold correctly refusing to call Japanese on genuinely low-confidence OCR reads — exactly the intended fail-safe behavior, not a bug.

## 10. OCR-v1 Freeze Decision (Phase G)

Checking the Phase G required conditions against the heldout evidence (the primary, unbiased evidence per Phase B):

1. Zero/near-zero false Japanese mismatches on human ENGLISH — **met** (0/65, Wilson upper 0.056).
2. Zero/near-zero Japanese misclassification of human CHINESE/KOREAN — **met** (0/9 combined, both splits; 0/3 heldout-only).
3. Meaningful true-positive Japanese detection — **partially met** (3/4 heldout TP; 12/16 all-25 TP).
4. **Heldout Japanese evidence is not trivially small — NOT MET.** The HELDOUT-split human-JAPANESE subset is **N=4**. This is a single-digit sample; a 75% recall point estimate on 4 rows carries a Wilson 95% CI of roughly [0.30, 0.95] — far too wide to responsibly certify a production-facing veto rule's recall.
5. Misses fail to UNVERIFIED rather than unsafe MATCH — **met** (0 unsafe MATCH misses anywhere in the data).
6. CPU performance remains practical — **met** (model load ~1.1s, consistent with E2.17's reported feasibility numbers; no GPU required).
7. No E2.14 tuning occurred — **met** (no thresholds/rules were touched at any point in this task; source hash pinned in §2).

Condition 4 fails. Per the explicit task instruction: *"If the HELDOUT Japanese subset is too small to support a responsible freeze: DO NOT force a freeze."* **OCR-v1 does not freeze.** No production-facing conservative-veto certification can be responsibly drawn from a 4-row heldout Japanese sample, even though every other condition (safety on English/Chinese/Korean, fail-safe miss behavior, CPU practicality, no tuning) is satisfied.

## 11. OCR-v1 Fingerprint — N/A (not frozen)

Not recorded. No `ebay_e2_17b_ocr_v1_freeze.json` artifact was written (verified by test `test_ocr_v1_not_frozen_this_run_no_freeze_artifact_written`). Per Phase H, freezing is contingent on the Phase G decision, which did not clear the bar.

## 12. LANGUAGE-v2 Contract — N/A (gated on OCR-v1 freeze)

Not built or frozen this run, per Phase I's explicit gate ("only if OCR-v1 freezes"). The precedence table specified in the task (provider KOREAN/CHINESE always mismatch; provider-only JAPANESE cannot veto; OCR clear-Japanese can veto regardless of provider; weak/failed OCR never invents a mismatch; French/unsupported → UNVERIFIED) is pinned as pure logic in the test suite (`_language_v2_spec` in the tests file) as a contract for a future implementation, but no production LANGUAGE-v2 module was created or touched.

## 13. COMBINED-v4 Contract — N/A (gated on LANGUAGE-v2 freeze)

Not built or frozen this run, per Phase J's gate. The `LANGUAGE_MISMATCH → REJECTED_LANGUAGE_CONTRADICTION` / `LANGUAGE_MATCH → no promotion change` / `LANGUAGE_UNVERIFIED → unchanged` contract is pinned as pure logic in the test suite (`_combined_v4_spec`) for the same reason.

## 14. E2.14 Post-Hoc — N/A (gated on all three freezes)

Not run. Phase K is explicitly gated on OCR-v1 **and** LANGUAGE-v2 **and** COMBINED-v4 all freezing; none did. The frozen E2.14 certification artifacts (`ebay_e2_14_fresh_blind_certification.json`, `ebay_e2_14_fresh_blind_predictions.json`) were read for context only and are confirmed untouched — this task wrote no `ebay_e2_17b_e2_14_post_hoc_diagnostic.json` file (verified by test). Row E13-0127 (`v1|407215142815|0`) status is therefore **unchanged** from its existing E2.14 certification record; this task made no determination about it.

## 15. V4/V5/E2.9B Post-Hoc — N/A (same gate)

Not run, for the same reason as §14 — Phase L diagnostics are downstream of the same freeze chain, and no tuning or diagnostic run against V4/V5/E2.9B occurred in this task.

## 16. New-Blind Decision

Per the explicit gate: a new independent certification blind is justified only if OCR-v1 freezes AND LANGUAGE-v2 freezes AND COMBINED-v4 freezes AND E13-0127 is rejected AND no new catastrophic error appears AND the E2.14 diagnostic clears Wilson≥0.98/coverage≥0.80. **None of these conditions were reached** because OCR-v1 itself did not freeze. **Not justified.**

## 17. Tests

`backend/tests/unit/test_ebay_e2_17b_authoritative_japanese_ocr_validation.py` — 28 tests, all passing (`python -m pytest backend/tests/unit/test_ebay_e2_17b_authoritative_japanese_ocr_validation.py -q` → `28 passed`). Covers, using real data/fingerprints wherever a real artifact exists (items 1–14, 21), and pure spec-contract logic pins for the gated/not-yet-implemented phases (items 15–20, each explicitly documented as gated-not-frozen rather than faked):

1. specific-language corpus fingerprint (recomputed, matches manifest)
2. specific-language label fingerprint (recomputed, matches manifest) + manifest metadata (frozen/development_only/production_authority/label counts)
3. original split preservation / no reshuffle + DESIGN/HELDOUT counts by specific language
4. Japanese TP (12/16 all-25)
5. Japanese FN fails to UNVERIFIED, never MATCH
6. Chinese never classified Japanese mismatch
7. Korean never classified Japanese mismatch
8. heldout-only Japanese metrics (N=4, TP=3, recall=0.75)
9. all-row Japanese characterization metrics (N=16, TP=12, recall=0.75), plus a test that heldout and all-row views are kept distinct
10. English false-mismatch rate + Wilson interval (0/65, upper<0.06)
11. single Han/CJK glyph alone insufficient (synthetic unit test on imported `ocr_v1_decision`)
12. kana positive triggers mismatch (synthetic unit test)
13. Hangul suppression (synthetic unit test) + a real-data test documenting that the Hangul guard never actually fires on this corpus (§7 finding)
14. OCR candidate immutability (source SHA-256 pinned) + Unicode range constants pinned
15. OCR freeze fingerprint absent (no freeze artifact written)
16-19. LANGUAGE-v2 precedence contract (provider Korean/Chinese always mismatch; provider-only Japanese cannot veto; OCR clear-Japanese can veto; weak OCR never invents a mismatch)
20. COMBINED-v4 language rejection contract (mismatch→rejected; unverified→unchanged)
21. E2.14 post-hoc-only gate (no diagnostic artifact written; frozen E2.14 cert file still present/untouched) + no-production-writes sanity check + supplemental-OCR-results file is clearly labeled non-production

## 18. Next Step

Per Phase G's own recommendation: do not force a freeze. The responsible next step is a **small, additional, independent Japanese-specific development holdout** — specifically more HELDOUT-split rows with human-confirmed JAPANESE labels (current heldout Japanese N=4 needs to grow to something on the order of 20-30+ before a recall estimate is trustworthy enough to certify a production veto). A good source is the existing E2.16/E2.16B corpora: run the same `ebay_e2_17a_specific_language_review_server.py` review flow against additional NON_ENGLISH HELDOUT-split rows that were not part of this 25-row queue, focusing on growing the Japanese HELDOUT count specifically (Chinese/Korean heldout evidence, while also thin at N=1 and N=2, showed 0 false positives and is lower-stakes since OCR-v1's failure mode there is fail-safe-to-UNVERIFIED, not a false accept). Once that holdout exists, re-run this exact Phase C/D/G evaluation (same unchanged OCR-v1 candidate, same fingerprint-verification discipline) before revisiting the freeze decision.

## Files Produced This Run

- `backend/artifacts/index_fair_value/ebay_e2_17b_supplemental_ocr_results.json` — unchanged OCR-v1 candidate applied to the 11/25 rows absent from the original E2.17 OCR run (development-only, clearly labeled).
- `backend/artifacts/index_fair_value/ebay_e2_17b_joined_25rows.json` — the 25-row join of frozen specific-language labels × E2.17 split × OCR-v1 decisions, used for all confusion-matrix computations in this report.
- `backend/tests/unit/test_ebay_e2_17b_authoritative_japanese_ocr_validation.py` — 28 passing pytest tests.
- `backend/artifacts/index_fair_value/EBAY_E2_17B_AUTHORITATIVE_JAPANESE_OCR_VALIDATION.md` — this report.

No files in `backend/artifacts/index_fair_value/` predating this task were modified. No production code, Fair Value, Explorer, Capture-Allocation, D3-v5, IMAGE-v2, LANGUAGE-v1, or COMBINED-v3 modules were touched. No git add/commit/push occurred.

EBAY_OCR_V1_NOT_READY_INSUFFICIENT_HELDOUT_JAPANESE_EVIDENCE
