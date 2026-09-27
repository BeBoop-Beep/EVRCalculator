# EBAY E2.17C — OCR-v2 Korean-Reader Fix + Small Independent Japanese Holdout Prep

Status: **verification pass over a prior, interrupted attempt.** All listed
implementation files already existed on disk. This pass re-ran the tests,
recomputed the Phase B development regression directly from the frozen
artifacts (not from the prior agent's narrative), and found a real,
mechanically-verified defect that fails the Phase C freeze gate. The verdict
below is downgraded honestly rather than papering over it.

## 1. Korean-reader defect fix (Phase A)

`backend/scripts/ebay_e2_17c_ocr_v2_korean_reader_fix.py` (pre-existing,
verified correct in its scope). Confirmed EasyOCR 1.7.2 behavior empirically
documented in the module docstring: `easyocr.Reader(["ja","ko","en"])` raises
`ValueError: Japanese is only compatible with English, try
lang_list=["ja","en"]`. OCR-v2 therefore runs **two** separate Reader
instances against the same image:

- `reader_ja = easyocr.Reader(["ja","en"], gpu=False)` — unchanged from v1;
  still the sole source of `japanese_kana_count`, `high_conf_kana_count`,
  `distinct_regions_with_kana`, `cjk_shared_count`, `latin_char_count`.
- `reader_ko = easyocr.Reader(["ko","en"], gpu=False)` — new; sole source of
  `korean_hangul_count`.

This is the smallest deterministic two-reader architecture the spec called
for. `ocr_v2_decision()` is byte-for-byte the same rule as OCR-v1's
`ocr_v1_decision()` (Japanese kana threshold, confidence threshold, Han/Kanji
handling, `korean_hangul_count >= 2` suppression guard all unchanged) —
confirmed by direct source diff-reading. Nothing outside the reader
architecture was retuned. This part of the strict change boundary is
satisfied.

## 2. EasyOCR reader architecture

| Reader | Langs | Role |
|---|---|---|
| `reader_ja` | `["ja","en"]` | kana/kanji/latin evidence (unchanged from v1) |
| `reader_ko` | `["ko","en"]` | Hangul evidence (new) |

Merge logic: deterministic **disjoint union** — each signal comes from
exactly one reader, no cross-reader text merging. Documented as
`merge_logic_version = "ocr_v2_merge_v1_union_disjoint_readers"`.

## 3. OCR-v1 vs OCR-v2 development regression — recomputed directly from artifacts

Recomputed from `ebay_e2_17_ocr_results.json` (v1, 139 rows) and
`ebay_e2_17c_ocr_v2_results.json` (v2, 150 rows), joined on `row_id`, plus the
frozen E2.17A specific-language truth (`JAPANESE=16, CHINESE=5, KOREAN=4`,
reconstructed from `ebay_e2_17a_specific_language_review_history.jsonl` +
`ebay_e2_17_japanese_specific_language_review_queue.csv`, matching the
frozen manifest's `specific_language_label_counts` exactly).

**On the 139 rows common to both runs (ENGLISH/NON_ENGLISH/UNCERTAIN,
E2.16+E2.16B):**

| | v1 | v2 |
|---|---|---|
| ENGLISH → LANGUAGE_MATCH | 1 | 1 |
| ENGLISH → LANGUAGE_MISMATCH (false positive) | 0 | 0 |
| NON_ENGLISH → LANGUAGE_MISMATCH | 36 | **0** |
| NON_ENGLISH → LANGUAGE_UNVERIFIED | 34 | **70** |

**On the 16 human-labeled JAPANESE rows from E2.17A that v1 also scored
(14 of 16 overlap v1's smaller run):**

- v1: 7/14 correctly `LANGUAGE_MISMATCH`, 2/14 `LANGUAGE_UNVERIFIED`.
- v2 (all 16, since v2's larger manifest covers all of them): **0/16**
  `LANGUAGE_MISMATCH` — every single JAPANESE-labeled row now decides
  `LANGUAGE_UNVERIFIED`.

Root cause, confirmed by direct inspection of matched rows (e.g.
`e16b_e2_16b_dev_0012`: kana=110, high_conf_kana=37, distinct_regions=20 —
identical between v1 and v2, i.e. the JA reader's output did not change):
`korean_hangul_count` on this row is **23**, so the unchanged
`korean_hangul_count >= 2` suppression guard now fires and downgrades what
would be a correct `LANGUAGE_MISMATCH` to `LANGUAGE_UNVERIFIED`. This is not
an isolated case:

- **100% (81/81)** of NON_ENGLISH-labeled rows have `korean_hangul_count >= 2`.
- **38% (25/65)** of ENGLISH-labeled rows also have `korean_hangul_count >= 2`.
- Mean `korean_hangul_count` on NON_ENGLISH rows is ~44; on ENGLISH rows ~1.5.

The dedicated `["ko","en"]` reader, when fed an image containing dense
Japanese kana/kanji, does not fail cleanly — it forces its output into the
Korean-only character vocabulary and hallucinates large volumes of Hangul
from Japanese glyphs it has no model for. Because the reused Hangul-guard
threshold (`>= 2`) was calibrated against a field that was structurally
always 0 in OCR-v1 (i.e., never actually calibrated at all), it now
saturates on essentially every genuinely non-English row and blanket-
suppresses the Japanese-mismatch signal.

## 4. Hangul evidence verification

Hangul evidence is **genuinely present and non-zero** — Phase B's minimum
bar ("must actually produce nonzero Hangul evidence on at least some known
Korean rows") is met and then some: all 4 KOREAN-labeled E2.17A rows show
large Hangul counts (70, 141, 116, 87) with `ko_ocr_ok=True`. So this is not
the "Hangul remains structurally absent → STOP" failure mode the spec
anticipated. It is the mirror-image failure: Hangul evidence is real but so
over-sensitive (false-triggers on Japanese text) that it destroys the
Japanese-detection signal it was only supposed to guard.

## 5. OCR-v2 freeze decision — FAILS Phase C, gate 4

Gate-by-gate, using the recomputed numbers above:

1. Korean evidence genuinely available — **PASS**.
2. Zero new false-Japanese mismatches on English development rows — **PASS**
   (trivially: v2 produces zero `LANGUAGE_MISMATCH` decisions at all on the
   139-row common set, so no new false positives on English rows either).
3. Zero new false-Japanese mismatches on Chinese/Korean hard negatives —
   **PASS** (same reason: v2 never emits `LANGUAGE_MISMATCH` on this corpus).
4. Japanese behavior materially consistent with the prior conservative
   candidate — **FAIL**. True-positive Japanese mismatch detection collapsed
   from 36/139 (v1) to 0/139 (v2), and from 7/16 to 0/16 on the frozen
   E2.17A JAPANESE-labeled ground truth. This is not "materially
   consistent" by any reading of the term — it is a total loss of the
   detector's positive signal, caused by the unchanged Hangul-suppression
   guard saturating against noisy real Hangul evidence it was never
   calibrated against.
5. Weak evidence continues to UNVERIFIED — **PASS** (mechanically true, but
   only because virtually everything now falls into UNVERIFIED).
6. CPU runtime remains practical — **PASS**: mean ~6.1s/row across both
   readers on 150 rows (`ja_load_seconds`/`ko_load_seconds` logged in the
   results artifact); acceptable for development-scale runs.
7. No certification evidence (E2.14) used to tune — **PASS**: only E2.16,
   E2.16B, E2.17A development corpora were used.

Gate 4 is a hard freeze gate per the spec ("freeze OCR-v2 only if: ...4...").
It fails. Per the spec's own instruction ("If not safe:
`EBAY_OCR_V2_NOT_READY_<REASON>`"), OCR-v2 as currently implemented is
**not frozen**. Consistent with this, the pre-existing holdout manifest
already recorded `"ocr_v2_freeze_fingerprint": "PENDING_OCR_V2_FREEZE_FINGERPRINT"`
— i.e. the freeze was never actually finalized by the prior attempt either,
even though downstream holdout-capture work (Phase D) proceeded ahead of
that gate. No fix was attempted here: retuning the `korean_hangul_count >= 2`
guard is explicitly forbidden by the task's strict change boundary unless
"mechanically required by the merge," and a threshold retune is a policy
change, not a mechanical necessity of running two readers — so it is
correctly left to a follow-up task (E2.17D) rather than smuggled in here.

## 6. OCR-v2 fingerprint (recorded, not a freeze certification)

- `ocr_v2_source_version`: `ebay_e2_17c_ocr_v2_korean_reader_fix_v1`
- `ocr_v2_source_fingerprint_sha256`: `59984ccef60e15f1de27dc17ce86e91f7cdbf3f9a82161d2984bad2fc9caa280`
- `easyocr_version`: `1.7.2`
- `reader_ja_config`: `["ja","en"]`
- `reader_ko_config`: `["ko","en"]`
- `merge_logic_version`: `ocr_v2_merge_v1_union_disjoint_readers`
- `production_authority`: `false`
- Development corpus fingerprints consumed: E2.16 (`ebay_e2_16_language_development_queue.csv`, 200 rows), E2.16B (`ebay_e2_16b_japanese_language_development_queue.csv`, 150 rows), E2.17A frozen specific-language truth (`specific_language_label_fingerprint = 3dc900663abc939c64564383fe79234aea01b7abd7d252e5f1c3ce562ba0dda9`, 25 rows: JAPANESE=16, CHINESE=5, KOREAN=4).

This fingerprint identifies the *candidate* that was evaluated, not a frozen
production-eligible OCR-v2. The holdout manifest's
`ocr_v2_freeze_fingerprint` field correctly remains `PENDING_OCR_V2_FREEZE_FINGERPRINT`
and has been left as-is (not backfilled) since OCR-v2 did not pass freeze.

## 7–14. Holdout (Phase D) — capture verified sound; sequenced ahead of freeze

Even though OCR-v2 did not freeze, the small independent holdout capture
work itself was checked and is legitimate, well-formed development-holdout
infrastructure that can be reused once E2.17D resolves the freeze gate — no
rework needed there. Verified directly against
`ebay_e2_17c_small_japanese_holdout_manifest.json`,
`ebay_e2_17c_small_japanese_holdout_queue.csv`, and the review server:

- **Holdout size**: 43 rows (within the 35–45 tolerance).
- **Japanese-candidate stratum**: 25 rows.
- **Not-Japanese hard-negative stratum**: 18 rows, split
  `NOT_JAPANESE_KOREAN_QUERY=6`, `NOT_JAPANESE_CHINESE_QUERY=6`,
  `NOT_JAPANESE_ENGLISH_CONTROL=6`.
- **Canonical-card identity novelty**: 43/43 unique canonical_card_ids;
  27 novel vs. prior OCR development cohorts, 16 reused (canonical-card
  reuse is permitted by spec as long as no prior *listing* is reused —
  confirmed separately below).
- **Historical exclusions**: 12,281 prior listing IDs excluded across all
  prior cohorts (D2/D3/V4/V5/E2.9B/E2.13/E2.14/E2.15/E2.16/E2.16A/E2.16B/
  E2.17/E2.17A/E2.17B — full per-file counts recorded in the manifest's
  `historical_exclusion.counts_per_file`); 0 search/getitem provider errors.
- **Reviewer blinding**: directly verified the CSV header —
  `row_id,canonical_card_id,image_url,human_truth_label,human_note,reviewer_id,label_timestamp`
  — contains none of the forbidden fields (no provider Language aspect, no
  sampling stratum, no OCR-v2 output/kana/Hangul/Han counts, no confidence,
  no expected answer, no seller query language, no listing title). The
  server additionally enforces this at runtime via `assert_reviewer_blind()`
  against `FORBIDDEN_REVIEWER_COLUMNS` on every start and freeze, and the
  HTML renderer only interpolates from `REVIEWER_VISIBLE_COLUMNS`.
- **Review contract**: exactly three buttons —
  `JAPANESE` / `NOT_JAPANESE` / `UNCERTAIN` — confirmed in
  `LABEL_CHOICES = ("JAPANESE", "NOT_JAPANESE", "UNCERTAIN")` and the HTML/JS
  button wiring; no button or prompt asks the reviewer to name the specific
  non-Japanese language.
- **Review session**: `review_session_id: null`, **`reviewed_count: 0`**
  (directly verified: all 43 rows have blank `human_truth_label`,
  `human_note`, `reviewer_id`, `label_timestamp` in the queue CSV — no
  premature or accidental labeling occurred).
- **OCR-v2 predictions for the holdout**: **not precomputed/sealed**
  (`ocr_v2_predictions_precomputed: false` in the manifest). This was
  optional per spec ("encouraged but not strictly mandatory"), and given
  that OCR-v2 itself failed to freeze in this pass, precomputing/sealing its
  predictions now would be premature — this is correctly left as residual
  work for E2.17D, alongside the freeze-gate fix.

## 15. Tests

Ran both existing test files directly:

```
python -m pytest backend/tests/test_ebay_e2_17c_ocr_v2_korean_reader_fix.py backend/tests/test_ebay_e2_17c_holdout_review.py -q
31 passed in 3.24s
```

Coverage confirmed present and passing: Korean OCR evidence availability,
Hangul-suppression-guard exercised (unit-level, on synthetic evidence),
Japanese kana still detected (unit-level rule test), English false-mismatch
non-regression (unit-level), Chinese/Korean hard-negative guard behavior,
OCR-v2 determinism, OCR-v2 fingerprint stability, EasyOCR reader
compatibility assertions (`["ja","ko","en"]` rejected /
`["ko","en"]` accepted), holdout historical-listing exclusion, no
OCR-v2-output-based sampling, reviewer sees only the 3-button contract,
provider-language/OCR-evidence hiding, review starts at 0 rows, row/image
binding, no production writes. These unit tests correctly verify the
*decision-rule logic* in isolation; they do not (and structurally cannot,
being unit tests on synthetic fixtures) catch the corpus-scale
false-Hangul-saturation regression documented in §3 — that required running
the actual frozen OCR-v2 development-corpus artifact against the actual
frozen E2.17A ground truth, which is what this verification pass did.

No new test gaps were found that needed filling; the existing 31 tests are a
legitimate and passing baseline for the code as fixed today.

## 16. Exact review command (for reference; DO NOT RUN as part of this task)

```
python backend/scripts/ebay_e2_17c_holdout_review_server.py --reviewer donny --port 8919
```

Summary/freeze utility flags: `--summary` (print progress, no side effects),
`--freeze` (materialize final labels into the queue CSV once reviewed).
Neither was invoked during this task — reviewed_count remains 0.

## Bottom line

The Korean-reader architecture fix (Phase A) is real and correctly scoped.
Korean/Hangul evidence is genuinely non-zero (Phase B minimum bar met). But
the unchanged Hangul-suppression guard, now facing real (rather than
structurally-zero) Hangul evidence, saturates almost universally on
non-English rows and erases Japanese-mismatch detection entirely
(36→0 on the 139-row common set; 7/16→0/16 on frozen JAPANESE ground truth).
That is a hard failure of Phase C freeze gate 4. OCR-v2 is not frozen. The
holdout capture and review infrastructure (Phase D) were verified sound and
can be reused once E2.17D fixes the guard-saturation defect and re-runs this
freeze evaluation — no holdout rework needed.

EBAY_OCR_V2_NOT_READY_KOREAN_READER_HANGUL_GUARD_SATURATES_AND_ERASES_JAPANESE_DETECTION
