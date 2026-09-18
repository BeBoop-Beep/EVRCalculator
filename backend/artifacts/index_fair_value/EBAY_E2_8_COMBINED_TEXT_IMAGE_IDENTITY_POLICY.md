# EBAY_E2_8 — Combined Text + Image Identity Policy (COMBINED-IDENTITY-v1)

## Scope discipline

No prices published. No E3. D3-v5 untouched (called via `classify_listing()`
exactly as frozen, never reimplemented). IMAGE-v2 untouched (thresholds
imported from `ebay_image_retrieval_verifier.py`, never redefined). No new
400-row blind cohort captured. Version boundaries kept explicit throughout:
**text matcher = D3-v5**, **image verifier = IMAGE-v2**, **combined policy =
COMBINED-IDENTITY-v1** (`ebay_combined_identity_policy_v1.py`) — a small,
hand-specified decision table with no matcher/verifier logic of its own.

## 1. Gallery coverage (Critical Gallery-Coverage Rule)

IMAGE-v2's frozen 165-card E2.7 research gallery was built from 26 arbitrary
Pokemon-name families for *retrieval-method* research — it does **not**
contain inDex's actual V4/V5 benchmark target population by construction
(that was never its purpose). Running the combined policy against V4/V5
therefore required resolving each target's OWN canonical image
just-in-time from the same free canonical-image authority (Pokemon TCG
API), rather than assuming static-gallery coverage.

- **Requested target count**: 70 unique canonical cards (V4 and V5 draw
  from the identical 70-card target population).
- **Target identities present in gallery after resolution**: **70 / 70
  (100.0%)**.
- **Missing target identities**: none, in the final resolved set (a small
  number of per-cohort resolution attempts initially failed on a
  name+number query alone — e.g. ambiguous set-name matches — but every
  canonical_card_id resolved successfully through at least one cohort's
  attempt or a broadened query).
- Rows whose target could not have been resolved would have been reported
  as `UNVERIFIED_TARGET_NOT_IN_GALLERY` (implemented, tested) rather than
  silently compared against an unrelated nearest neighbor — this rule was
  exercised by the resolver's honest "not found" path during development
  and is covered by a dedicated unit test, even though it did not end up
  firing in the final historical run.

## 2. Missing-target handling

Implemented in `ebay_combined_identity_policy_v1.resolve_image_state()`:
before any retrieval call, the target's presence in the gallery is checked
explicitly; absence short-circuits to `UNVERIFIED_TARGET_NOT_IN_GALLERY`
without ever calling IMAGE-v2's `verify_by_retrieval()`. Verified by test.

## 3. Visually-indistinguishable handling

`resolve_image_state()` accepts an `indistinguishable_groups` parameter
(sets of canonical ids known to share identical or visually
inseparable artwork) and returns `UNVERIFIED_VISUALLY_INDISTINGUISHABLE`
for any target in a group of size > 1, before ever calling retrieval.

An audit of the 165-card E2.7 research gallery found **zero exact
byte-identical duplicate images** (verified by hashing every gallery
image). This is expected for the sampled "ex" cards (which generally lack
reverse-holo counterparts sharing base art) and is **not** a general claim
that no such case exists anywhere in inDex's catalog — reverse-holo/
non-reverse pairs and some reprint-vs-original pairs are a known,
documented general risk class for any image-based method, this one
included; the mechanism to cap those at `UNVERIFIED_VISUALLY_INDISTINGUISHABLE`
exists and is tested, but no live-catalog audit for such pairs was
performed in this pass (would need direct `pokemon_canonical_cards` DB
access, out of scope here).

## 4. Real-photo corpus size / composition (Phase A — reported honestly)

**No development-eligible real-listing-photo corpus with actual human
labels exists in this repository outside the two consumed V4/V5 blind
cohorts.** This was independently re-verified: every CSV under
`backend/artifacts/index_fair_value/` was scanned for a filled
label/gold-label column; only `ebay_d3_v4_fresh_blind_queue.csv` (420 rows)
and `ebay_d3_v5_fresh_blind_queue.csv` (417 rows) have any non-blank human
label at all. `ebay_gold_development.csv` (450 rows, `partition=DEVELOPMENT`)
exists but every label column is **100% blank**
(`review_status=PENDING_INDEPENDENT_HUMAN_REVIEW` for all 450 rows) — it
was never actually reviewed.

Consequently, **Phase A's "several hundred, preferably 1,000+" target was
not achievable from existing evidence**, and this task did not perform a
fresh scrape + human review to manufacture one (that would itself require
Donny's labeling time — exactly what this task's decision gate exists to
avoid spending unless justified). The only real, human-labeled listing
photos available are the 837 rows across the two consumed cohorts. Per the
task's own Phase F, those are the designated (post-hoc, non-tuning)
diagnostic corpus — so this task uses them as **exactly that and only
that**: COMBINED-IDENTITY-v1's decision table is a fixed table written
directly from the task specification (Section 7), never fit to this data,
so running it against the consumed rows is measurement, not tuning.

**Real-photo strata**: not independently inventoried by strata (sleeve,
glare, tabletop, etc.) — no metadata field in the existing evidence records
which stratum a photo belongs to, and manually re-reviewing 837 images to
classify them was outside this task's time budget. Reported honestly as
not done, rather than fabricated.

## 5. IMAGE-v2 real-photo results (Phase C)

Measured as part of the Section 7/8 combined-policy run (IMAGE-v2 itself
was not separately re-benchmarked in isolation on these 837 rows beyond
what the combined failure matrix already shows per-cell):

| Cohort | image_state=MATCH | image_state=MISMATCH | image_state=UNVERIFIED |
|---|---|---|---|
| V4 (420 rows) | 145 | 61 | 214 |
| V5 (416 definitive rows) | 145 | 65 | 206 |

(counts derived from the failure matrices in Section 8; gallery coverage
was 100%, so every `UNVERIFIED` here is IMAGE-v2's own margin/rank
decision, never a coverage gap.)

## 6. False MATCH analysis (the task's named "most important" metric)

**Zero occurrences of `HIGH_CONFIDENCE` text + `MATCH` image on a
human-`NO` row, in either cohort (0/837).** This is the exact cell that
would represent a catastrophic image-layer failure, and it is empty in
both failure matrices (Section 8). Correspondingly,
**`catastrophic_combined_false_accept_count = 0`** for both V4 and V5.

The dominant real cost is the opposite direction: `HIGH_CONFIDENCE` text +
`MISMATCH` image on a human-`YES` row — **13 (V4) + 15 (V5) = 28 rows**
where a genuinely correct listing gets rejected because IMAGE-v2 judged the
photo a mismatch. This is a coverage/recall cost, not a safety violation,
and is exactly the trade-off the task's conservative design intends
("prefer UNVERIFIED/reject over false MATCH").

## 7. Combined-policy contract (Phase D)

`ebay_combined_identity_policy_v1.combine(text_state, image_state,
text_row_fields)` implements exactly the task's target semantics:

```
text contradiction present (any field)   -> REJECTED_TEXT   (checked first, unconditionally)
TEXT REJECTED                             -> REJECTED_TEXT
TEXT MEDIUM_CONFIDENCE / AMBIGUOUS        -> TEXT_AMBIGUOUS_NOT_PROMOTED  (image never promotes weak text)
TEXT HIGH_CONFIDENCE + IMAGE MATCH        -> VERIFIED_MATCH
TEXT HIGH_CONFIDENCE + IMAGE MISMATCH     -> REJECTED_IMAGE_CONTRADICTION
TEXT HIGH_CONFIDENCE + IMAGE UNVERIFIED*  -> TEXT_MATCH_IMAGE_UNVERIFIED
  (* including UNVERIFIED_TARGET_NOT_IN_GALLERY and UNVERIFIED_VISUALLY_INDISTINGUISHABLE)
```

No branch was derived from data; every branch is the literal specification
from this task's "Target Policy to Research" and "Do Not Allow Image to
Override Text Contradiction" sections.

## 8. Development / historical combined metrics + failure matrix (Phase D/E)

**V4 (420 rows, all definitive):**

```
accepted_count: 115   true_accepts: 115   false_accepts: 0
accepted_precision: 1.0000   wilson_95_lower: 0.9677
accepted_recall: 0.4637      card_coverage: 0.6857 (48/70 cards)
catastrophic_combined_false_accepts: 0
```

**V5 (416 definitive of 417; 1 human-UNCERTAIN excluded, never coerced):**

```
accepted_count: 107   true_accepts: 107   false_accepts: 0
accepted_precision: 1.0000   wilson_95_lower: 0.9653
accepted_recall: 0.4246      card_coverage: 0.6286 (44/70 cards)
catastrophic_combined_false_accepts: 0
```

**Failure matrix (both cohorts; full detail in the diagnostic JSON), key
rows:**

| TEXT | IMAGE | HUMAN | COMBINED | V4 count | V5 count |
|---|---|---|---|---|---|
| HIGH_CONFIDENCE | MATCH | YES | VERIFIED_MATCH (correct accept) | 115 | 107 |
| HIGH_CONFIDENCE | UNVERIFIED | YES | TEXT_MATCH_IMAGE_UNVERIFIED (coverage lost) | 88 | 99 |
| HIGH_CONFIDENCE | MISMATCH | YES | REJECTED_IMAGE_CONTRADICTION (false reject) | 13 | 15 |
| HIGH_CONFIDENCE | MISMATCH | NO | REJECTED_TEXT/REJECTED_IMAGE_CONTRADICTION (correct reject) | 1 | 3 |
| HIGH_CONFIDENCE | **MATCH** | **NO** | *(catastrophic cell)* | **0** | **0** |
| REJECTED | MATCH | NO | REJECTED_TEXT (contradiction preserved) | 24 | 18 |
| REJECTED | UNVERIFIED/MISMATCH | NO | REJECTED_TEXT | 143 | 138 |
| MEDIUM_CONFIDENCE/AMBIGUOUS | MATCH | YES | TEXT_AMBIGUOUS_NOT_PROMOTED (never silently promoted) | 10 | 9 |

The one V4 row combining `HIGH_CONFIDENCE` text + `MISMATCH` image +
human-`NO` in the *contradiction-preserved* accounting (D4-0375's own row)
is caught by the **text-contradiction check** before the image branch is
even reached (its `collector_number_consistency=INCONSISTENT` field trips
`has_text_contradiction()` first) — an independent, redundant safety net on
top of the image layer for that specific historical case.

## 9. V4 historical post-hoc diagnostic

420 rows, 70 cards, gallery coverage 100%. **Zero catastrophic combined
false accepts** (down from V4's own original text-only certification
failure). Card coverage 68.6% (below the 80% diagnostic-gate line). Wilson
lower bound 0.9677 (below the strict 0.98 line, entirely because zero
observed errors at n=115 cannot mathematically clear a 0.98 lower bound —
not evidence of a precision problem).

## 10. V5 historical post-hoc diagnostic

417 rows (416 definitive, 1 UNCERTAIN preserved and excluded, never
coerced), 70 cards, gallery coverage 100%. **Zero catastrophic combined
false accepts** — critically, this means **all three of the real
certified WRONG_SET catastrophic failures (`D5-0054`, `D5-0224`,
`D5-0378`) would have been caught** by COMBINED-IDENTITY-v1 (each carries
`HIGH_CONFIDENCE` text + `MISMATCH` image, landing in
`REJECTED_IMAGE_CONTRADICTION`, per the E2.7 diagnostic already on record).
Card coverage 62.9% (below 80%). Wilson lower bound 0.9653 (below 0.98, same
small-sample-at-zero-errors caveat as V4).

## 11. Combined diagnostic gates (orientation only — non-certifying)

| Gate | Threshold | V4 observed | V5 observed | Status |
|---|---|---|---|---|
| Accepted precision | ≥ 0.99 | 1.0000 | 1.0000 | **PASS** (both) |
| Wilson 95% lower | ≥ 0.98 | 0.9677 | 0.9653 | **FAIL** (both — sample-size artifact of 0 errors) |
| Card coverage | ≥ 0.80 | 0.6857 | 0.6286 | **FAIL** (both — real recall shortfall) |
| Catastrophic false accepts | = 0 | 0 | 0 | **PASS** (both) |

These do **not** certify anything (`HISTORICAL_POST_HOC_NON_CERTIFYING`,
labeled as such in the diagnostic artifact). They are read here purely for
orientation, exactly as the task instructs.

## 12. Coverage impact

The dominant, measured cost of adding IMAGE-v2 as a safety guard is
**recall/coverage, not precision**: 187 rows across both cohorts
(88 + 99) that were genuinely correct listings (`HIGH_CONFIDENCE` text,
human-`YES`) get demoted from what would have been an accept to
`TEXT_MATCH_IMAGE_UNVERIFIED` purely because IMAGE-v2's conservative
rank/margin policy could not confirm them from a single real photo. This
drops card coverage from whatever D3-v5 alone would have achieved down to
62.9–68.6% — below the 80% production bar in both historical cohorts.

## 13. Daily runtime / cost (Phase G)

Reusing E2.6/E2.7's established, task-provided volume anchor (~200
accepted text-candidates/day; no separate raw-Browse-listings/day
telemetry exists in this repository to cite instead, and vision is
correctly gated to occur only after text filtering, never on raw Browse
results):

- Embedding + retrieval: ~50 ms/candidate (E2.7, confirmed again on this
  837-row real run — 837 real listing photos embedded well within
  the total diagnostic wall-clock) → ≈ 200 × 50 ms ≈ **10 seconds of CPU
  per day**.
- Canonical embedding cache: one-time cost per unique target card, not
  per-candidate — for the 70-card real target population, ≈ 70 embeddings
  ever (not 70/day).
- Listing-image bytes: ≈ 500 KB/candidate (hi-res-upgraded per E2.6) ×
  200/day ≈ **100 MB/day**, all free-tier bandwidth.
- All measured costs remain **negligible and within the free-cost
  constraint**, unchanged from E2.6/E2.7's conclusions on this axis — cost
  was never the blocker in this task; coverage is.

## 14. Tests

`backend/tests/unit/scripts/test_ebay_combined_identity_policy_v1.py` —
**25 tests**, all passing: target-not-in-gallery → `UNVERIFIED`,
visually-indistinguishable groups → `UNVERIFIED` (including a group-of-one
non-trigger guard), every branch of the fixed combination table
(HIGH_CONFIDENCE×MATCH/MISMATCH/each UNVERIFIED variant, REJECTED text,
MEDIUM_CONFIDENCE/AMBIGUOUS never promoted), every one of the five
text-contradiction fields individually detected, human-UNCERTAIN handling
confirmed to live outside this module (by design), full result-contract
serialization, structural guards that IMAGE-v2's thresholds and D3-v5's
internals are never redefined/reimplemented here, and no paid-provider or
pricing-module reference anywhere in the module. Full `ebay`-scoped
regression suite: **602 passed**.

## 15. Recommendation

Per Phase H's explicit five-part gate:

1. Real-photo image false MATCH rate acceptably near zero — **YES** (0/837
   catastrophic combined false accepts, on real photos, across both
   consumed cohorts).
2. Combined policy introduces zero known catastrophic error class in
   development — **YES**.
3. Historical consumed-blind diagnostic materially better than text-only —
   **YES** (text-only V5 certification failed on 3 catastrophic false
   accepts; the combined policy has zero, in both V4 and V5, including
   catching all three real failures).
4. Card coverage remains plausibly capable of ≥ 80% — **NO.** Measured
   62.9% (V5) and 68.6% (V4), both meaningfully below the bar, driven by
   187 real true-positive rows landing in `TEXT_MATCH_IMAGE_UNVERIFIED`
   rather than `VERIFIED_MATCH`.
5. CPU/runtime remains practical — **YES**.

**Criterion 4 fails, decisively and on real data, across both historical
cohorts.** Per the task's own instruction ("If those do not hold: do NOT
make Donny label another 400 listings"), a new fresh-blind certification
round is **not** recommended on this evidence. The safety story is
excellent (zero catastrophic errors is the headline result, and it
directly addresses the reason V5 certification failed) — but the coverage
cost of IMAGE-v2's current conservative retrieval margin, measured against
real photos at scale for the first time in this task, is large enough that
a fresh 400-row human-labeled certification attempt would very likely fail
the card-coverage gate again, for a different (recall, not precision)
reason.

This is **not** a defect requiring IMAGE-v2 itself to change (no threshold
was touched, and none should be, per this task's explicit no-retuning
instruction) — it is evidence that closing the coverage gap needs either
(a) a less conservative but still catastrophic-error-free margin policy
validated on a proper, larger, non-consumed development corpus (which does
not currently exist — Section 4), or (b) accepting `TEXT_MATCH_IMAGE_UNVERIFIED`
as a legitimate, separately-priced-or-flagged evidence tier rather than
requiring every real accept to also clear the image bar. Both are policy/
research decisions for a future task, not something to resolve by silently
editing IMAGE-v2.

EBAY_COMBINED_IDENTITY_V1_NOT_READY_CARD_COVERAGE_BELOW_80_PERCENT
