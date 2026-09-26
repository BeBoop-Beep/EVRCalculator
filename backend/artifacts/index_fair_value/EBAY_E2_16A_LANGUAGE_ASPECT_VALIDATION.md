# EBAY E2.16A -- Frozen Human-Truth Language-Aspect Validation + LANGUAGE-v1 Freeze Decision

**Status: DEVELOPMENT ONLY. `development_only=true`, `production_authority=false`. Not a certification. Does not modify D3-v5, IMAGE-v2, CAPTURE-ALLOCATION-v2, or the frozen/consumed E2.14 certification.**

Analysis code: `backend/scripts/ebay_e2_16a_language_aspect_validation.py`
Tests: `backend/tests/test_ebay_e2_16a_language_aspect_validation.py` (35 passed)

---

## 1. Phase A -- Precondition results

All nine preconditions were independently recomputed from the on-disk artifacts (not assumed from the task's stated numbers) and **all passed**:

| # | Precondition | Result |
|---|---|---|
| 1 | corpus row count = 200 | PASS -- 200 rows in `ebay_e2_16_language_development_queue.csv` |
| 2 | corpus fingerprint matches | PASS -- recomputed `8a22b6a76bb2eade33b0e0dddbba49a3ac8203067dcfcb3d291d4ffe07f0319f` == manifest == spec-stated value |
| 3 | human label fingerprint matches | PASS -- recomputed `1934c5f038f62584432c32d5538983b851a2a63a1cb8a3a972f09a5e7d7fd46c` == manifest == spec-stated value |
| 4 | labels complete | PASS -- all 200 rows have a valid `human_truth_label` in `{ENGLISH, NON_ENGLISH, UNCERTAIN}` |
| 5 | counts ENGLISH 134 / NON_ENGLISH 63 / UNCERTAIN 3 | PASS -- recomputed exactly `{"ENGLISH": 134, "NON_ENGLISH": 63, "UNCERTAIN": 3}` |
| 6 | `development_only = true` | PASS |
| 7 | `production_authority = false` | PASS |
| 8 | raw internal evidence row IDs match reviewer rows exactly | PASS -- 200/200 `row_id`s in `ebay_e2_16_language_development_raw_internal.jsonl` match the queue exactly, set-equal |
| 9 | no post-freeze human-label mutation | PASS -- 0 review-history events recorded after `freeze_timestamp` (2026-09-16T18:59:28.210136+00:00); all 205 history events (200 labels + 5 re-labels/edits, reconciled by "latest non-undone event per row_id") predate the freeze |

**All preconditions pass. Proceeding to Phase B onward.**

---

## 2. Frozen human counts

- Total rows: 200
- ENGLISH: 134
- NON_ENGLISH: 63
- UNCERTAIN: 3
- Definitive rows (ENGLISH + NON_ENGLISH, used for the confusion matrix per Phase E): 197

---

## 3. Aspect coverage

- `language_aspect_present = true` for 180/200 rows (90.0%), consistent with the manifest's own `language_aspect_present_rate: 0.9`.
- On the 197 definitive human rows: 177 have a recognized explicit Language aspect value under the E2.16A normalization table (see Section 4-5), i.e. structured-aspect coverage = 177/197 = **89.85%**.
- 20/200 rows have no `Language` aspect at all (`language_aspect_present = false`); these are `<absent>` in the normalization table below.

---

## 4. All raw Language values observed

| raw value | rows | notes |
|---|---|---|
| `English` | 122 | |
| `Korean` | 25 | |
| `<absent>` (no Language aspect) | 20 | |
| `Chinese` | 20 | |
| `Japanese` | 11 | |
| `French` | 1 | |
| `Simplified Chinese` | 1 | distinct string from `Chinese`; not folded into it -- see normalization audit note below |

No German, Spanish, Italian, or Portuguese raw values were observed anywhere in this 200-row corpus. LANGUAGE-v1 therefore has zero development evidence for those languages and per Phase D/H they remain unsupported (`UNVERIFIED`) rather than fabricated.

---

## 5. Normalization table (Phase C audit)

Normalization was performed independently in this task (`NORMALIZATION_MAP` in the analysis script), not by blindly trusting E2.15's `ebay_language_evidence_v1.py` map. E2.15's map was consulted as a starting point, but every raw string actually observed in this corpus was audited by hand against it. One discrepancy was found and is called out below.

| raw value | normalized | row count | human ENGLISH | human NON_ENGLISH | human UNCERTAIN |
|---|---|---|---|---|---|
| `English` | ENGLISH | 122 | 117 | 3 | 2 |
| `Korean` | KOREAN | 25 | 0 | 25 | 0 |
| `<absent>` | UNKNOWN | 20 | 15 | 4 | 1 |
| `Chinese` | CHINESE | 20 | 0 | 20 | 0 |
| `Japanese` | JAPANESE | 11 | 1 | 10 | 0 |
| `French` | FRENCH | 1 | 1 | 0 | 0 |
| `Simplified Chinese` | **UNKNOWN** | 1 | 0 | 1 | 0 |

**Normalization audit finding:** `Simplified Chinese` is a distinct raw string from `Chinese` and was deliberately left unmapped (falls to `UNKNOWN`) rather than folded into `CHINESE`, per the task's "normalize conservatively" instruction and because this specific string form was not one of the values E2.15's map recognized either (E2.15 only mapped `"chinese (simplified)"`/`"chinese (traditional)"`, not `"Simplified Chinese"`). This costs 1 row of recall (a genuinely NON_ENGLISH row stays UNVERIFIED) but avoids guessing at an unvalidated string variant. This is a legitimate target for a future normalization-map addition, not for this freeze.

---

## 6. Confusion matrix (Phase E)

Evaluated on the 197 definitive rows, using the **frozen LANGUAGE-v1 contract** (supported authoritative non-English values = `{KOREAN, CHINESE}` only -- see Section 13 for why Japanese and French were excluded).

| | LANGUAGE_MISMATCH | not MISMATCH (MATCH or UNVERIFIED) |
|---|---|---|
| **Human NON_ENGLISH** (n=63) | TP = 45 | FN = 18 |
| **Human ENGLISH** (n=134) | FP = 0 | TN = 134 |

- **Mismatch precision** = TP/(TP+FP) = 45/45 = **1.0** (Wilson 95% CI: [0.9213, 1.0])
- **Mismatch recall** = TP/(TP+FN) = 45/63 = **0.7143** (Wilson 95% CI: [0.5930, 0.8110])
- **False-mismatch rate on human ENGLISH** = FP/134 = 0/134 = **0.0** (Wilson 95% CI: [0.0, 0.0279])
- **Structured-aspect coverage** (recognized explicit Language / definitive rows) = 177/197 = **0.8985**

### For reference: the broader (all-4-language) candidate that was NOT frozen

If Japanese and French had also been treated as authoritative (the naive "every language the corpus happened to mention" candidate), the numbers would have been: TP=55, FP=2, FN=8, TN=132, precision=0.9649 (Wilson lower 0.8808), recall=0.8730. **This candidate was rejected** because it has 2 observed false mismatches against human-confirmed ENGLISH rows, violating Phase H's "zero observed false mismatch" freeze bar. See Section 11 (conflicts) for the exact two rows.

---

## 7-8. Mismatch precision / recall

See Section 6 above: precision 1.0 (Wilson lower 0.9213), recall 0.7143 (Wilson lower 0.5930), both computed on the frozen `{KOREAN, CHINESE}`-only contract.

## 9. False-mismatch rate

0/134 = 0.0 (Wilson upper bound 0.0279) on the frozen contract. This is the key freeze-justifying number: the explicit Korean/Chinese Language aspect never once produced a false accusation of non-English-ness against a human-confirmed English card in 134 observations.

---

## 10. Per-language results (Phase F)

Grouped by the human-identified non-English language (from `human_language_if_known` free text where the reviewer filled it in, else the observed aspect's language name as a reporting fallback -- never used to compute the confusion matrix itself).

| Language | Human count | Aspect present | Correct non-English aspect | Missing aspect | Wrong aspect (says English) | Unknown aspect value |
|---|---|---|---|---|---|---|
| KOREAN | 25 | 25 | 25 | 0 | 0 | 0 |
| CHINESE | 20 | 20 | 20 | 0 | 0 | 0 |
| JAPANESE | 10 | 10 | 10 | 0 | 0 | 0 |
| UNSPECIFIED (reviewer left language free-text blank, aspect absent/unknown for most) | 5 | 1 | 0 | 4 | 0 | 1 |
| "ENGLISH" (reviewer free-text field literally said English on a NON_ENGLISH-truth row -- i.e. the aspect said English on a NON_ENGLISH card; grouping artifact, not a new language) | 3 | 3 | 0 | 0 | 3 | 0 |

No German, Spanish, Italian, or Portuguese non-English rows exist in this development corpus -- none are fabricated here.

**Important finding:** Japanese has a **perfect explicit-aspect track record on the 10 human-confirmed Japanese rows** (10/10 correct explicit non-English aspect) -- but it is *excluded* from the frozen authoritative set anyway, because a *separate*, human-confirmed-**ENGLISH** row (`e2_16_dev_0153`, Reshiram ex) carries an explicit `Language: Japanese` aspect. That is a false positive against the ENGLISH population, and Phase H requires *zero* false mismatches for a language to be authoritative -- so Japanese is excluded from vetoing despite being reliable on its own true-positive population. This is the correct, conservative outcome per the task's "exclude only that value" instruction (Section 13).

---

## 11. Every conflict row (Phase G)

### Conflict class 1 -- human ENGLISH but aspect non-English (2 rows)

| row_id | item_id | title | human truth | raw aspect | normalized | stratum | forensic read |
|---|---|---|---|---|---|---|---|
| `e2_16_dev_0153` | `v1\|317094720076\|0` | "Reshiram ex 158/086 White Flare" | ENGLISH | Japanese | JAPANESE | LATIN_SCRIPT_FOREIGN | Title and reviewer both say the physical card/photo is English; seller's structured Language aspect says Japanese. Most likely explanation: **seller aspect metadata error** (a bulk-lister mis-tagging or copy-pasting the aspect from a different SKU/variant listing template) -- the title explicitly names an English-language product line ("White Flare" is a real EN-market set), which argues against a genuine Japanese physical card being mislabeled by the human reviewer. Not conclusively provable without OCR/photo re-inspection, but flagged as provider-metadata-wrong is the best-supported read. |
| `e2_16_dev_0160` | `v1\|188817883615\|0` | "French Pokemon Card - Nidoking EX 119/182 - EV10 Destiny Rivalries" | ENGLISH | French | FRENCH | LATIN_SCRIPT_FOREIGN | This is the most instructive conflict in the corpus: the **listing title itself claims "French Pokemon Card"**, yet the human reviewer (judging the photo only, per protocol) labeled it ENGLISH, and the structured Language aspect agrees with the title (French). Two plausible reads: (a) the reviewer correctly identified an English-language card despite a misleading/incorrect seller title+aspect (stock photo mismatch or seller error), or (b) the reviewer made an error. Because human truth is frozen and must not be second-guessed by this task, this row is recorded as-is and drives home exactly why LANGUAGE-v1 must never trust title text as authority -- title and aspect agreeing with each other does not make either one correct against the physical card. |

### Conflict class 2 -- human NON_ENGLISH but aspect English (3 rows)

| row_id | item_id | title | human truth | raw aspect | forensic read |
|---|---|---|---|---|---|
| `e2_16_dev_0092` | `v1\|298470211211\|0` | "Pokemon Chinese ID Set #PMSS1022 Trubbish R" | NON_ENGLISH | English | Title explicitly says "Chinese ID Set"; seller's Language aspect says English anyway. Most likely: **seller aspect metadata wrong / boilerplate default** -- many sellers appear to default the Language aspect field to English regardless of the actual printed card language. |
| `e2_16_dev_0105` | `v1\|377484020097\|0` | "Pokemon Japanese Dachsbun Ex 129 Stella Miracle Special Art Rare SAR NM Holo" | NON_ENGLISH | English | Same pattern -- title says "Japanese," aspect says English. Seller aspect metadata wrong / boilerplate default. |
| `e2_16_dev_0111` | `v1\|137695956422\|0` | "Korean Pikachu ex 044/193 M2a: High Class: MEGA Dream ex Rare Holo 2025 NM" | NON_ENGLISH | English | Same pattern -- title says "Korean," aspect says English. Seller aspect metadata wrong / boilerplate default. |

These three rows are the direct evidence for why LANGUAGE-v1 is a **conservative veto, not a broad classifier**: an English-tagged aspect on a title that self-declares non-English is common enough (3/63 non-English rows, 4.8%) that `LANGUAGE_MATCH` must never be trusted to *positively confirm* a card is English -- it only prevents a MISMATCH veto from firing. This is exactly the contract in Section 13: `LANGUAGE_MATCH` does not promote anything in COMBINED-v3.

### Conflict class 3 -- human NON_ENGLISH but a conflicting (different) foreign-language aspect

0 rows observed. No row's human-confirmed non-English language conflicts with a *different* explicit foreign-language aspect value (i.e. no "human says Korean, aspect says Japanese" case exists in this corpus).

### Conflict class 4 -- human UNCERTAIN with explicit aspect (2 rows)

| row_id | item_id | title | human truth | raw aspect | forensic read |
|---|---|---|---|---|---|
| `e2_16_dev_0011` | `v1\|227267417522\|526472350351` | "Pokemon Pick Your Temporal Forces Reverse Holo Pokémon Card! Near Mint" | UNCERTAIN | English | **Listing with multiple cards / "pick your card" listing** -- the reviewer correctly marked this UNCERTAIN because the photo does not identify a single physical card's language (a "pick one" multi-listing), even though the seller's aspect (English) may be accurate for the whole lot. This is exactly the ambiguity class LANGUAGE-v1 must never resolve on the reviewer's behalf. |
| `e2_16_dev_0021` | `v1\|407117492537\|677292395403` | "CHOOSE YOUR CARD - TEMPORAL FORCES - HOLO/REVERSE - FAST SHIP - VOLUME DISCOUNTS" | UNCERTAIN | English | Same pattern -- "choose your card" multi-item listing, correctly flagged UNCERTAIN by the human reviewer regardless of the aspect value present. |

Both UNCERTAIN conflicts are explained by the same root cause (multi-card "pick your card" listings), not by aspect error, and both are excluded from the confusion matrix per Phase E, as required.

---

## 12. OCR decision (Phase I)

**OCR is not required.** Rationale:

- Structured-aspect coverage is 89.85% on definitive rows, not 100% -- but the task explicitly states OCR is not mandated merely because coverage is short of 100%.
- Within the supported vocabulary (`{KOREAN, CHINESE}`), the explicit `localizedAspects` Language field is a **zero-false-positive, high-recall-within-vocabulary veto**: 45/45 precision, and it correctly flags 100% of every human-confirmed Korean (25/25) and Chinese (20/20) row where the aspect happened to be present, and the aspect was present for every single one of those 45 rows (0 missing-aspect cases among Korean/Chinese truth rows).
- The actual recall gap (18/63 FN) is concentrated in: (a) Japanese rows correctly tagged by the aspect but excluded from the authoritative set by this freeze's conservative bar (10 rows -- addressable by future, larger Japanese-specific development evidence, not by OCR), (b) rows with no aspect at all (4 rows), (c) the one `Simplified Chinese` normalization gap (1 row), and (d) the 3 rows where the seller aspect itself is wrong (English on a non-English card -- OCR would fix these, but they are a small, seller-metadata-quality problem, not a coverage problem).
- LANGUAGE-v1 can remain **intentionally sparse** (MATCH/MISMATCH/UNVERIFIED, with UNVERIFIED as an acceptable, non-rejecting default) exactly as Phase I anticipates.

**Recommendation:** do not build OCR now. If a future workstream wants to raise recall further, first (a) expand the Japanese development sample past 11 observations to see whether the single false positive was a one-off seller-metadata error or a systemic issue, and (b) add the `Simplified Chinese` / `Chinese (Simplified)` string variant to the normalization map -- both are far cheaper than building OCR and would likely close most of the recall gap on their own.

---

## 13. LANGUAGE-v1 contract (frozen)

```
LANGUAGE-v1 (DEVELOPMENT ONLY -- production_authority = false)

Input:  normalized Language aspect value from getItem localizedAspects
        (never: seller country, item location, marketplace, listing title)

Normalization (conservative, only values actually observed + validated
in this development corpus map to a canonical language; everything else
-> UNKNOWN):
    "English"              -> ENGLISH
    "Korean"                -> KOREAN
    "Chinese"                -> CHINESE
    "Japanese"              -> JAPANESE   (normalized but NOT authoritative -- see below)
    "French"                -> FRENCH     (normalized but NOT authoritative -- see below)
    anything else / absent  -> UNKNOWN

Authoritative (veto-eligible) non-English values: { KOREAN, CHINESE }
    -- Japanese and French are explicitly EXCLUDED from the authoritative
       set despite being normalized, because Japanese produced 1 false
       positive against a human-confirmed ENGLISH row (e2_16_dev_0153) and
       French produced 1 false positive against a human-confirmed ENGLISH
       row (e2_16_dev_0160) out of only 1 French observation total. Per
       the task's Phase H instruction ("if one language value is
       unreliable, exclude only that value from the authoritative set"),
       these two values are excluded rather than discarding the whole
       veto.

Classification:
    normalized == ENGLISH                    -> LANGUAGE_MATCH
    normalized in {KOREAN, CHINESE}           -> LANGUAGE_MISMATCH
    normalized in {JAPANESE, FRENCH, UNKNOWN} -> LANGUAGE_UNVERIFIED
    missing/absent aspect                     -> LANGUAGE_UNVERIFIED

No OCR dependency. No seller-country/marketplace/title inference.
```

**Freeze criteria check (Phase H):**

1. Zero observed false mismatch on definitive human-ENGLISH rows for every language proposed as authoritative -- **PASS** (0/134 for KOREAN+CHINESE).
2. Meaningful true-positive evidence (not "one or two catches") -- **PASS** (45 true positives: 25 Korean + 20 Chinese).
3. Supported language values explicitly enumerated from development evidence -- **PASS** ({KOREAN, CHINESE}).
4. Missing/unsupported/unknown values always UNVERIFIED -- **PASS** by construction.
5. No seller-country/marketplace inference -- **PASS**, verified both by design and by an AST-based test.
6. No OCR dependency unless structured metadata proves insufficient -- **PASS**, per Section 12, structured metadata is sufficient for a sparse, conservative veto.

**LANGUAGE-v1 is JUSTIFIED and FROZEN** under this contract.

---

## 14. Freeze fingerprint

```
corpus_fingerprint:        8a22b6a76bb2eade33b0e0dddbba49a3ac8203067dcfcb3d291d4ffe07f0319f
human_label_fingerprint:   1934c5f038f62584432c32d5538983b851a2a63a1cb8a3a972f09a5e7d7fd46c
confusion_matrix_fingerprint (sha256 of sorted "row_id:normalized_language:language_v1_state"):
                            0fc54e48df06c190e77398e4a350dc2cc334f37152254fdad54121c4f909bc2a
supported_authoritative_language_values: ["CHINESE", "KOREAN"]
normalization_version:     e2_16a_v1_conservative
development_only:          true
production_authority:      false
source_hash (this analysis module): backend/scripts/ebay_e2_16a_language_aspect_validation.py (see git diff for exact content; file is untracked/uncommitted per task instructions)
```

---

## 15. COMBINED-IDENTITY-v3 contract (frozen)

Since LANGUAGE-v1 froze, the smallest possible COMBINED-IDENTITY-v3 is defined as:

```
COMBINED-IDENTITY-v3(text_state, image_state, combined_v2_state, language_v1_state):
    if language_v1_state == LANGUAGE_MISMATCH:
        return REJECTED_LANGUAGE_CONTRADICTION
    return combined_v2_state   # COMBINED-v2 behavior preserved exactly otherwise
```

- `LANGUAGE_MATCH` does not promote anything -- a MATCH row falls straight through to whatever COMBINED-v2 already decided.
- `LANGUAGE_UNVERIFIED` does not demote anything -- identical fallthrough.
- No other policy change versus COMBINED-v2. D3-v5 and IMAGE-v2 are untouched (neither module was imported or modified by this task; verified by AST-level inspection in tests).

```
combined_v3_fingerprint (sha256 of "COMBINED-IDENTITY-v3|LANGUAGE-v1|supported=['CHINESE', 'KOREAN']|corpus_fp=...|label_fp=...|confusion_fp=..."):
                            9ec4f99912ec9ea3400b569e30a26d38e4668b95087d05d818c92f19573b4779
```

COMBINED-IDENTITY-v3 is **development only, production_authority=false**, exactly like LANGUAGE-v1. It has not been certified against any fresh blind cohort.

---

## 16. E2.14 post-hoc diagnostic (non-certifying)

E2.14 (`ebay_e2_14_fresh_blind_certification.json`) remains **CONSUMED**. This is diagnostic only and is never treated as a certification pass.

Actual frozen E2.14 metrics, read directly from the certification JSON (not from prose): `accepted_count=259, true_accepts=258, false_accepts=1, accepted_precision=0.9961389961389961, accepted_precision_wilson_95=[0.9784576202034251, 0.9993181125637599], distinct_card_coverage=0.8285714285714286 (58/70)`. This matches the task spec's stated numbers exactly.

**Sizing-only hypothetical, recomputed from the actual artifact (not trusted from prose):** if only the 1 false accept is removed with everything else unchanged: `accepted=258, true_accepts=258, false_accepts=0, precision=1.0`, Wilson lower recomputed here = **0.9853290657713424** (matches the spec's stated ≈0.985329). Coverage is unaffected at 58/70 because E2.14's own report already establishes the false-accept row's target card was covered by its other allocated rows.

**Is the known WRONG_LANGUAGE catastrophic false accept (`E13-0127`, item `v1|407215142815|0`) now rejected under this task's frozen LANGUAGE-v1?**

**No -- not under the E2.16A-frozen contract.** E2.15's prior research (`EBAY_E2_15_WRONG_LANGUAGE_VETO_RESEARCH.md`, Section 14) captured this exact row's live getItem evidence and found `Language: "Japanese"`. Under E2.15's own (broader, JAPANESE-inclusive) proposed contract, that row would have resolved to `REJECTED_LANGUAGE_CONTRADICTION`. **However, this task's independently-recomputed LANGUAGE-v1 (Section 13) explicitly excludes Japanese from the authoritative veto set**, because this development corpus surfaced a genuine Japanese-aspect false positive against a human-confirmed ENGLISH row (`e2_16_dev_0153`) that E2.15's smaller/different development sample did not observe. Under the E2.16A-frozen `{KOREAN, CHINESE}`-only contract, a `Language: Japanese` aspect classifies as `LANGUAGE_UNVERIFIED`, not `LANGUAGE_MISMATCH` -- so COMBINED-IDENTITY-v3 as frozen here would **not** newly reject `E13-0127`.

This is reported honestly rather than reused from E2.15's more permissive finding, per the task's explicit instruction not to trust prose and to recompute independently. It is the single most important finding of this task: **the corpus-validated, conservative freeze is measurably less aggressive than E2.15's proposed contract, and does not catch the one known real-world catastrophic failure it was originally motivated by.** This does not mean LANGUAGE-v1 is worthless (Section 6 shows a genuine, zero-false-positive Korean/Chinese catch rate), but it does mean the specific catastrophic row that motivated E2.15/E2.16 is not solved by what development evidence actually supports freezing today.

- **Any human-YES rows newly rejected?** No live full-553-row replay was performed in this task (would require new live eBay getItem calls, out of scope per the task's working notes -- "should NOT require new live eBay API calls"). E2.15's own bounded 15/553 true-accept sample (12 English/MATCH, 3 missing/UNVERIFIED, 0 Korean/Chinese) shows no true accept in that sample would be newly rejected even under the broader contract, and the E2.16A contract is strictly more conservative (a subset of MISMATCH triggers) than E2.15's, so nothing in that 15-row sample changes under this stricter freeze either. This remains a 15/553 (2.7%) sample, not a full replay, and is explicitly flagged as such.
- **Accepted count / precision / Wilson lower / coverage:** unchanged from the current frozen E2.14 numbers above, because this task performed no new full-cohort replay -- see "next step" (Section 19) for what a genuine post-hoc recomputation would require.
- **Catastrophic false accepts:** the one known WRONG_LANGUAGE row is not resolved by the frozen (conservative) LANGUAGE-v1, per above.

---

## 17. V4/V5/E2.9B post-hoc results

No item-level Language-aspect evidence exists in the on-disk V4 (`ebay_d3_v4_fresh_blind_certification.json`), V5 (`ebay_d3_v5_fresh_blind_certification.json`), or E2.9B/E2.9C (`EBAY_E2_9B_COMBINED_V2_FRESH_BLIND_CAPTURE.md`) cohort artifacts -- their frozen predictions/certifications record text/image verification states only, with no captured `localizedAspects`. Reproducing E2.15's own conclusion (Section 4 of `EBAY_E2_15_WRONG_LANGUAGE_VETO_RESEARCH.md`), which is corroborated here by inspecting those same certification files directly:

- **D3-v4**: 2 false accepts recorded, taxonomy `{OTHER_MISMATCH: 1, WRONG_CARD_NUMBER: 1}`. **0 WRONG_LANGUAGE.** LANGUAGE-v1/COMBINED-v3 is inert against V4 -- it targets a failure class that never occurred in that cohort. No live replay performed here (would require new getItem calls against V4's 420-ish rows, out of this task's bounded scope).
- **D3-v5**: 3 catastrophic false accepts, all tagged `WRONG_SET` (rows D5-0054, D5-0224, D5-0378). **0 WRONG_LANGUAGE.** Same conclusion -- inert-but-harmless.
- **E2.9B/E2.9C**: the frozen E2.9C certification's own error taxonomy records `WRONG_LANGUAGE: 0` alongside 0 total and 0 catastrophic false accepts. Inert-but-harmless; no false accept existed to fix.

These are taxonomy-label comparisons against artifacts already on disk, not new live replays, and are reported as such rather than re-verified live (consistent with the task's "should NOT require new live eBay API calls" guidance).

---

## 18. Is a new certification blind justified?

**Yes, but scoped narrowly to the validated {KOREAN, CHINESE} veto, not to the broader contract that would have caught the E2.14 catastrophic row.**

Justification:
- LANGUAGE-v1 (as frozen here) demonstrates a genuine, zero-false-positive, meaningfully-recall'd (45 TP) signal on an independent, blind-labeled 200-row development corpus -- this is real, new evidence, not noise.
- It is architecturally incapable of rejecting on missing or ambiguous evidence (UNVERIFIED is the safe default), so worst case it is a no-op on any row where the aspect is absent, Japanese, French, or otherwise unsupported.
- COMBINED-IDENTITY-v3 makes the smallest possible change to COMBINED-v2 (a single additive veto condition), so certification risk is limited to that one new decision path.
- However, Section 16 shows this specific frozen contract would **not** have caught the E2.14 catastrophic row that originally motivated this whole workstream (that row's Japanese-tagged evidence is excluded from authority here). A new blind capture should be explicit that it is certifying a **Korean/Chinese-only** wrong-language veto, not a general-purpose wrong-language fix, and should NOT claim it retroactively resolves E13-0127.
- A future, larger, Japanese-focused development pass (to determine whether the single Japanese false positive found here was a one-off seller-metadata error or systemic) is the natural next step before Japanese could ever be added to the authoritative set.

---

## 19. Tests

`backend/tests/test_ebay_e2_16a_language_aspect_validation.py` -- **35 passed**, run via:

```
"/c/Users/Owner/AppData/Local/Programs/Python/Python38/python" -m pytest backend/tests/test_ebay_e2_16a_language_aspect_validation.py -q
```

Coverage against the 24 required test areas (all present, several with more than one concrete test):
1. frozen corpus fingerprint mismatch blocks -- `test_corpus_fingerprint_mismatch_blocks`
2. label fingerprint mismatch blocks -- `test_label_fingerprint_mismatch_blocks`
3. UNCERTAIN excluded -- `test_uncertain_excluded_from_confusion_matrix`
4. explicit English -> MATCH -- `test_explicit_english_is_match`
5. validated non-English -> MISMATCH -- `test_validated_non_english_is_mismatch` (parametrized Korean/Chinese)
6. unsupported language -> UNVERIFIED -- `test_unsupported_language_is_unverified` (parametrized Japanese/French/German/Spanish/Italian/Portuguese)
7. missing language -> UNVERIFIED -- `test_missing_language_is_unverified`
8. unknown language -> UNVERIFIED -- `test_unknown_raw_value_is_unverified`
9. seller country ignored -- `test_seller_country_never_consulted` (AST-based)
10. marketplace ignored -- `test_marketplace_never_consulted` (AST-based)
11. English title cannot override mismatch -- `test_english_title_cannot_override_mismatch`, `test_classify_language_v1_signature_excludes_title`
12. mismatch precision calculation -- `test_mismatch_precision_calculation`
13. mismatch recall calculation -- `test_mismatch_recall_calculation`
14. false-mismatch calculation -- `test_false_mismatch_rate_calculation`
15. supported-language allowlist -- `test_supported_language_allowlist_explicit`
16. unsupported language cannot veto -- `test_unsupported_language_cannot_veto`
17. LANGUAGE_MISMATCH rejects in COMBINED-v3 -- `test_language_mismatch_rejects_in_combined_v3`
18. LANGUAGE_MATCH preserves v2 behavior -- `test_language_match_preserves_v2_behavior`
19. LANGUAGE_UNVERIFIED preserves v2 behavior -- `test_language_unverified_preserves_v2_behavior`
20. D3-v5 immutable -- `test_d3_v5_and_image_v2_never_imported_or_mutated`, `test_d3_v5_freeze_manifest_file_untouched_by_this_task`
21. IMAGE-v2 immutable -- covered by the same AST-based check (20)
22. consumed E2.14 excluded from tuning -- `test_e2_14_never_referenced_in_frozen_contract_functions`
23. deterministic freeze fingerprint -- `test_freeze_fingerprint_deterministic`
24. no production writes -- `test_no_production_write_calls_in_module`

Plus supplementary tests validating end-to-end artifact consistency (`test_preconditions_pass_on_real_artifacts`), per-language totals, exact conflict-row counts, and the E2.14 sizing-only Wilson-lower recomputation (0.985329...).

---

## 20. Next step

1. If a new certification blind is captured (Section 18), scope it explicitly to the `{KOREAN, CHINESE}`-only LANGUAGE-v1 contract and COMBINED-IDENTITY-v3 as frozen here -- do not silently broaden to Japanese/French without new, larger, dedicated development evidence for those languages.
2. Investigate the single Japanese false positive (`e2_16_dev_0153`) and single French false positive (`e2_16_dev_0160`) further -- ideally with a larger, targeted development sample -- before either language could be added to the authoritative veto set.
3. Add the `Simplified Chinese` (and likely `Chinese (Simplified)`/`Chinese (Traditional)`) raw-string variants to the normalization map; this is a low-risk, evidence-backed recall improvement independent of any language's authoritative status.
4. If E2.14 is ever revisited for an actual (non-diagnostic) re-certification, that would require a full live-replay `getItem` capture across all 553 rows -- out of this task's scope and explicitly not performed here.
5. Do not deploy LANGUAGE-v1/COMBINED-v3 to production; both remain `production_authority=false` pending a real fresh-blind certification pass.

---

## Confirmation of scope compliance

- No frozen human labels were modified.
- D3-v5, IMAGE-v2, and CAPTURE-ALLOCATION-v2 were not modified (verified by AST-level test, Section 19 item 20/21).
- E2.14 was not rewritten and is never called a certification pass in this report (Section 16).
- No new certification blind was captured.
- No E3 work, Fair Value, or Explorer changes were made.
- No git add/commit/push/pull/merge/rebase/reset/sync was run. All new files (`backend/scripts/ebay_e2_16a_language_aspect_validation.py`, `backend/tests/test_ebay_e2_16a_language_aspect_validation.py`, this report) remain uncommitted in the working tree.

---

EBAY_LANGUAGE_V1_COMBINED_V3_FROZEN_NEW_BLIND_CAPTURE_JUSTIFIED
