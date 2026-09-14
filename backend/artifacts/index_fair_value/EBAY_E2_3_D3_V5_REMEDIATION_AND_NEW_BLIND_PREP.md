# eBay E2.3 — D3-v5 Catastrophic False-Accept Remediation + New Blind Prep

## 1. V4 failed certification summary

Real, genuinely-run certification (`ebay_d3_v4_fresh_blind_certification.json`, reproduced unchanged in this session):

| Metric | Value |
|---|---|
| Definitive human-labeled rows | 420 |
| Matcher accepted (HIGH_CONFIDENCE) | 218 |
| True accepts | 216 |
| False accepts | 2 |
| Accepted precision | 0.99082569 |
| Wilson 95% lower | 0.96717241 |
| Accepted recall | 0.87096774 |
| Card coverage | 57/70 = 0.81428571 |

| Gate | Result |
|---|---|
| precision ≥ 0.99 | PASS |
| Wilson lower ≥ 0.98 | **FAIL** |
| coverage ≥ 0.80 | PASS |
| catastrophic == 0 | **FAIL** |

**`EBAY_D3_V4_NOT_CERTIFIED`**

## 2. Immutable V4 artifact fingerprints

- Certification artifact SHA-256: `07a965fd6d7987c3cec56eede3e87c91efc3224574a0c94fc30e7952847d0ec3`
- Cohort fingerprint: `31e97a7429a24afa4595a16902a15f1d52e0b18eddb44be780e6c0cf80e5d19b`
- Final label fingerprint: `2153104730b3c7b96c6ea19aef3e7cc2a6a850dfe9ab0e31286f1a2a9f7ea346`
- V4 matcher fingerprint evaluated: `14336982da2cbd420f686c350cc47f5c2843dd94afb7b711175a7f7dbe14b523`

Recorded, immutable, in `ebay_d3_v4_fresh_blind_consumed_status.json`
(`status: CONSUMED_HISTORICAL_DIAGNOSTIC_ONLY`,
`eligible_for_future_certification_of_any_matcher: false`). No V4 artifact
(cohort, labels, certification result) was modified, regenerated, or
replaced by this task.

## 3. Exact root cause of D4-0375

**Listing**: "Roaring Moon ex - 162/131 - Pokemon Prismatic Evolutions Special Illustration NM", target collector number `162`.

The listing's fraction `162/131` **exactly matches** the target's recorded
number (`162`) via `FRACTION_RE` — a fully structured match, not the bare-
digit fallback path v4's existing number-context guard addresses. Searched
DEVELOPMENT for the same target card (`d09b2fb5-...`, canonical card
"Roaring Moon ex"): **6 independent development listings** exist for this
exact target, **all six show the identical `162/131` (or `#162`) numbering**,
and **two of them are human-gold-labeled `EXACT_TARGET_MATCH`**
(`D2-0933`, `D2-0939`). This proves `162/131` is the normal, correct
numbering convention for this card — not a text-pattern defect.

**Conclusion**: this is not a fixable text-parsing gap. It is an
**image-only identity risk**, structurally undetectable from
title/condition/aspect text — exactly analogous to the repository's
already-documented `IMAGE_ONLY_GRADED_RISK` precedent (`D2-0310` in the v3
development study, where a slab was only visible in the photo). No rule was
written for this failure. Inventing a text rule with no supporting
development evidence would be exactly the kind of title-specific special
case this task explicitly forbids.

## 4. Exact root cause of D4-0415

**Listing**: "Team Rocket's Nidoking ex 233/182 Sv10 Destined Rivals SIR Holo Full Art Auto", target collector number `233`. Human class: `OTHER_MISMATCH`. Row's recorded structural fields: `single_card_or_lot=SINGLE_CARD`, `raw_or_graded=RAW`, `card_or_sealed_nonshcard=CARD`, all consistency fields blank — i.e. the reviewer's own "why NOT the target" selection produced no taxonomy override at all, which is exactly what the review UI's catch-all `OTHER` reason yields.

Number, set, and variant all check out (`233` matches, "Destined Rivals" matches, treatment matches). The only remaining textual evidence is the title's own trailing word: **"Auto"** — the standard TCG-market abbreviation for an on-card/sticker **autograph**. DEVELOPMENT contains **zero** rows matching any auto/autograph/signed/signature/inscription terminology (confirmed by direct search, not assumed) — this is a real gap in the existing product-object ontology, not a fit to any known example.

**Conclusion**: the most defensible interpretation, converging from (a) the taxonomy-exhausting `OTHER_MISMATCH` classification, (b) the literal, unambiguous "Auto" token, and (c) the complete absence of any competing explanation in the row's own structural fields, is that this listing is an autographed/altered copy — a materially different instrument from a standard raw card, which the existing product-object ontology (graded / lot / sealed / accessory) had no category for at all. Epistemic honesty note: the review UI does not capture a free-text reason for `OTHER`, so this conclusion rests on convergent evidence, not a literal reviewer note.

## 5. Development analogs

- Roaring Moon ex: 6 development rows, all showing the correct `162/131` numbering, 2 gold `EXACT_TARGET_MATCH` — direct proof the number itself is not the defect (see `ebay_d3_v5_development_study.json:roaring_moon_number_consistency_audit`).
- Autograph/signed terminology: 0 development rows match (see `ebay_d3_v5_development_study.json:autograph_terminology_audit`) — Guard 4 is new ontology, not a tuned fit.

## 6. V5 rules

`backend/scripts/ebay_d3_matcher_v5.py` wraps v4 (imported, never copied) and adds exactly one new guard:

**Guard 4 — altered/autograph detection** (`ALTERED_OR_AUTOGRAPH_GUARD_VERSION`): `\bauto(?:s|graph(?:ed|s)?)?\b|\bsigned\b|\bsignature\b|\bartist[- ]signed\b|\binscri(?:bed|ption)\b`, word-boundaried (rejects "automatic" as a substring false-positive), with a narrow documented escape hatch for `auto draft/complete/checklist` phrasing. Fires only on an already-accepted (non-REJECTED) v4 result → `REJECTED` / `ALTERED_OR_AUTOGRAPHED_V5`. Downgrade-only: never touches a v4 `REJECTED` result, never upgrades anything.

**No rule was added for D4-0375** (see §3) — this is a deliberate, documented non-fix, not an omission.

## 7. V4 vs V5 development metrics (strict DEVELOPMENT partition, 450 rows)

| Metric | v4 | v5 | Delta |
|---|---|---|---|
| Accepted (HIGH) | 194 | 194 | 0 |
| Precision | 100.0% | 100.0% | 0 |
| Recall | 70.04% | 70.04% | 0 |
| Card coverage | 58/70 | 58/70 | 0 |
| Catastrophic HIGH total | 0 | 0 | 0 |
| Newly-rejected legitimate listings | — | — | **0** |
| Autograph-term development rows | 0 | 0 | (guard never fires on real dev data, as expected) |

## 8. Legitimate coverage impact

**Zero.** No development listing legitimately labeled `EXACT_TARGET_MATCH`
was newly rejected by Guard 4 (`newly_rejected_legitimate_count: 0`). The
guard's real-world cost, if any, would only be paid on listings that
genuinely contain autograph/signed terminology, and legitimate raw single
cards essentially never carry that language.

## 9. V5 freeze manifest

```json
{
  "matcher_version": "index_fair_value_ebay_d3_v5",
  "matcher_fingerprint": "93301e5da1cf8129896993f12cfec2b66c5c887d679cb6f0755785c884581c69",
  "matcher_source_sha256": "90618933c6767ec318ae039e4684f0f2050ed0105335ef00c05b39ea3e89f90a",
  "development_corpus_fingerprint": "30420853d50f1e1c70655b5607cad91d680385f24ab18e558d999fe4454a9ccf",
  "validation_pass_result": "NOT_ELIGIBLE_ALREADY_CONSUMED_BY_V4",
  "v4_blind_cohort_status": "CONSUMED_HISTORICAL_DIAGNOSTIC_ONLY",
  "logic_frozen": true,
  "production_authority": false,
  "certified_against_new_blind": false
}
```
Full manifest: `backend/artifacts/index_fair_value/ebay_d3_v5_freeze_manifest.json`. No code/threshold change has occurred since this freeze.

## 10. Historical post-hoc diagnostic (clearly non-certifying)

Ran ONCE, after freeze, against the now-consumed 420-row V4 cohort — reported as `HISTORICAL_POST_HOC_DIAGNOSTIC`, `certifying: false`:

| | v5 on consumed V4 cohort |
|---|---|
| Accepted precision | 0.99539171 |
| Wilson 95% lower | 0.97436303 |
| Card coverage | 0.81428571 |
| Catastrophic false accepts | **1** (down from 2) |
| D4-0375 still a false accept? | **Yes** (exactly as predicted in §3 — no text rule existed to catch it) |
| D4-0415 still a false accept? | **No** — resolved by Guard 4 |
| New errors introduced | **0** |

This exactly confirms the root-cause analysis: the fixable failure was
fixed, the genuinely unfixable (image-only) one persists, and nothing new
broke. Per the task's rule, **this result does not certify v5 and did not
trigger any further v5 revision** — no code changed after this diagnostic ran.

## 11. New blind capture calls

**140 Browse requests, 140/140 successful, 0 failed** (E1 collector, 3-tier
allocation tier-1+tier-2, full 70-card cohort, `run_id a7532fd7290044e1ba311c1c6fa4fa64`). Per the task's explicit statistical note, the cohort size was **not** inflated to compensate for V4's errors — an 8,796-listing raw capture at the same ~140-request budget as V4's capture.

## 12. Duplicate/relist exclusions

| | Count |
|---|---|
| New raw evidence captured | 8,796 |
| Excluded — exact historical item ID (D2/D3 gold + **V4's 420-row blind queue**) | 1,766 |
| Excluded — likely relist (content fingerprint) | 22 |
| Eligible after dedup | 7,008 |

`HISTORICAL_FILES` for v5's capture explicitly includes
`ebay_d3_v4_fresh_blind_queue.csv` in addition to every file v4's capture
already excluded — verified by test and by direct comparison: the new v5
queue's 417 `listing_item_id`s are fully disjoint from the V4 queue's 420.

## 13. New blind row count

**417 rows** (target was ~420/6-per-card; a small number of cards had fewer
than 6 eligible listings remaining after the doubled historical-exclusion
set — not adjusted upward, per the task's explicit instruction not to
inflate the cohort).

## 14. Target-card coverage

**70/70 cards represented** in the new v5 cohort.

## 15. Reviewer protocol

`SINGLE_REVIEWER_BLIND`, honestly declared in `ebay_d3_v5_fresh_blind_manifest.json` (`reviewer_b_exists: false`). `labels_exist: false`, `labels_frozen: false` — **no labeling has occurred yet**, and none was performed by this task.

## 16. Tests

```
22 passed  -- test_ebay_d3_matcher_v5.py (new)
85 passed  -- test_ebay_d3_v5_blind_review_server.py (new; V5-specific artifacts, EXPECTED_ROW_COUNT=417)
8 passed   -- test_ebay_d3_v5_remediation.py (new)
463 passed -- full backend/tests/unit/scripts -k "ebay or fair_value" (one stale assertion in
              test_certify_ebay_d3_v4_fresh_blind.py fixed -- it hardcoded "the real V4 cohort
              is unlabeled," which stopped being true once real certification genuinely ran;
              replaced with a check that the tool never fabricates a result, whatever the
              current real state is; no other regressions)
```

Covers all 20 required areas: explicit collector-number contradiction, valid
agreement, price/year/quantity/grade numerics never becoming false collector-
number evidence, unusual (`#N`) and promo/multi-fraction formats, the second
failure-class guard (autograph/altered) with word-boundary and escape-hatch
false-positive controls, downgrade-only behavior (v5 never upgrades a v4
rejection, never exceeds v4's confidence), no listing-ID/title-literal
special case in the executable guard code (only the docstring documents
provenance), v4's own decision tree left unaffected by the v5 wrapper, a
deterministic freeze fingerprint that changes under mutation, previous-V4-
blind-item exclusion (both via the exclusion-list constant and a direct
disjointness check against the real captured files), the shared relist-
fingerprint heuristic, a matcher-field-free new queue, and an honest
single-reviewer manifest declaration.

## 17. Confirmation E3 remains blocked

No eBay price was published or computed. No active-ask valuation was built.
No TCGplayer combination occurred. No public price, Set Value, simulation
input, market snapshot, ranking, or frontend surface was touched. V4's
historical labels, cohort, and certification result were read but never
modified. The new blind cohort has zero labels — labeling and certification
remain future, out-of-scope work.

## Final decision

**`EBAY_D3_V5_FROZEN_NEW_BLIND_LABELING_REQUIRED`**

Next: label the 417-row `ebay_d3_v5_fresh_blind_queue.csv` via
`python -m backend.scripts.ebay_d3_v5_blind_review_server --reviewer Donny`
(reusing the corrected E2.1D/E2.1E undo/back/edit/review-existing UX,
entirely new V5-named artifacts), then a future E2.4-equivalent task can
build the v5 certifier and run genuine certification against these frozen
labels — locked to the same gates (precision ≥ 0.99, Wilson lower ≥ 0.98,
coverage ≥ 0.80, catastrophic == 0) with no relaxation.
