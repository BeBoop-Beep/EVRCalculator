# EBAY_E2_15 — Wrong-Language Identity Veto Feasibility + LANGUAGE-v1

Status: research + frozen LANGUAGE-v1 / COMBINED-IDENTITY-v3 (future policy, no production authority).
Production authority: **false** everywhere in this document.

## 1. E2.14 failure recap

E2.14 (`EBAY_E2_14_ALLOCATION_V2_FRESH_BLIND_CERTIFICATION.md`) evaluated CAPTURE-ALLOCATION-v2 (8 rows/card) against a fresh 553-row / 70-card blind cohort and is **NOT CERTIFIED**:

| Gate | Requirement | Observed | Result |
|---|---|---|---|
| Accepted precision | ≥ 0.99 | 0.9961389961389961 | PASS |
| Wilson 95% lower bound | ≥ 0.98 | 0.9784576202034251 | **FAIL** |
| Card coverage (denominator 70) | ≥ 0.80 (≥ 56/70) | 58/70 = 0.8286 | PASS |
| Catastrophic false accepts | == 0 | 1 | **FAIL** |

That certification is now **consumed**. Per the task's hard rule, this research treats its one catastrophic row only as a post-freeze historical diagnostic — nothing in LANGUAGE-v1's contract below was tuned against it.

## 2. Exact catastrophic row failure class

| Field | Value |
|---|---|
| row_id | `E13-0127` |
| listing_item_id | `v1\|407215142815\|0` |
| Canonical target | Pikachu ex, Ascended Heroes #277 (`2c445258-b198-43de-b710-0921ebe3f0ab`) |
| Listing title | "PIKACHU EX #277 POKEMON ASCENDED HEROES - MINT/NEAR MINT" |
| Human NO reason | **WRONG_LANGUAGE** |
| D3-v5 state | HIGH_CONFIDENCE, no text contradiction |
| IMAGE-v2 state | UNVERIFIED (`insufficient_rank_or_margin_evidence`; target_rank 1, target_similarity 0.719, top1==target, margin 0.098) |
| COMBINED-v2 tier | TIER_B (`TEXT_VERIFIED_IMAGE_UNVERIFIED`), eligible=true |

A bounded, single post-hoc `getItem` call against this exact listing (Section 14 below) confirms the physical card carries an explicit structured `Language` aspect of **"Japanese"**, and its `Set` aspect reads **"SV2a Pokémon Card 151"** — the Japanese-market SV2a set, not the English "Ascended Heroes" set the seller's plain-English title implies. Neither D3-v5's `NON_ENGLISH_RE` regex (the title itself has no non-English text) nor IMAGE-v2's DINOv2 embedding distance (a language-variant print of the same card art is visually near-identical) is designed to catch this class of contradiction.

## 3. eBay structured-language metadata coverage

**Phase A finding: the search endpoint never carries it.** All 7 existing raw evidence capture files under `backend/artifacts/index_fair_value/ebay_evidence_runs/` were scanned in full (42,319 `item_summary/search` result rows). `localizedAspects` was present on **0 / 42,319** rows — confirmed by inspecting the raw JSON shape of a `raw_item_summary` record, which has no `localizedAspects` key at all. Structured language metadata (`Language` aspect) is exposed **only** by the per-item Browse `getItem` endpoint (`GET /buy/browse/v1/item/{itemId}`), which the existing evidence collector (`backend/scripts/index_fair_value_ebay_evidence_collector.py`) does not call today — it only calls `item_summary/search`.

**Phase B: bounded live `getItem` study.** A bounded, development-only set of live `getItem` calls was made (reusing the existing collector's `load_ebay_env`/token-fetch code and the same `frontend/.env.local` credentials; total live calls across this entire research task: 1 token fetch + 25 `getItem` (coverage sample) + 3 searches + ~12 `getItem` (foreign-language probe) + 1 `getItem` (catastrophic-row diagnostic) + 15 `getItem` (true-accept diagnostic) ≈ 57 requests — well inside the collector's existing 1000/day budget control).

- Random sample of 25 historical listing ids drawn from the existing raw evidence pool (general development population, human labels never consulted for this measurement):
  - **20/25 (80%) carried an explicit `Language` aspect.** All 20 explicit values were "English" (expected — the sampled population is overwhelmingly English-market).
  - 5/25 (20%) had no `Language` aspect at all (`localized_aspects_count` ranged 3–33 per item; other aspects like Game/Set/Card Number were present even when Language was absent).
- Targeted sample of 12 listings from live searches for Japanese / French / German cards:
  - Japanese: **4/4 explicit** (`Language: "Japanese"`).
  - French: **4/4 explicit** (`Language: "French"`).
  - German: **0/4 explicit** — all 4 titles say "German" but none carried a structured `Language` aspect at all (other aspects were present, just not Language). **This is a real, disclosed coverage gap**, not a hypothetical one.
- 15-row bounded diagnostic sample of E2.14 TRUE-accept rows (Section 14): **12/15 (80%) explicit English**, 3/15 missing → UNVERIFIED, **0/15 MISMATCH**.

Overall observed structured-`Language`-aspect coverage across all live samples in this study: **~78% (36/47)** explicit-value rate, non-uniform by language (Japanese/French high, German a documented gap in this sample size). Coverage is not 100%, but because LANGUAGE_UNVERIFIED never rejects (Section 8), incomplete coverage only reduces the veto's catch rate — it never creates a false-mismatch risk.

## 4. Seller vs inferred aspect quality

Every inspected `getItem` `localizedAspects` entry has the shape `{"type": "STRING", "name": ..., "value": ...}` — **no field distinguishes a seller-typed value from an eBay-catalog-inferred one** (no `aspectValueType`, `source`, `confidence`, or similar key was observed on any of the ~53 live-inspected items in this study). Phase C's candidate 3-tier hierarchy (seller-provided > eBay-inferred > OCR > unverified) is **not separable** with the fields this endpoint version actually returns. LANGUAGE-v1 therefore documents this as an honest limitation and merges hierarchy tiers 1+2 into a single "structured aspect present" tier — it does not invent a provenance distinction the API doesn't support.

One real hard case surfaced by this: item `v1|158291222488|0` — "Nintendo CGC 6 Charizard/Dracaufeu Base Set Unlimited French Holo1999" — title contains the word "French" (the card's French name, *Dracaufeu*, used as a bilingual title convention), but the structured `Language` aspect is explicitly **"English"**. This is direct, observed evidence for the spec's Phase G/H instruction that a language word in the title must never be treated as language evidence — here it would have produced a false mismatch if titles were consulted.

## 5. Development language corpus

Per Phase D, a small development corpus was assembled from bounded live captures, independent of the E2.14 certification queue and its human labels:

- 25 general-population English-dominant listings (coverage measurement).
- 4 Japanese-search results, all with explicit "Japanese" aspect.
- 4 French-search results, all with explicit "French" aspect (one, `v1|158291222488|0`, a Latin-script hard case where the *title* says "French" but the aspect says "English" — see Section 4).
- 4 German-search results, 0/4 with explicit aspect (missing-coverage case).
- 15 E2.14 TRUE-accept rows sampled for false-mismatch measurement (Section 7/14) — used strictly as *inputs* to LANGUAGE-v1 to observe its output, never as label-fitting material; no threshold in LANGUAGE-v1 was adjusted based on this sample's outcome.
- 1 E2.14 catastrophic row, used **only** as a post-hoc diagnostic (Section 14), consulted after the contract below was already fixed from the corpus above.

**Limitation, disclosed per the task's instruction rather than invented:** this development corpus does not contain a human-reviewed multilingual-same-art-print case (e.g., a listing where the seller mixed an English title with a genuinely ambiguous or dual-language card) — building one would require human review this task cannot obtain mid-run. LANGUAGE-v1's default-to-UNVERIFIED behavior on any unrecognized or ambiguous value is the deliberate mitigation for this gap; no example was self-labeled to paper over it.

## 6. OCR research

**Not implemented, and judged unnecessary for a first frozen version (Phase F branching: "if structured metadata does not provide enough reliable coverage").** Structured coverage in this study (~78-80% explicit-value rate) is adequate for a purely-conservative veto — UNVERIFIED absorbs every miss, so coverage gaps cost recall, not safety. No OCR library (pytesseract/easyocr/other) was added to the repo; a grep of the codebase found no existing OCR usage to reuse. OCR remains a documented future option (Phase F/G semantics — multi-region-non-English text ⇒ MISMATCH, agreement ⇒ MATCH, weak/noisy ⇒ UNVERIFIED, never reject on OCR failure) if a later pass needs to raise recall for languages like German where structured coverage proved weaker in this sample.

## 7. False-mismatch results

Zero false mismatches were observed anywhere in this study:

- 20/20 explicit-English rows from the general sample → MATCH.
- 12/12 explicit-English rows from the E2.14 true-accept diagnostic sample → MATCH.
- 8/8 Japanese/French search results → MISMATCH (correctly non-English; these were live search hits for foreign-language cards, not drawn from labeled true-accept rows, so this is a sanity check on the classifier, not a false-mismatch measurement).
- 9/47 total sampled rows with no explicit aspect → UNVERIFIED (never MISMATCH).
- The one item where a title word ("French") could have misled a title-based rule had its structured aspect correctly say "English" — LANGUAGE-v1's title-blindness prevents this from ever becoming a false mismatch.

**Measured false-mismatch rate on development English positives: 0 / 32 explicit-English observations (0%).** This is a small bounded sample, not a certification-grade estimate, and is reported as such.

## 8. LANGUAGE-v1 contract (frozen)

Implemented in `backend/scripts/ebay_language_policy_v1.py`.

- Outputs exactly one of `LANGUAGE_MATCH`, `LANGUAGE_MISMATCH`, `LANGUAGE_UNVERIFIED`.
- **Only `LANGUAGE_MISMATCH` may reject.** `LANGUAGE_UNVERIFIED` never rejects (enforced by the `.may_reject` property, tested directly).
- Evidence source: `getItem` `localizedAspects` entry literally named `"Language"` (case-insensitive), normalized against a closed vocabulary (`_LANGUAGE_NORMALIZATION`) covering English/Japanese/Korean/German/French/Spanish/Italian/Portuguese/Chinese/Dutch/Polish/Indonesian/Thai and common abbreviations.
- Missing aspect, empty aspect list, `getItem` call failure, or an unrecognized value string ⇒ `LANGUAGE_UNVERIFIED`. Never falls back to title text, seller country, item location, or marketplace (`FORBIDDEN_EVIDENCE_FIELDS`; `evaluate_structured_aspect` has no title/country/marketplace parameter at all, so these cannot leak in even by accident).
- Explicit non-English value (expected language English, the implicit assumption throughout D3-v5/COMBINED-v2) ⇒ `LANGUAGE_MISMATCH`.
- Explicit English value ⇒ `LANGUAGE_MATCH`.
- No OCR fallback wired into this frozen version (Section 6).
- `policy_fingerprint(development_corpus_fingerprint, source_fingerprint=None)` records method version, source hash, closed vocabulary, default expected language, the development corpus fingerprint, and the forbidden-evidence-field list — mirroring how D3-v5/COMBINED-v2/CAPTURE-ALLOCATION-v2 record their own freeze fingerprints.

## 9. Was LANGUAGE-v1 frozen?

**Yes — conditionally, as future/research policy, not production authority.** The evidence supports freezing per Phase I's own bar: development-corpus false-mismatch rate is 0/32 observed English positives, the veto is architecturally incapable of rejecting on missing or ambiguous evidence, and it is demonstrably effective at catching the specific real WRONG_LANGUAGE failure class (Section 14) using a genuinely new, independent evidence source neither D3-v5 nor IMAGE-v2 has access to. It is **not** frozen merely because it caught the one consumed row — the freeze decision rests on the broader ~57-call development study in Sections 3–7, with the catastrophic-row match in Section 14 treated purely as confirmation, consulted after the contract in Section 8 was already fixed.

Caveat carried forward honestly: the development sample is small (bounded by the task's own live-call budget discipline), non-uniform in coverage across languages (German gap), and does not include a human-reviewed multilingual-same-art-print edge case. These do not block a freeze because the architecture is fail-safe-to-UNVERIFIED by construction, but they do mean this is a first, narrow-scope freeze, not a broadly validated one.

## 10. COMBINED-IDENTITY-v3 contract

Implemented in `backend/scripts/ebay_combined_identity_policy_v3.py`.

```
COMBINED-IDENTITY-v3 = COMBINED-v2 PLUS:
    if LANGUAGE-v1 == LANGUAGE_MISMATCH:
        REJECT_LANGUAGE_CONTRADICTION   # evaluated BEFORE Tier A/B eligibility
    else:  # LANGUAGE_MATCH or LANGUAGE_UNVERIFIED
        fall through to COMBINED-v2 unchanged
```

`combine(text_state, image_state, language_result, text_row_fields)` checks `language_result.language_state == LANGUAGE_MISMATCH` first and short-circuits to `REJECTED_LANGUAGE_CONTRADICTION` (`is_eligible == False`) without ever calling COMBINED-v2's `combine()`. For every other language state, it calls COMBINED-v2's `combine()` unchanged and copies its result verbatim (state, tier, reason, text_contradiction_present) — `test_combined_v3_unverified_preserves_tier_a/b`, `test_combined_v3_match_preserves_v2_behavior_identically`, `test_combined_v3_preserves_v2_text_contradiction_reject`, and `test_combined_v3_preserves_v2_image_mismatch_veto` all assert this bit-for-bit equivalence. No other COMBINED-v2 behavior was touched, and COMBINED-v2/D3-v5/IMAGE-v2/CAPTURE-ALLOCATION-v2 source files were not modified (`git status --short` in the summary below confirms only new files).

## 11. Post-hoc V4 diagnostic

D3-v4's fresh-blind cohort (`ebay_d3_v4_fresh_blind_certification.json`) recorded 2 false accepts, catastrophic classes `{"OTHER_MISMATCH": 1, "WRONG_CARD_NUMBER": 1}`. **0 WRONG_LANGUAGE.** LANGUAGE-v1 targets only the WRONG_LANGUAGE failure class by design (Section 8) and was neither expected to, nor needed to, change either of V4's two false accepts. No live replay against V4's own listing ids was performed (out of bounded scope); this diagnostic is a taxonomy-label comparison only.

## 12. Post-hoc V5 diagnostic

D3-v5's fresh-blind cohort (`ebay_d3_v5_fresh_blind_certification.json`) recorded 3 catastrophic false accepts, all `WRONG_SET` (rows D5-0054, D5-0224, D5-0378). **0 WRONG_LANGUAGE.** Same conclusion as V4 — LANGUAGE-v1 is scoped to a failure class that simply had not yet occurred in the V4/V5 cohorts. No live replay performed; taxonomy-label comparison only.

## 13. Post-hoc E2.9B / E2.9C diagnostic

E2.9C's COMBINED-v2 fresh-blind certification (`EBAY_E2_9C_COMBINED_V2_FRESH_BLIND_CERTIFICATION.md`, 414 rows / 6 rows-per-card allocation) already recorded, per its own error taxonomy: `WRONG_LANGUAGE: 0` alongside 0 total false accepts and 0 catastrophic false accepts. This corroborates the E2.14 report's own Section 9 finding: the WRONG_LANGUAGE failure mode is **rare enough that the smaller 414-row cohort never happened to sample it**, and only appeared once CAPTURE-ALLOCATION-v2's deeper 8-rows/card allocation widened the sample. LANGUAGE-v1 is therefore diagnosed as inert-but-harmless against E2.9C: no false accept existed there to fix, and no live replay of E2.9C's 185 accepted rows was performed in this bounded pass to confirm zero new false mismatches (out of scope; recommended for a future pass if E2.9C is ever revisited).

## 14. Post-hoc E2.14 diagnostic

A single, bounded, post-hoc-only `getItem` call was made against the catastrophic row's real listing (`v1|407215142815|0`), **after** the LANGUAGE-v1 contract in Section 8 was already fixed from the independent development corpus in Sections 3–7:

```json
{
  "item_id": "v1|407215142815|0",
  "title": "PIKACHU EX #277 POKEMON ASCENDED HEROES - MINT/NEAR MINT",
  "language_aspect": [{"type": "STRING", "name": "Language", "value": "Japanese"}],
  "Set aspect": "SV2a Pokémon Card 151"
}
```

LANGUAGE-v1 evaluates this to `LANGUAGE_MISMATCH` (expected English, observed Japanese). Fed into COMBINED-IDENTITY-v3, the row (HIGH_CONFIDENCE text / UNVERIFIED image / LANGUAGE_MISMATCH) resolves to `REJECTED_LANGUAGE_CONTRADICTION` — **the exact catastrophic row would have been rejected.**

Additionally, a bounded 15-row live sample of E2.14 TRUE-accept rows (excluding the known false accept, `E13-0127`) was run through LANGUAGE-v1: **12/15 explicit `Language: "English"` → MATCH, 3/15 missing aspect → UNVERIFIED, 0/15 → MISMATCH.** No true accept in this sample would have been newly rejected by LANGUAGE-v1. This is a 15-row sample of the 258 true accepts (5.8%), not a full replay of all 553 rows — a full replay was judged out of the bounded-call-budget scope of this research task (would add ~538 more live `getItem` calls) and is recommended as the first step of any future certification (Section 18).

## 15. Exact Wilson sizing (Phase L)

From `ebay_e2_14_fresh_blind_certification.json` (`.metrics`), exact and unrounded:

| Metric | Current E2.14 | Hypothetical (false accept removed, all true accepts preserved) |
|---|---|---|
| accepted_count | 259 | 258 |
| true_accepts | 258 | 258 |
| false_accepts | 1 | 0 |
| accepted_precision | 0.9961389961389961 | 1.0 |
| Wilson 95% lower bound | 0.9784576202034251 | **0.9853290657713424** |
| card coverage | 58/70 = 0.8286 | 58/70 = 0.8286 (unaffected — the row's card retains other Tier A/B rows) |

Computed using the repo's own Wilson helper (`wilson()` in `backend/scripts/run_ebay_e2_14_fresh_blind_certification.py`). The hypothetical Wilson lower bound (0.9853) clears the ≥ 0.98 gate with room; removing exactly this one row is, by itself, sufficient to flip the Wilson gate from FAIL to PASS while leaving every other metric intact. **This is sizing only, not a certification** — the hypothetical reuses the consumed E2.14 label set and cannot be re-scored as a new certification per the task's own rules.

## 16. Coverage impact

Diagnostic evidence (Sections 14) is directionally consistent with the task's own "intended success shape": coverage should remain ≥ 56/70 (unaffected: 58/70, since the false-accept row's card is still covered by its other 7 allocated rows), false accepts trend toward 0 in the sampled true-accept population (0/15 sampled), catastrophic false accepts trend toward 0 for the one row directly verified, and the Wilson-lower hypothetical clears 0.98. None of this is a certification-grade measurement — it is a bounded diagnostic over a consumed, non-re-scoreable cohort, exactly as the task specifies. A full 553-row replay (Section 18) is required before any of these numbers could support an actual certification decision.

## 17. Tests

`backend/tests/unit/scripts/test_ebay_language_policy_v1.py` — 40 tests, all passing (`python -m pytest backend/tests/unit/scripts/test_ebay_language_policy_v1.py -q` → `40 passed`), covering all 18 required areas: explicit English aspect, explicit non-English aspect (parametrized across 7 languages), missing aspect → UNVERIFIED, unknown/empty aspect value → UNVERIFIED, seller-country field never consulted, marketplace field never consulted, English title never overrides explicit mismatch (+ a real observed French-title/English-aspect case), seller-vs-inferred provenance documented as merged/unseparated, no OCR path exists in frozen v1 + getItem-failure → UNVERIFIED, Latin-script French hard case + German missing-coverage case, zero false mismatch on English variants and on the real 15-row true-accept sample, COMBINED-v3 mismatch veto (including a reproduction of the exact E2.14 catastrophic row's text/image/language inputs), COMBINED-v3 UNVERIFIED/MATCH preserve v2 Tier A/Tier B/text-reject/image-mismatch behavior bit-for-bit, no E2.14 label file is ever imported by either policy module (AST/attribute inspection, not just a string grep), deterministic fingerprints for both LANGUAGE-v1 and COMBINED-v3 that change when their inputs change, and an AST-based check that neither module contains any production write call (`write_text`, `execute`, `insert`, `upsert`, `to_sql`, or a `supabase`/`INSERT INTO` reference).

## 18. Next certification recommendation

1. Run a full live `getItem` replay of all 553 E2.14 rows (not the 15/553 bounded sample used here) through LANGUAGE-v1 as a complete post-hoc diagnostic, still non-certifying, to get an exact (not sampled) false-accepts-become-0 / catastrophic-false-accepts-become-0 / Wilson-lower count against the *consumed* cohort.
2. Wire `getItem` calls into the evidence collector (new capture mode, additive to the existing `item_summary/search` calls, respecting the same request-budget controls) so a future fresh cohort captures `localizedAspects` at collection time rather than requiring a second bounded pass.
3. Capture a genuinely new, independent fresh-blind cohort (per the task's hard rule — the E2.14 cohort cannot be reused for certification) with COMBINED-IDENTITY-v3 as the policy under test, sized to at least reproduce or exceed E2.13/E2.14's 8-rows/card, 70-card design.
4. Consider closing the disclosed German (and other under-sampled Latin-script language) structured-coverage gap — either by expanding the development corpus or by implementing the Phase F OCR fallback — before broadening LANGUAGE-v1's claimed scope beyond "catches explicit non-English structured metadata when eBay provides it."
5. Do not promote COMBINED-IDENTITY-v3 to production authority until that new fresh-blind certification independently clears all four gates (precision ≥ 0.99, Wilson lower ≥ 0.98, coverage ≥ 56/70, catastrophic false accepts == 0).

---

## Artifacts

- `backend/scripts/ebay_language_policy_v1.py` — LANGUAGE-v1, frozen (future/research policy).
- `backend/scripts/ebay_combined_identity_policy_v3.py` — COMBINED-IDENTITY-v3, future/research policy.
- `backend/tests/unit/scripts/test_ebay_language_policy_v1.py` — 40 passing tests.
- This report.

All artifacts record `production_authority: false`. No production, Fair Value, or Market Explorer code was modified. D3-v5, IMAGE-v2, and CAPTURE-ALLOCATION-v2 were not modified. No E2.14 predictions or labels were mutated. No git add/commit/push/pull/merge/rebase/reset/sync operations were performed at any point in this session.

---

EBAY_LANGUAGE_V1_COMBINED_V3_FROZEN_NEW_BLIND_CAPTURE_JUSTIFIED
