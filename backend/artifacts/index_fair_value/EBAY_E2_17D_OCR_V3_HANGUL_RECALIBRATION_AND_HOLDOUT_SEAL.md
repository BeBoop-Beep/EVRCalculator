# EBAY E2.17D — OCR-v3 Hangul-Suppression Recalibration + Small Japanese Holdout Seal

Status: **OCR-v3 frozen using ONLY development evidence (E2.16, E2.16B,
E2.17A). Predictions sealed against the 43-row E2.17C holdout BEFORE any
human labeling.** No certification (E2.14) or holdout truth was inspected
or used to tune anything. Nothing was committed, staged, or pushed.

---

## 1. OCR-v2 saturation reproduction (Phase A)

Recomputed directly from real artifacts, joining the frozen E2.17A
specific-language truth (`JAPANESE=16, CHINESE=5, KOREAN=4`, reconstructed
from `ebay_e2_17a_specific_language_review_history.jsonl` +
`ebay_e2_17_japanese_specific_language_review_queue.csv`) against
`ebay_e2_17c_ocr_v2_results.json` by `row_id`:

| Truth | n | OCR-v2 `korean_hangul_count` range | OCR-v2 decision |
|---|---|---|---|
| JAPANESE | 16 | 3–46 (all ≥2) | 16/16 `LANGUAGE_UNVERIFIED` (0/16 `LANGUAGE_MISMATCH`) |
| KOREAN | 4 | 70–141 | 4/4 `LANGUAGE_UNVERIFIED` (guard correctly fires, but destroys signal on Japanese too) |
| CHINESE | 5 | 10–52 | 5/5 `LANGUAGE_UNVERIFIED` |

Example: `e16b_e2_16b_dev_0012` (JAPANESE) — `japanese_kana_count=110`,
`high_conf_kana_count=37` (would independently qualify as
`LANGUAGE_MISMATCH`), but `korean_hangul_count=23` ≥ 2 → suppressed to
`LANGUAGE_UNVERIFIED`. Confirms: the `korean_hangul_count >= 2` guard,
calibrated when this field was structurally always 0 (OCR-v1), saturates
against a real Korean reader — 100% of NON_ENGLISH dev rows and 38% of
ENGLISH dev rows trip it, collapsing Japanese-mismatch recall from 7/16
(v1) to 0/16 (v2).

## 2. Hallucination root cause (Phase B)

New evidence gathered specifically for this task: re-ran the two-reader
architecture (`reader_ja=["ja","en"]`, `reader_ko=["ko","en"]`, unchanged)
against **349/350** real development images (`ebay_e2_16_language_development_queue.csv`
+ `ebay_e2_16b_japanese_language_development_queue.csv`; 1 image
403'd on refetch), this time capturing **per-region** Hangul confidence,
region counts, and contiguous-Hangul run length (script:
`backend/scripts/ebay_e2_17d_ocr_v3_hangul_recalibration.py`; results:
`backend/artifacts/index_fair_value/ebay_e2_17d_ocr_v3_development_results.json`).

Finding, directly from `raw_ko_regions_sample`:

- **English rows** (138/186 show any Hangul at all): spurious hits are
  low-confidence (0.03–0.32), mixed with Latin letters/digits/punctuation
  in the same recognized-text string (e.g. `"떠llus 예inalo"`, `"[때때 2537217"`,
  `"테280"`), and are isolated 1–2 character runs scattered across many
  different regions — never sustained multi-character Hangul in a single
  region.
- **Real Korean rows** (the 4 KOREAN-truth rows): genuine multi-word
  Hangul phrases at 0.66–0.71 confidence, 3–27 contiguous Hangul
  characters per region, appearing in 2–5 distinct regions per card (e.g.
  `"로켓단의 비밀기지"` at conf 0.66, `"자신의…포켓몬을…"` runs of 23–27 chars).
- Conclusion: the ko-reader does not fail cleanly on Japanese kana/kanji —
  it forces glyphs it has no model for into low-confidence, short,
  scattered Hangul-lookalike guesses. Genuine Hangul is categorically
  different: high-confidence, multi-character, multi-region. Isolated
  investigation of confidence, bounding-box/region count, and run length
  (not just raw character count) is what separates the two populations —
  exactly the richer per-region evidence the raw-count-only field could
  never distinguish.

## 3. Candidate conflict rules tested (Phase C/E) — including failures

All tested on the real 349-row + 25-row development corpus
(`backend/artifacts/index_fair_value/ebay_e2_17d_ocr_v3_development_results.json`).
Japanese recall is out of the 16 frozen JAPANESE E2.17A rows; false
mismatch is out of 186 ENGLISH / 4 KOREAN / 5 CHINESE.

| Candidate | Rule | JP recall | false ENGLISH | false KOREAN | false CHINESE |
|---|---|---|---|---|---|
| A (OCR-v2 baseline) | `korean_hangul_count >= 2` | 0/16 | 0/186 | 0/4 | 0/5 |
| B (naive "raise the threshold") | `korean_hangul_count >= 5` | 0/16 | 0/186 | 0/4 | 0/5 |
| B | `>= 10` | 1/16 | 0/186 | 0/4 | 0/5 |
| B | `>= 20` | 3/16 | 0/186 | 0/4 | 0/5 |
| B | `>= 30` | 8/16 | 0/186 | 0/4 | 0/5 |
| B | `>= 50` | 12/16 | 0/186 | 0/4 | 0/5 |
| C | `ko_distinct_high_conf_hangul_regions >= 1` | 10/16 | 0/186 | 0/4 | 0/5 |
| C | `>= 2` | 12/16 | 0/186 | 0/4 | 0/5 |
| C | `>= 3` | 12/16 | 0/186 | 0/4 | 0/5 |
| D | `ko_max_hangul_run_length >= 2` | 1/16 | 0/186 | 0/4 | 0/5 |
| D | `>= 3` | 6/16 | 0/186 | 0/4 | 0/5 |
| D | `>= 4` | 10/16 | 0/186 | 0/4 | 0/5 |
| F | `ko_high_conf_hangul_count >= 3/5/8` | 12/16 (all three) | 0/186 | 0/4 | 0/5 |
| **E (SELECTED)** | `ko_distinct_high_conf_hangul_regions >= 2 AND ko_max_hangul_run_length >= 2` | **12/16** | **0/186** | **0/4** | **0/5** |

Naive raw-count threshold-raising (Candidate B) was explicitly tested and
rejected per the task's own warning: it "works" only at `>=50`, an
uninterpretable magic number with no structural justification, and is
strictly dominated by C/E. Candidates C and E achieve identical numeric
results on this development corpus; **E was selected over C** because
requiring both a minimum count of independent high-confidence regions
*and* a minimum contiguous-run length is more conservative against a
plausible future failure mode C alone would not catch — several
one-character high-confidence noise hits landing in different regions
(which C alone would treat as "strong"). No row-specific, card-specific,
or Pokemon-name rules were used at any point.

## 4. Selected OCR-v3 rule

```
strong_kana   = (high_conf_kana_count >= 4 AND distinct_regions_with_kana >= 2)
                OR (high_conf_kana_count >= 6)              # UNCHANGED from v1/v2
strong_hangul = ko_distinct_high_conf_hangul_regions >= 2    # NEW
                AND ko_max_hangul_run_length >= 2            # NEW
                (region confidence threshold: 0.5)

strong_kana AND strong_hangul       -> UNVERIFIED  (conflict_strong_kana_and_strong_hangul)
strong_kana AND NOT strong_hangul   -> JAPANESE_MISMATCH
strong_hangul AND NOT strong_kana   -> NOT_JAPANESE_EVIDENCE
neither (+ latin-dominant fallback) -> NOT_JAPANESE_EVIDENCE or UNVERIFIED
```

Implementation: `backend/scripts/ebay_e2_17d_ocr_v3_hangul_recalibration.py`,
functions `_strong_kana`, `_strong_hangul`, `ocr_v3_decision`. Reader
architecture (`reader_ja=["ja","en"]`, `reader_ko=["ko","en"]`, disjoint
union merge) is byte-for-byte the same as OCR-v2. Only the Hangul
suppression rule changed, using richer per-region KO evidence that OCR-v2
computed internally but never wrote to its results file.

## 5. Japanese development results (Phase F)

16 human JAPANESE rows (E2.17A):

| | count |
|---|---|
| `JAPANESE_MISMATCH` (correct) | 12 |
| `UNVERIFIED` (missed, safely) | 4 |
| `NOT_JAPANESE_EVIDENCE` | 0 |
| **Recall** | **12/16 = 75%** |

All 4 misses fall through to `UNVERIFIED`, never to `NOT_JAPANESE_EVIDENCE`
— per the task's core principle, a missed Japanese card is never treated
as proof of non-Japanese identity. (Row-level: `e16_e2_16_dev_0068`,
`e16b_e2_16b_dev_0007`, `e16b_e2_16b_dev_0025`, `e16b_e2_16b_dev_0029` —
all have `ko_distinct_high_conf_hangul_regions=0`, i.e. no real conflicting
Hangul; they simply have below-threshold high-confidence kana evidence.)

## 6. Korean hard-negative results

4 human KOREAN rows: **0/4 false `JAPANESE_MISMATCH`**. 3/4 correctly
`NOT_JAPANESE_EVIDENCE` (strong Hangul detected, no meaningful kana); 1/4
`UNVERIFIED` (weaker Hangul signal on that particular image, still safe).

## 7. Chinese hard-negative results

5 human CHINESE rows: **0/5 false `JAPANESE_MISMATCH`**. All 5 land in
`UNVERIFIED` (shared-CJK kanji/hanzi evidence alone never counts as
`strong_kana`, unchanged from v1/v2; none had strong Hangul either).

## 8. English safety

186 human ENGLISH rows (E2.16 + E2.16B): **0/186 false `JAPANESE_MISMATCH`**.
138/186 show *some* spurious Hangul (`korean_hangul_count > 0`), confirming
the hallucination is real and common, but only 6/186 cross the
`strong_hangul` bar (correctly landing in `NOT_JAPANESE_EVIDENCE`, a
diagnostic label, not a Japanese veto) and 180/186 are `UNVERIFIED`.

## 9. UNVERIFIED behavior

- JAPANESE misses → 4/4 `UNVERIFIED` (never `NOT_JAPANESE_EVIDENCE`).
- Genuine conflict (strong kana + strong Hangul simultaneously): 0
  observed in this development corpus (no row triggered both), but the
  rule path exists and is unit-tested (`test_strong_kana_and_strong_hangul_conflict_is_unverified`).
- Broader NON_ENGLISH bucket (135 rows without specific-language labels,
  mostly Japanese by listing context): 41/135 (30.4%) `UNVERIFIED`, 77/135
  `JAPANESE_MISMATCH`, 17/135 `NOT_JAPANESE_EVIDENCE` — diagnostic only,
  not truth-checked since these rows lack specific-language ground truth.

## 10. CPU performance

Mean 6.25 s/row (both readers, CPU-only, `gpu=False`), reader load times
~1.1s (ja) + ~1.0s (ko). 349-row development run completed in ~36 minutes
wall-clock; the 43-row holdout run completed in a few minutes. Practical
for development-scale batch use; unchanged from OCR-v2's measured ~6.1s/row.

## 11. OCR-v3 freeze fingerprint

Recorded in `backend/artifacts/index_fair_value/ebay_e2_17d_ocr_v3_freeze_manifest.json`:

- `source_fingerprint_sha256` (sha256 of `ebay_e2_17d_ocr_v3_hangul_recalibration.py`
  at freeze time, 64 hex chars, verified programmatically):
  `9194795896f57a78f1fcc4ee2bb6d421b084fd318e7afb9c7cfb98db1cbac668`
- `easyocr_version`: `1.7.2`
- `reader_ja_config` / `reader_ko_config`: `["ja","en"]` / `["ko","en"]`
- `merge_logic_version`: `ocr_v3_merge_v1_union_disjoint_readers_rich_ko_evidence`
- `development_fingerprint_sha256` (sha256 over sorted `row_id:decision`
  across all 349 development rows, 64 hex chars):
  `f5d3af67220af8eb569254c3b4f3f3d0306752bbfee5c00ed7b7925826b89547`
- `freeze_fingerprint_sha256` (sha256 over
  `source_fingerprint | easyocr_version | reader configs | merge_logic_version | thresholds | development_fingerprint`,
  64 hex chars): `79bed607ff3a34bf701030d5f2947048f176427010fbc34273c91588a0059756`
- `production_authority: false`; `e2_14_or_holdout_truth_used: false`.

## 12. Holdout integrity

Reconfirmed against `ebay_e2_17c_small_japanese_holdout_queue.csv` and
`..._manifest.json`:

- 43 rows, 43 unique `row_id`, 43 unique `canonical_card_id`.
- `strata_counts`: `JAPANESE_CANDIDATE=25`, `NOT_JAPANESE_KOREAN_QUERY=6`,
  `NOT_JAPANESE_CHINESE_QUERY=6`, `NOT_JAPANESE_ENGLISH_CONTROL=6` (sum
  18 not-Japanese hard-negative + 25 Japanese-candidate = 43). Sampling
  stratum is explicitly NOT human truth.
- `reviewed_count: 0` in the manifest; every `human_truth_label` cell in
  the queue CSV is blank (verified programmatically).
- Holdout membership was not altered in any way by this task.

## 13. Sealed prediction fingerprint

`backend/artifacts/index_fair_value/ebay_e2_17d_ocr_v3_holdout_predictions.json`:

- 43 rows, one per holdout `row_id`, containing ONLY: OCR-v3
  decision + reason code, kana metrics, Hangul metrics (raw count,
  high-conf count, distinct high-conf regions, max run length, region
  confidences), OCR confidence/region metrics. **No `human_truth_label`,
  no `specific_language_truth`, no sampling stratum** — verified
  programmatically before writing (`assert all(... is None ...)`).
- `prediction_fingerprint` / `prediction_fingerprint_sha256`:
  `f0d1032df2a64eec10771eb5f153b889212904a3e2a0c347b8ce768a7c943757`
  (sha256 over sorted `row_id:ocr_v3_decision` across all 43 rows).
- `ocr_v3_freeze_fingerprint` embedded from the freeze manifest (Section 11).
- `created_at`: recorded ISO-8601 UTC timestamp at sealing time.
- Distribution: `UNVERIFIED=34`, `NOT_JAPANESE_EVIDENCE=5`,
  `JAPANESE_MISMATCH=4`. Not evaluated against truth — no truth exists to
  evaluate against, and none was inspected or inferred at any point.

## 14. Reviewer-blinding proof

- `backend/scripts/ebay_e2_17c_holdout_review_server.py` was NOT modified.
- `REVIEWER_VISIBLE_COLUMNS = frozenset({"row_id", "canonical_card_id", "image_url"})`
  — hardcoded, unchanged; `page()` only ever interpolates
  `{k: row[k] for k in REVIEWER_VISIBLE_COLUMNS if k in row}`.
- Grepped the server source for any reference to
  `ebay_e2_17d_ocr_v3_holdout_predictions.json` or any OCR-v3 field name
  (`ocr_v3`, `japanese_kana_count`, `korean_hangul_count`,
  `high_conf_kana_count`, `ko_distinct_high_conf_hangul_regions`,
  `mean_region_conf`, `development_stratum`) — zero matches. There is no
  code path in the review server that reads, imports, or serves the
  sealed prediction file. This is asserted by
  `test_ocr_output_hidden_from_reviewer`.
- The sealed prediction JSON lives at a separate path the review server
  never opens.

## 15. Tests

`backend/tests/test_ebay_e2_17d_ocr_v3_hangul_recalibration.py`:
**23 passed, 0 failed, 0 skipped** (all 3 holdout-artifact tests that
previously skipped now pass since the sealed artifact exists):

```
23 passed in 2.08s
```

Covers: Hangul/kana classification, weak-hallucination non-suppression of
strong kana, strong-Hangul suppression, strong-kana+strong-Hangul conflict
→ UNVERIFIED, weak/weak → UNVERIFIED, English false-mismatch safety
(including spurious-Hangul English row), Korean false-Japanese safety,
Chinese false-Japanese safety, Japanese positive, Japanese miss →
UNVERIFIED (never NOT_JAPANESE_EVIDENCE), determinism, freeze-fingerprint
stability, sealed holdout-prediction artifact existence/fingerprint/
membership/blank-labels, reviewer-blinding, no-E2.14-tuning reference, no
production writes. Pre-existing E2.17C tests
(`test_ebay_e2_17c_ocr_v2_korean_reader_fix.py`,
`test_ebay_e2_17c_holdout_review.py`) still pass unmodified (31 passed).

## 16. Exact Donny review command

Unchanged from E2.17C (no code changes to the review server were made or
needed):

```
python backend/scripts/ebay_e2_17c_holdout_review_server.py --reviewer donny
```

Progress check: `python backend/scripts/ebay_e2_17c_holdout_review_server.py --reviewer donny --summary`
Freeze after all 43 are labeled: `python backend/scripts/ebay_e2_17c_holdout_review_server.py --reviewer donny --freeze`

## 17. Next step

After Donny completes blind JAPANESE / NOT_JAPANESE / UNCERTAIN review of
all 43 holdout rows and freezes labels via the command above, task
**E2.17E** should join the frozen human labels against the sealed
`ebay_e2_17d_ocr_v3_holdout_predictions.json` (by `row_id`) to compute
OCR-v3's true holdout precision/recall — the first fully out-of-sample
evaluation of this detector. This report does not perform that evaluation
and no holdout truth was inspected to produce it.

---

EBAY_OCR_V3_FROZEN_SMALL_JAPANESE_HOLDOUT_READY_FOR_HUMAN_LABELING
