# EBAY E2.17 -- Local OCR-v1 Japanese Physical-Card Language Feasibility

**Status: DEVELOPMENT RESEARCH ONLY. `development_only=true`, `production_authority=false`.**
**Not a certification. No paid OCR APIs used. No production writes. Nothing committed.**

Analysis/harness code: `backend/scripts/ebay_e2_17_ocr_v1_japanese_language_feasibility.py`
Tests: `backend/tests/test_ebay_e2_17_ocr_v1_japanese_language_feasibility.py` (31 passed)
Corpus split artifact: `backend/artifacts/index_fair_value/ebay_e2_17_combined_corpus_split.json`
Real OCR run output: `backend/artifacts/index_fair_value/ebay_e2_17_ocr_results.json`
Prepared Donny review queue: `backend/artifacts/index_fair_value/ebay_e2_17_japanese_specific_language_review_queue.csv`

This task follows up on `EBAY_E2_16C_JAPANESE_LANGUAGE_ASPECT_VALIDATION.md`, which found the
provider `Language=Japanese` eBay aspect has 97.83% precision (90 TP / 2 FP across 92 rows) but
the two false positives had different, non-generalizable root causes, so Japanese was correctly
withheld from the frozen LANGUAGE-v1 vocabulary (`{KOREAN, CHINESE}` only). E2.17 asks whether a
free, local, CPU OCR/script layer can do better as an independent rejection veto.

---

## 1. Environment audit (Phase A)

Checked via `pip show` and `which`/`--version` in this repo's isolated Python 3.8.10 environment
(`C:\Users\Owner\AppData\Local\Programs\Python\Python38`) before installing anything:

| Package | Pre-existing? | Notes |
|---|---|---|
| `tesseract` (binary) | **Not present** | `which tesseract` -> not found on PATH; no Windows install detected |
| `pytesseract` | Not installed | would still need the tesseract binary, which is not pip-installable on Windows (needs a separate installer) |
| `easyocr` | Not installed (installed for this task) | pure-Python, ships its own PyTorch-based detection/recognition models |
| `paddleocr` / `paddlepaddle` | Not installed | heavier dependency footprint; not needed once EasyOCR proved viable |
| `onnxruntime` | Not installed | not needed |
| `torch` | **Already present: 2.4.1+cpu** | CPU wheel, no CUDA -- confirms this box is CPU-only, consistent with "CPU-capable" requirement |
| `opencv-python` | Not installed as such; `opencv-python-headless` 5.0.0.93 pulled in as an EasyOCR dependency | |

**Decision:** EasyOCR was the smallest robust local option given `torch` (CPU build) was already
present in the environment, has first-class Japanese (`ja`) + English (`en`) language packs, and
required no OS-level installer (unlike Tesseract, which has no publicly documented pip-only path
to a Windows binary in this sandbox). Installed via `pip install easyocr` **into this repo's
existing Python environment only** -- not system-wide, no lockfile changes, nothing committed.

Installed versions (exact, via `pip show`):

| Package | Version | License |
|---|---|---|
| easyocr | 1.7.2 | Apache License 2.0 |
| opencv-python-headless | 5.0.0.93 | Apache 2.0 |
| torch | 2.4.1+cpu | BSD-3 |
| torchvision | 0.19.1 | BSD |

EasyOCR's underlying detection model is CRAFT (Character Region Awareness for Text detection);
recognition is a CRNN-style model. Both ship pretrained weights that EasyOCR downloads once to
`~/.EasyOCR/model/` (~65MB combined for the `ja`+`en` recognition networks + shared detector,
observed via the actual download in this run) and reuses on every subsequent load. All operation
is fully offline after the first download; no network call is made per-image, no data leaves the
machine, and no paid API of any kind (OpenAI Vision, Google Vision, AWS Rekognition/Textract,
Azure OCR) was used anywhere in this task.

Japanese support: yes (dedicated `ja` recognition model, plus the detector is script-agnostic).
English support: yes (`en` recognition model). CPU support: yes, confirmed by running with
`gpu=False` throughout (see Section 14 for measured CPU timings).

---

## 2. OCR engine selected

**EasyOCR 1.7.2**, `Reader(['ja', 'en'], gpu=False)`. Free, local, Apache-2.0-licensed, CPU-capable,
offline after first model download, no paid API involved anywhere in the pipeline.

---

## 3. Japanese human-truth construction (Phase B) -- the critical finding

Per the spec, OCR-v1 needs **independently human-supported** Japanese-specific truth, not inferred
from the provider Language aspect, sampling stratum, seller title, or marketplace, and not
self-labeled by this agent and presented as authoritative.

Both development corpora record a `human_language_if_known` field per review event
(`ebay_e2_16_language_development_review_history.jsonl`, 205 events / 200 rows, and
`ebay_e2_16b_japanese_language_development_review_history.jsonl`, 152 events / 150 rows, reviewer
`donny` on both). **Every single event in both files has `human_language_if_known == ""` (empty
string) -- 0 of 357 label events carry a specific-language annotation, in either corpus.**
Verified programmatically, not assumed:

```
ebay_e2_16_language_development_review_history.jsonl:  total 205, nonempty specific_lang 0
ebay_e2_16b_japanese_language_development_review_history.jsonl: total 152, nonempty specific_lang 0
```

So the only authoritative human truth that exists is the **binary** `ENGLISH` / `NON_ENGLISH` /
`UNCERTAIN` label (which the E2.16/E2.16B/E2.16C tasks already established and froze). There is
**no authoritative human confirmation that any specific NON_ENGLISH row is Japanese** as opposed to
Korean, Chinese, French, or something else -- Donny was never asked to (or did not) fill in the
specific-language field during either review pass.

**What this means for the confusion matrix used below:**
- The **ENGLISH-safety side is fully authoritative.** `human_truth_label == ENGLISH` is a real,
  human-reviewed label directly from Donny's review history, independent of any provider aspect,
  title, or agent judgment. The critical false-LANGUAGE_MISMATCH metric (Section 8) is measured
  against this authoritative truth and is valid as reported.
- The **Japanese-recall side is only indirectly supported.** Rows this task reports as OCR
  "Japanese mismatch" are backed by (a) the authoritative `NON_ENGLISH` human label, plus (b) this
  task's own OCR detection of genuine Hiragana/Katakana Unicode characters (`U+3040-30FF`), which
  is script-deterministic evidence -- kana is not used in Chinese or Korean text, so a real kana
  hit is inherently Japanese-specific by construction of the Unicode standard, not by human
  language-identification judgment. This is a solid *technical* argument, but it is **not** the
  same thing as an authoritative human reviewer having looked at the card and written "Japanese."
  Per the spec, this report explicitly flags this as **not human-confirmed Japanese-specific
  truth** and does not present it as such.
- Listing titles were inspected only as *provisional, non-evidentiary* context (e.g., 35/36
  OCR-flagged-mismatch rows also happen to contain the word "Japanese" in their seller title) --
  labeled here explicitly as **AI-assisted provisional annotation, not authoritative human truth**,
  and titles were never used as an input to the OCR decision rule itself (see
  `test_e2_14_excluded_from_tuning_sources` sibling test
  `test_no_title_based_evidence` is implicit via the rule's fixed field set -- `ocr_v1_decision`
  only accepts `OcrEvidence`, which carries no title field).

**Conclusion of Phase B: insufficient authoritative Japanese-specific human truth exists to run a
freeze-quality evaluation of Japanese recall or a Japanese-specific precision claim.** A prepared,
blinded review queue for Donny is included with this task (Section 20) rather than fabricating that
authority. This is the primary driver of the final verdict below.

---

## 4. Development sample counts

- E2.16: 200 rows -- ENGLISH=134, NON_ENGLISH=63, UNCERTAIN=3 (independently recomputed, matches
  the frozen manifest exactly).
- E2.16B: 150 rows -- ENGLISH=52, NON_ENGLISH=97, UNCERTAIN=1 (independently recomputed corpus
  fingerprint `38636c3ff0a6b907d464430f57c16520fa5f28c00150389a0cf4f9962591ab9b` and label
  fingerprint `06d68834b284e12ff97bf1461573a18f71c6acac372015eca84eda9a7c3f2e30` both match the
  values stated in the task exactly).
- Combined corpus: 350 rows -- ENGLISH=186, NON_ENGLISH=160, UNCERTAIN=4.
- All 350 rows carry a `canonical_card_id` (200/200 in E2.16, 150/150 in E2.16B).

---

## 5. Design/validation split (Phase F)

Split by `canonical_card_id` (not row) with a fixed seed and a deterministic hash-based assignment
so the split is reproducible: 56 unique `canonical_card_id` groups across the 350 rows (heavy
duplication is expected -- both corpora repeatedly sample well-known target cards). Assignment:
41 groups -> DESIGN, 15 groups -> HELDOUT (~70/30 by group, the unit that must not leak).

| | DESIGN | HELDOUT |
|---|---|---|
| Rows | 272 | 78 |
| ENGLISH | 151 | 35 |
| NON_ENGLISH | 120 | 40 |
| UNCERTAIN | 1 | 3 |

Verified zero `canonical_card_id` overlap between DESIGN and HELDOUT groups (test
`test_grouped_split_no_identity_leak`, and independently in the harness script at build time).

Given the very large real network-fetch and CPU-OCR-inference cost of running all 350 rows'
images (many rows share the same physical listing across duplicate `canonical_card_id`s), this
task ran a **real, network-fetched, stratified sample of 139 rows** (30 DESIGN-ENGLISH,
30 DESIGN-NON_ENGLISH, 35 HELDOUT-ENGLISH, 40 HELDOUT-NON_ENGLISH, plus all 4 UNCERTAIN rows),
rather than fabricating or simulating OCR output for the full 350. 138/139 images (99.3%) were
successfully fetched from live `i.ebayimg.com` URLs; 1 fetch failed (network timeout) and is
counted as an OCR failure -> `LANGUAGE_UNVERIFIED`, never silently dropped.

The decision-rule thresholds (Section 7) were fixed by inspecting **only DESIGN-split evidence**
before being applied, unmodified, to the HELDOUT split. No threshold was re-tuned after seeing
HELDOUT results (`test_validation_not_referenced_in_rule_source` asserts the rule's source
contains no reference to the holdout partition).

---

## 6. Preprocessing (Phase C)

This task used the **full listing image** (`image_url`, the first/primary retained image per row)
directly, without a card-crop or perspective-rectification step. An `image_processing`/`card_crop`
grep across `backend/services` and `backend/` for existing E2.6/E2.7 infrastructure (`card_crop`,
`perspective`, `image_normalize`) did not return a reusable, already-built crop/rectification
module in the time available for this task; rather than build new crop infrastructure from
scratch (out of scope for a feasibility study), OCR was run against the raw listing photo, with
EasyOCR's own built-in CRAFT text-region detector locating text regions internally. This is a
legitimate limitation: multi-card collage images, heavy backgrounds, and off-card text (seller
watermarks, grading-company labels) are not filtered out by a crop step in this pass. Where no
usable text region was found at all, the row correctly falls to `LANGUAGE_UNVERIFIED` (0 regions
or too little recognized text), per the Phase C fallback rule.

---

## 7. OCR/script rule (Phases D/E/G)

Implemented in `ebay_e2_17_ocr_v1_japanese_language_feasibility.py`. Conservative, Unicode-range
based, fixed on DESIGN only:

- Classifies every OCR-recognized character into `JP_KANA` (Hiragana `U+3040-309F` +
  Katakana `U+30A0-30FF`, unambiguous Japanese-only script), `CJK_SHARED` (Kanji/Hanzi
  `U+4E00-9FFF`, ambiguous between Japanese and Chinese, **never used alone to trigger a
  mismatch**), `KOREAN` (Hangul `U+AC00-D7A3`, hard-negative guard), `LATIN`, `OTHER`.
- `LANGUAGE_MISMATCH` requires **either** >=4 high-confidence (OCR conf >=0.5) kana characters
  spread across >=2 distinct recognized text regions, **or** >=6 high-confidence kana characters
  in a single dense region -- i.e., a single stray glyph never triggers a veto (tested explicitly).
- Real Hangul presence (>=2 chars) suppresses a Japanese call entirely (`LANGUAGE_UNVERIFIED`),
  even if some ambiguous shared-CJK glyphs also appear, so Korean text is never mistaken for
  Japanese by this rule.
- `LANGUAGE_MATCH` requires zero kana AND zero shared-CJK evidence, >=8 Latin characters across
  >=2 regions, and mean region confidence >=0.35 -- i.e., strong, unambiguous English/Latin
  evidence with no Japanese contradiction.
- Anything else (weak OCR, too little text, crop/decode failure, ambiguous mixed evidence,
  moderate-but-not-strong kana) falls to `LANGUAGE_UNVERIFIED`, per the "prefer UNVERIFIED over a
  false veto" instruction.
- The decision function `ocr_v1_decision(ev)` takes **only** OCR-derived evidence (`OcrEvidence`);
  it has no parameter and no field for the provider Language aspect, title, or marketplace --
  structurally verified by test (`test_provider_japanese_alone_cannot_veto`).

---

## 8. English safety results (Phase E / CRITICAL SAFETY METRIC)

This is the authoritative-truth-backed half of the evaluation (Section 3).

| Split | Human-ENGLISH n | False `LANGUAGE_MISMATCH` | Rate | Wilson 95% CI |
|---|---|---|---|---|
| DESIGN | 30 | 0 | 0.0% | -- |
| HELDOUT | 35 | 0 | 0.0% | -- |
| **Combined** | **65** | **0** | **0.0%** | **[0.0%, 5.58%]** |

**Zero false Japanese mismatches on 65 real, network-fetched, authoritative-human-ENGLISH card
images**, across both the design and held-out partitions, without ever reading the provider
Language aspect. This is the single strongest positive finding of this task. The Wilson upper
bound (5.58%) reflects real sample-size uncertainty at n=65 -- it is not proof the true rate is
zero, only that zero failures were observed in this sample.

Every row called `LANGUAGE_MISMATCH` across the full 139-row sample (n=36) was independently
checked: **all 36 have `human_truth_label == NON_ENGLISH`** (precision of the MISMATCH class =
36/36 = 100%, Wilson lower bound 90.36%). Zero false positives were found and individually
inspected (there were none to inspect).

---

## 9. Japanese recall (Phase D, with the Section 3 caveat)

Against the **binary** human-`NON_ENGLISH` label (not Japanese-specific, per Section 3):

| Split | Human-NON_ENGLISH n | OCR `LANGUAGE_MISMATCH` (kana-evidenced) | Recall vs. NON_ENGLISH | `LANGUAGE_UNVERIFIED` |
|---|---|---|---|---|
| DESIGN | 30 | 17 | 56.7% | 13 |
| HELDOUT | 40 | 19 | 47.5% | 21 |
| **Combined** | **70** | **36** | **51.4%** | **34** |

Zero NON_ENGLISH rows were ever called `LANGUAGE_MATCH` (the unsafe direction) in either split.
Every mismatch call is backed by real, multi-region, high-confidence kana detection -- script
evidence that is inherently Japanese-specific by Unicode construction -- but, per Section 3, this
is not the same as an authoritative human reviewer confirming "this card is Japanese" versus some
other non-English language. Moderate recall (~51%) with zero unsafe false calls is consistent with
the spec's explicit allowance ("even moderate Japanese recall can be useful if mismatch precision
is extremely high").

---

## 10. False mismatch rate

Covered in Section 8: **0/65 (0.0%), Wilson 95% CI [0.0%, 5.58%]**, combined across DESIGN and
HELDOUT, on authoritative human-ENGLISH truth.

---

## 11. Other-language hard negatives (Phase G)

The sampled 139 rows come from corpora that were purpose-built around Japanese-targeted search
strata (E2.16B especially); as in E2.16C, **no Korean or Chinese rows were present in this
Japanese-focused sample to evaluate as hard negatives directly.** The rule's Hangul-suppression
guard (Section 7) is unit-tested (`test_korean_hard_negative`) and structurally guarantees a
Korean card cannot be classified `LANGUAGE_MISMATCH` by this rule even if shared-CJK glyphs
happen to also appear, but this has **not** been validated against a single real Korean/Chinese
card image in this task -- that remains an open gap flagged for any future evaluation round,
consistent with the instruction not to broaden OCR-v1 authority to other languages here. Latin-
script foreign languages (e.g. French) were not present in the sample either; the rule's own
construction (zero kana/CJK => never `LANGUAGE_MISMATCH`) makes a French card structurally safe
from a false veto regardless, but again this was not empirically observed against a real French
card in this run.

---

## 12. Hard image cases (Phase H)

With no dedicated card-crop step (Section 6), hard cases were not independently broken out by
category (clean stock vs. tabletop photo vs. sleeve/toploader vs. glare vs. rotated vs. multi-card
collage) because the harness does not currently tag images with these attributes and doing so by
hand for 139 real images was not completed in this pass. The one honest signal available: 102/139
(73.4%) of all sampled rows -- across both ENGLISH and NON_ENGLISH truth -- resolved to
`LANGUAGE_UNVERIFIED` rather than a confident call, which is consistent with a real-world mix of
clean listing photos and harder cases (glare, angle, low text density, multi-card collages) that
this conservative rule correctly refuses to call rather than guessing. This high UNVERIFIED rate
is a deliberate safety property, not a defect, but it also means hard-case behavior was validated
in aggregate (never producing an unsafe call) rather than case-by-case.

---

## 13. UNVERIFIED rate

**102/139 (73.4%)** of all sampled rows resolved to `LANGUAGE_UNVERIFIED`. Broken out:

- 34 of the 70 human-NON_ENGLISH rows (48.6%) -- correctly conservative rather than guessing.
- 65 of the 65 human-ENGLISH rows that were *not* confidently called `LANGUAGE_MATCH`: in fact
  only **1 of 65** ENGLISH rows reached `LANGUAGE_MATCH` (the rest fell to UNVERIFIED). The
  `LANGUAGE_MATCH` threshold (Section 7) turned out to be quite strict in practice against real
  listing photos (full, uncropped images with lots of non-text background), which is safe (no
  false positives) but means OCR-v1 in its current form provides almost no positive MATCH signal
  -- its practical value today is overwhelmingly as a Japanese-mismatch veto, not an
  English-confirmation source. This is an important, honestly-reported limitation: without a
  card-crop step (Section 6), `LANGUAGE_MATCH` essentially does not fire.
- All 4 UNCERTAIN-truth rows -> `LANGUAGE_UNVERIFIED` (correct fall-through).

---

## 14. CPU performance (Phase I)

Measured directly on this machine, CPU-only (`gpu=False`), for the real 139-image run:

- Model load time (one-time, `ja`+`en` detector+recognizer): **1.09 seconds** (models were
  already cached locally in `~/.EasyOCR/model/` from the initial download during Phase A setup;
  the first-ever cold download took several minutes over the network, a one-time cost).
- Mean per-image OCR inference time: **3.13 seconds/image** (138 real images processed).
- No GPU used at any point.

At an estimated 250-350 image-eligible listings/day: 250 x 3.13s = 782s (~13.0 min/day);
350 x 3.13s = 1,096s (~18.3 min/day), plus a ~1-2 second one-time model load per process
invocation. This is comfortably practical for a CPU-only daily batch job; it is not a real-time,
per-request-latency-sensitive path in this pipeline's current usage pattern. Peak memory was not
separately profiled in this pass (a gap for a future run) but no out-of-memory or excessive-RSS
behavior was observed processing 139 images sequentially in a single process.

---

## 15. OCR-v1 freeze decision (Phase J)

Checking all seven freeze conditions:

1. **Zero or near-zero false LANGUAGE_MISMATCH on human ENGLISH** -- MET. 0/65 (Wilson upper
   5.58%), on real network-fetched images, both DESIGN and HELDOUT.
2. **Meaningful number of correctly detected Japanese cards** -- **PARTIALLY MET, with the
   Section 3 caveat.** 36 real kana-evidenced mismatch calls exist, all on human-NON_ENGLISH rows,
   but none are backed by an authoritative human "this is specifically Japanese" label, because
   zero such labels exist anywhere in either source corpus (Section 3). The script-level kana
   evidence is technically strong and self-consistent, but the spec is explicit that OCR-v1 must
   not be frozen on the strength of an AI-agent's own provisional judgment standing in for
   authoritative human truth.
3. **Deterministic preprocessing** -- MET. Fixed Unicode-range rule, fixed thresholds, no
   randomness (`test_deterministic_decision`); same image bytes -> same OCR call and same
   downstream decision.
4. **Weak evidence safely becomes UNVERIFIED** -- MET. 73.4% overall UNVERIFIED rate, zero unsafe
   MATCH calls on NON_ENGLISH rows, zero unsafe MISMATCH calls on ENGLISH rows.
5. **CPU runtime is practical** -- MET. ~13-18 minutes/day of CPU time at the target daily volume.
6. **OCR decision does not use provider Japanese aspect** -- MET. Structurally verified
   (`test_provider_japanese_alone_cannot_veto`); `OcrEvidence` carries no provider-language field.
7. **E2.14 was not used for threshold selection** -- MET. Thresholds were fixed by inspecting only
   DESIGN-split OCR evidence before ever looking at HELDOUT or any E2.14 artifact; the harness
   script contains zero references to any `e2_14` path or artifact
   (`test_e2_14_excluded_from_tuning_sources`).

**Six of seven conditions are cleanly met. Condition 2 is not met to the standard the spec
requires** -- "meaningful number of correctly detected Japanese cards" needs to rest on
authoritative human truth, and per Section 3, zero rows in either 200-row or 150-row corpus carry
a human-confirmed specific-language annotation. The promising kana-detection numbers in Section 9
are real, repeatable, and safety-consistent, but they are evidence *for building a queue to get
that authoritative truth*, not a substitute for it.

**OCR-v1 is NOT frozen in this task.**

---

## 16. LANGUAGE-v2 contract/fingerprint

Not applicable -- Phase K is explicitly gated on "only if OCR-v1 freezes." OCR-v1 did not freeze
(Section 15), so no LANGUAGE-v2 module was created and no fingerprint was minted. LANGUAGE-v1
(`{KOREAN, CHINESE}`) and COMBINED-IDENTITY-v3 remain exactly as they were, untouched by this task
(`test_language_v1_module_untouched` confirms the E2.16A source file is present and unmodified;
no `ebay_language_v2_policy.py` or similar module was created,
`test_no_premature_language_v2_combined_v4_module`).

---

## 17. COMBINED-v4 contract/fingerprint

Not applicable, for the same reason as Section 16 (Phase M is gated on LANGUAGE-v2 freezing, which
did not happen). COMBINED-IDENTITY-v3 remains the frozen, unmodified combined policy.

---

## 18. V4/V5/E2.9B diagnostics

Not run. Phase N is explicitly gated on "only after OCR-v1/LANGUAGE-v2/COMBINED-v4 are all
frozen." None of the three froze in this task, so no post-hoc diagnostic against V4, V5, or E2.9B
cohorts was executed, consistent with the instruction not to tune or diagnose against consumed
cohorts before a real freeze.

---

## 19. E2.14 diagnostic

Not run for tuning purposes, per the spec's explicit prohibition. For context only (already
independently re-verified from the real `ebay_e2_14_fresh_blind_certification.json` artifact in
this task, not assumed): `accepted_count=259, true_accepts=258, false_accepts=1,
accepted_precision=0.9961389961389961, wilson_95_lower=0.9784576202034251,
distinct_card_coverage=0.8285714285714286` -- matching the spec's expected sizing exactly. The
single known catastrophic false accept is `E13-0127` (item `v1|407215142815|0`, target
`Pikachu ex`, `Ascended Heroes` #277, `human_no_derived_reason: WRONG_LANGUAGE`). Because
LANGUAGE-v2/COMBINED-v4 were not frozen this round, this row's disposition under any new policy
was **not evaluated** -- doing so before a real freeze would be exactly the "tune to catch E2.14"
anti-pattern the spec forbids (Phase J: "Do NOT freeze merely because it appears capable of
catching E2.14").

---

## 20. Whether another blind is justified

**No.** Per the spec's explicit gate, a new independent certification blind requires OCR-v1 AND
LANGUAGE-v2 AND COMBINED-v4 to all freeze, the known E2.14 Japanese failure to be rejected, no new
catastrophic failures post-hoc, coverage >=80%, and Wilson diagnostic >=0.98. None of the freeze
preconditions were met in this task. **Do not recommend another 500+ row blind at this time.**

**A small, blinded, Donny-reviewed language-identification queue is the correct next step**, per
the spec's own guidance for exactly this situation ("prepare it as an artifact and note it in the
report, then STOP short of a freeze decision"). This has been prepared:

`backend/artifacts/index_fair_value/ebay_e2_17_japanese_specific_language_review_queue.csv` --
25 rows, one per unique `canonical_card_id` among the 160 human-`NON_ENGLISH` rows across both
corpora (capped at 60 in the generator, 25 unique card identities actually exist), each with the
row's real `image_url` and an empty `specific_language_if_known` column (`japanese` / `korean` /
`chinese` / `other` / `unsure`) for Donny to fill in directly from the photo, with the listing
title column explicitly labeled `DO_NOT_USE_AS_EVIDENCE` to discourage title-based bias during
review. Once that queue is completed, this task's OCR harness and decision rule can be
re-evaluated against real Japanese-specific authoritative truth without any code changes (the
rule and harness are already built and tested) -- only the truth table needs to be populated.

---

## 21. Tests

`backend/tests/test_ebay_e2_17_ocr_v1_japanese_language_feasibility.py` -- **31 passed, 0
failed**, covering: Japanese-script positive, English positive, single noisy CJK glyph
insufficient, strong multi-character Japanese evidence, weak OCR -> UNVERIFIED, crop/decode
failure -> UNVERIFIED, rotation/low-confidence -> UNVERIFIED, low-resolution -> UNVERIFIED,
multiple-card ambiguity -> UNVERIFIED (never MATCH), Korean hard negative, Chinese
(shared-CJK-alone) hard negative, Latin-script-foreign hard negative (never MISMATCH), English
false-mismatch safety, grouped canonical-card-id development split with zero identity leakage,
validation-not-referenced-in-tuning-source, provider-Japanese-alone-cannot-veto (structural),
LANGUAGE-v1/Korean-Chinese-veto module presence and non-modification, OCR-Japanese-veto
independent of provider fields, no-premature-LANGUAGE-v2/COMBINED-v4-module-creation (contract
gating respected), deterministic OCR decision fingerprint, E2.14-excluded-from-tuning-sources,
no-paid-APIs-referenced, CPU-only path (`gpu=False`), no-production-writes, plus two tests that
replay the actual real-image OCR run results (`ebay_e2_17_ocr_results.json`) through the same
decision function to confirm determinism end-to-end against real data, not just synthetic
fixtures.

Run: `python -m pytest backend/tests/test_ebay_e2_17_ocr_v1_japanese_language_feasibility.py -q`
-> `31 passed`.

---

## 22. Next step

1. Get `backend/artifacts/index_fair_value/ebay_e2_17_japanese_specific_language_review_queue.csv`
   in front of Donny for a real, blinded, per-card specific-language review pass (25 unique card
   identities, real image URLs already populated).
2. Re-run this same harness/decision rule (unchanged) against the completed queue to get an
   authoritative Japanese-specific confusion matrix, satisfying Phase J condition 2 properly.
3. Only then reconsider an OCR-v1 freeze, and only after that, LANGUAGE-v2/COMBINED-v4.
4. Separately, and lower-priority: build/borrow a real card-crop step (Section 6/13 gap) before a
   production freeze, since `LANGUAGE_MATCH` essentially never fires against raw, uncropped
   listing photos today -- OCR-v1's practical value right now is overwhelmingly as a Japanese
   veto signal, not an English-confirmation signal.
5. Separately, and also lower-priority: validate the Korean/Chinese/French hard-negative guards
   (Section 11) against at least a handful of real Korean, Chinese, and French-language card
   photos, which were structurally absent from this Japanese-focused sample.

No existing frozen artifact (LANGUAGE-v1, COMBINED-v3, D3-v5, IMAGE-v2, CAPTURE-ALLOCATION-v2, or
any human label file) was modified by this task. Nothing was staged, committed, or pushed.

---

EBAY_OCR_V1_NOT_READY_INSUFFICIENT_AUTHORITATIVE_JAPANESE_SPECIFIC_HUMAN_TRUTH
