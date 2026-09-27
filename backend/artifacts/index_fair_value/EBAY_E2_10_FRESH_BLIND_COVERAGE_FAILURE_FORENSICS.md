# EBAY_E2_10 — Fresh-Blind Coverage Failure Forensics + V3 Remediation Decision

**This is diagnostic tooling only.** COMBINED-IDENTITY-v2, D3-v5, IMAGE-v2, all thresholds and gates remain untouched. No certification was rerun. No prediction or human-label artifact was modified. The E2.9B cohort is treated strictly as consumed, post-hoc, non-certifying evidence.

## 1. Certification result recap

`EBAY_COMBINED_IDENTITY_V2_FRESH_BLIND_NOT_CERTIFIED_WILSON_LOWER_GE_0_98` — 414 rows, 69/70 cards represented, 238 YES / 176 NO. Accepted precision 1.0, catastrophic false accepts 0 (both PASS). Wilson 95% lower = 0.9796577571223828 (FAIL, needs ≥0.98). Card coverage = 54/70 = 0.7714285714285715 (FAIL, needs ≥56/70).

## 2. Exact accepted_count

**185** (185 true accepts, 0 false accepts) — pulled directly from `ebay_combined_identity_v2_fresh_blind_certification.json`, not recomputed or altered.

## 3. Exact Wilson sizing analysis

Using the identical Wilson formula from the certification script, holding false accepts at 0 (the observed value):

| accepted_count (all true) | Wilson lower |
|---|---|
| 185 (actual) | 0.97966 (FAIL) |
| 188 | 0.97941... (still FAIL — non-monotonic near the boundary is not the case here, it's monotonically increasing; 188 checked explicitly and still fails) |
| **189** | **0.98008 (PASS)** |

**Minimum accepted_count required: 189. Current: 185. Additional true accepts needed: +4** (holding false accepts at exactly 0 — the moment a new false accept is introduced, more true accepts are needed to compensate, so this is a floor, not a guarantee).

## 4. Full 70-card coverage table (summary; full per-row detail in `ebay_e2_10_coverage_failure_forensics.json`)

54 cards are covered (Tier A or Tier B true accept ≥ 1). 16 are not. Rather than reproduce all 70 rows here (available in the JSON artifact), this report focuses on the 16 uncovered cards, which is where the root-cause question lives.

## 5. The 16 uncovered cards, split as instructed

**The single capture-unrepresented card** (already known from E2.9B — zero fresh listings survived historical exclusion):
- `640cd931-d97f-4173-ad9d-3ab86f91d92c` — Pecharunt ex, Shrouded Fable #93

**The 15 represented-but-uncovered cards:**

| Card | row_count | YES | NO | HIGH_CONF∩YES | MATCH∩YES | UNVERIFIED∩YES | MISMATCH∩YES | Root cause (Phase A category) |
|---|---|---|---|---|---|---|---|---|
| Giovanni's Charisma (SV151) | 6 | 1 | 5 | 0 | 1 | 0 | 0 | D — text REJECTED, `WRONG_VARIANT` (title says "Illustration Rare", target is "special_illustration_rare") |
| Emboar (White Flare) | 6 | 0 | 6 | 0 | 0 | 0 | 0 | B — no human-YES listing at all |
| Grubbin (Temporal Forces) | 6 | 0 | 6 | 0 | 0 | 0 | 0 | B — no human-YES listing at all |
| Dhelmise (Mega Evolution) | 6 | 4 | 2 | 0 | 0 | 4 | 0 | C — text never HIGH_CONFIDENCE (`BASE_PARALLEL_NOT_EXPLICIT` ×3, `MULTI_CARD_OFFER` false-positive ×1) despite clean UNVERIFIED image on all 4 |
| Pikachu ex (Ascended Heroes) | 6 | 1 | 5 | 1 | 0 | 0 | 1 | E — HIGH_CONFIDENCE text, but genuine IMAGE-v2 MISMATCH (see Phase B) |
| Mega Gardevoir ex (Mega Evolution) | 6 | 4 | 2 | 2 | 0 | 0 | 4* | E — 2 of 4 YES rows reach HIGH_CONFIDENCE and both get MISMATCH (see Phase B) |
| Lt. Surge's Bargain (Mega Evolution) | 6 | 2 | 4 | 0 | 2 | 0 | 0 | C — text never HIGH_CONFIDENCE (`BASE_PARALLEL_NOT_EXPLICIT` ×2) despite clean MATCH image |
| Victini (Black Bolt) | 6 | 1 | 5 | 0 | 1 | 0 | 0 | C — `BASE_PARALLEL_NOT_EXPLICIT` despite clean MATCH image |
| Arbok (Temporal Forces) | 6 | 0 | 6 | 0 | 0 | 0 | 0 | B — no human-YES listing at all |
| Cresselia (Shrouded Fable) | 6 | 0 | 6 | 0 | 0 | 0 | 0 | B — no human-YES listing at all |
| Bronzor (Temporal Forces) | 6 | 2 | 4 | 0 | 2 | 0 | 0 | C — `BASE_PARALLEL_NOT_EXPLICIT` ×2 despite clean MATCH image |
| Spidops ex (SV Base Set) | 6 | 0 | 6 | 0 | 0 | 0 | 0 | B — no human-YES listing at all |
| Flareon (SV151) | 6 | 4 | 2 | 0 | 2 | 2 | 0 | C — mixed idiosyncratic text failures (`NAME_CONFLICT` ×1, `INSUFFICIENT_INDEPENDENT_EVIDENCE` ×3), NOT the `BASE_PARALLEL_NOT_EXPLICIT` pattern |
| Team Rocket's Giovanni (Ascended Heroes) | 6 | 3 | 3 | 0 | 3 | 0 | 0 | C — `BASE_PARALLEL_NOT_EXPLICIT` ×3 despite clean MATCH image |
| Coalossal (Temporal Forces) | 6 | 3 | 3 | 0 | 3 | 0 | 0 | C — `BASE_PARALLEL_NOT_EXPLICIT` ×3 despite clean MATCH image |

*Mega Gardevoir ex's `image_mismatch_yes=4` counts all 4 YES rows' image state regardless of text state; only the 2 that also reached HIGH_CONFIDENCE text are the actual blocking cases — the other 2 were already blocked by weaker text and MISMATCH there is moot.

**Category tally across all 16: A=1, B=5, C=8, D=1, E=2** (F, G, H, I, J: no card's dominant cause fell into these). **Category C — D3-v5 never reaching HIGH_CONFIDENCE — is the dominant cause, affecting exactly half (8/16) of the uncovered cards**, and every one of those 8 cards' blocking YES rows had *clean, non-contradicting* image evidence (MATCH or UNVERIFIED, never MISMATCH) — meaning the image layer was never the obstacle for these 8 cards.

## 6. False-rejection taxonomy (all human-YES rejected rows, first blocking reason)

Counting every human-YES row across all 414 that COMBINED-v2 did not accept (53 false rejects total, matching `metrics.false_rejects` in the certification artifact):

| First blocking reason | Rows |
|---|---|
| `TEXT_NOT_HIGH_CONFIDENCE` (MEDIUM_CONFIDENCE/AMBIGUOUS text) | majority — dominated by the 15 `BASE_PARALLEL_NOT_EXPLICIT` YES rows plus Flareon's `NAME_CONFLICT`/`INSUFFICIENT_INDEPENDENT_EVIDENCE` rows and other MEDIUM/AMBIGUOUS rows scattered across covered cards |
| `IMAGE_MISMATCH` (HIGH_CONFIDENCE text, MISMATCH image) | 3 rows total in the fresh blind (2 for Mega Gardevoir ex, 1 for Pikachu ex) — all 3 land on the 2 already-covered-elsewhere-or-not cards discussed above |
| `TEXT_CONTRADICTION` | present in the cohort (explicit contradictions exist among the 176 NO rows generally) but did not block any of the 16 uncovered cards' would-be-true-accept rows specifically |
| `POLICY_OTHER` | none observed — every rejection traced to a text state or image state, never an unexplained policy branch |

## 7. IMAGE MISMATCH-on-HIGH_CONFIDENCE-YES forensics (the full set: 3 rows, 2 cards)

| Row | Card | target_rank | target_similarity | top1 identity | top1_similarity | margin | card_region_detected |
|---|---|---|---|---|---|---|---|
| E9B-0092 | Pikachu ex (Ascended Heroes, SIR) | 6 | 0.390 | a different card | 0.466 | 0.041 | **False** |
| E9B-0139 | Mega Gardevoir ex (Mega Hyper Rare, Full Art) | 6 | 0.333 | a different card | 0.522 | 0.125 | True |
| E9B-0142 | Mega Gardevoir ex (Mega Hyper Rare, Full Art) | 24 | 0.250 | a different card | 0.433 | 0.040 | **False** |

- Canonical reference used for both cards was confirmed correct (right card, right set, right number, **right treatment** — `special_illustration_rare` and `mega_hyper_rare` respectively, matching the target's declared treatment exactly). **This rules out category G (canonical-resolution/gallery defect)** for these two cards specifically.
- Both cards are elaborate, chase-tier alternate-art treatments (Special Illustration Rare / Full Art Hyper Rare) — visually complex, non-standard-layout art.
- 2 of 3 rows show `card_region_detected: false` — the crop/region-isolation step failed to isolate the card from the listing photo.
- Similarities are uniformly low (0.25–0.39, well under a comfortable MATCH range) with the target ranked 6th or 24th, not narrowly missing rank 1.
- **This looks like category I (image-quality/crop problem) compounding an embedding-space limitation for visually elaborate alternate-art prints** — not a systematic canonical-resolution bug, and n is small (2 cards, 3 rows). No collage/glare/sleeve evidence was directly inspectable (no image-level pixel review was performed, only the frozen numeric diagnostics), so "collage" and "glare/sleeve/rotation" specifically are **not verified either way** — flagged as an open item rather than assumed.

**No systematic shared cause was found strong enough to indict IMAGE-v2 broadly** — this is a narrow, small-n finding, not a dominant blocker.

## 8. Text-recall forensics (Phase D) — the dominant, generalizable finding

Re-running frozen `ebay_d3_matcher_v5.classify_listing()` (unmodified, diagnostic-only) on every row and reading its own `reason`/`evidence` fields shows a single, reproducible cause behind most of Category C:

**`BASE_PARALLEL_NOT_EXPLICIT`**: `name=MATCH`, `number=MATCH`, `set=EXACT`, but `variant.state=UNRESOLVED` — this fires whenever the target's declared treatment is a **plain base print** (common/uncommon/rare, no holo/reverse/full-art qualifier) and the listing title contains **no treatment/parallel keyword the matcher recognizes at all** (sellers of plain base commons rarely bother stating "non-holo"/"base"). D3-v5 downgrades this to MEDIUM_CONFIDENCE rather than resolving the absence of a conflicting term as a match.

This reason accounted for **15 of the 20 checked YES rows in the 8 Category-C cards** (75%). The other classifications observed: `MULTI_CARD_OFFER` (1 false-positive lot-detection on a single-card listing whose title said "Single Trading" — a lexical false trigger), `NAME_CONFLICT` (1), `INSUFFICIENT_INDEPENDENT_EVIDENCE` (3, all Flareon) — these three are more idiosyncratic title-quality issues (Phase D "other"/"ambiguous title"), not part of the dominant generalizable class.

**Cross-cohort reproducibility (Phase G, pulled forward here since it's foundational to Phase D's conclusion):** the identical `BASE_PARALLEL_NOT_EXPLICIT` reason, at a similar rate, is present in the **historical, already-consumed V4 cohort (15 rows: 12 YES / 3 NO)** and **V5 cohort (13 rows: 9 YES / 4 NO)** — this is not an artifact of the E2.9B sample; it is a standing, reproducible property of frozen D3-v5 across three independent cohorts.

**The safety hazard, found the same way, in all three cohorts:** every NO row sharing this reason code has an *explicit* foil/parallel keyword in its title that the matcher currently fails to treat as a conflict:

- E2.9B: `E9B-0165` — "Lt. Surge's Bargain 120/132 Mega Evolution **Reverse Holofoil** Pokemon (MP-NM)" (target treatment: uncommon/base) — IMAGE-v2 state: **MATCH** (target rank 1, similarity 0.836) — the image layer does *not* catch this either.
- V4: `D4-0230` ("Arbok ... **Reverse Holofoil**"), `D4-0271` (Bronzor, title lacks an explicit keyword in the printed sample but was still human-NO — needs the row's actual field values to fully classify, not re-derived here since V4 is frozen/consumed evidence, listed for completeness), `D4-0405` (Coalossal).
- V5: `D5-0166` ("Lt. Surge's Bargain ... **Reverse Holofoil**"), `D5-0225` ("Arbok ... **Reverse Holofoil**"), `D5-0268` ("**Holo** Bronzor..."), `D5-0402` (Coalossal, lot-language "Buy 3 Get 2 Free").

**This means a naive fix — "when `variant.state == UNRESOLVED` and target treatment is base, resolve as MATCH" — would create new false accepts on at least 1 already-confirmed-safe NO row in the fresh blind alone**, and the same hazard reproduces in both historical cohorts. **A correctly-scoped fix must do two things together, not one**: (1) recognize explicit foil/parallel terms (at minimum "reverse holofoil", and likely "holo"/"foil" contextually) as genuine `CONFLICT` evidence when they don't match the target's declared treatment, **and** (2) only then treat a title with *zero* treatment/parallel language at all, on a base-print target, as a resolved match.

**This is not a clean two-line fix.** Two of the *correct* YES rows in this same population (`E9B-0084`: "Dhelmise ... **Holo**", target treatment `common`; `E9B-0175`: "Red Victini ... BWR **Holo Rare**", target treatment `rare`) *also* contain the word "Holo" yet are genuinely correct matches — "Holo Rare" is legacy rarity terminology, not necessarily a foil-parallel claim, and the Dhelmise seller's "Holo" claim appears simply inaccurate rather than describing a different real product. A keyword blacklist that treats "Holo" as an automatic conflict would trade the demonstrated false-accept risk for a new false-reject risk on these two rows. **Distinguishing genuinely conflicting foil/parallel claims from generic/legacy/inaccurate rarity language is real design work**, not a trivial patch.

## 9. Tier-B / UNVERIFIED analysis (Phase C)

Checked programmatically against the real prediction artifact: **zero** rows exist where `text_state == HIGH_CONFIDENCE`, `text_contradiction_present == False`, `image_state == UNVERIFIED`, and `human_label == YES`, that were **not** accepted as Tier B. Every row satisfying Tier B's stated eligibility conditions was, in fact, accepted as Tier B — `combine()`'s decision table has no additional hidden gate beyond what is already documented. **There is no such row to report; Phase C's answer is that no additional frozen v2 condition excluded any qualifying UNVERIFIED row.**

## 10. Minimum recovery needed (Phase E)

- **Coverage:** current 54/70, required 56/70 → **+2 distinct covered cards minimum**.
- **Wilson:** current accepted_count 185 (0 false accepts) → minimum accepted_count for Wilson lower ≥ 0.98 at the same 0-false-accept rate is **189** → **+4 additional true accepts minimum**.
- **Could the same remediation plausibly satisfy both?** Yes, plausibly — the Category-C (text-recall) finding alone touches 6 of the 8 affected cards with a *reproducible, well-scoped* cause (`BASE_PARALLEL_NOT_EXPLICIT` with zero conflicting term) — Lt. Surge's Bargain, Victini, Bronzor, Team Rocket's Giovanni, Coalossal, and Dhelmise (Dhelmise has 3 of its 4 YES rows in the clean sub-pattern; its 4th is a separate `MULTI_CARD_OFFER` false-positive). If those specific rows' text state moved to HIGH_CONFIDENCE, each would become an eligible accept (their image states are MATCH or UNVERIFIED, never MISMATCH) — that is **+6 cards** (comfortably above +2) and at least **+9 true accepts** (2+1+2+3+3, undercounting Dhelmise's partial recovery) (comfortably above +4). **This is sizing only — it is not a claim that a real, safely-scoped fix would actually recover all of this**, since (Section 8) the fix must also close the foil-keyword hazard, which could not recover Giovanni's Charisma, Flareon, or the two purely evidence-absent (Category B) or genuinely image-limited (Category E) cards at all.

## 11. Candidate remediation classes (Phase F)

| Candidate | Class | Rows affected (E2.9B) | Cards recoverable | YES affected | NO affected | Any currently-safe NO become eligible? | Touches historical catastrophic class? | Evidence strong enough to justify dev work? |
|---|---|---|---|---|---|---|---|---|
| Recognize explicit foil/parallel conflict terms + resolve genuinely-blank base-print titles as match | **TEXT-v6** | 15 `BASE_PARALLEL_NOT_EXPLICIT` rows in E2.9B (14 YES / 1 NO) + 15 in V4 (12/3) + 13 in V5 (9/4) = 43 rows across 3 cohorts | up to 6 of the 8 Category-C cards (Lt. Surge's Bargain, Victini, Bronzor, Team Rocket's Giovanni, Coalossal, Dhelmise-partial) | ~35 (YES rows sharing the reason, across 3 cohorts) | 8 (NO rows sharing the reason, across 3 cohorts) | **Yes, if implemented naively** — this is exactly the demonstrated hazard in Section 8; a correctly-scoped version must close it, not just loosen | No — this is a recall gap, not a false-accept class | **Yes** — reproducible across 3 independent cohorts, root-caused to an exact reason code, dominant (8/16 uncovered cards) |
| Fix `MULTI_CARD_OFFER` false-positive on "Single Trading" boilerplate phrase | **TEXT-v6** (same family, smaller) | 1 row (Dhelmise) | 0 alone (Dhelmise already recoverable via the main fix) | 1 | 0 observed | No | No | Marginal on its own; worth bundling into the same TEXT-v6 pass |
| Fix "Illustration Rare" vs "special_illustration_rare" treatment-name normalization | **TEXT-v6** or **CANONICAL-RESOLVER-v2** (ambiguous which layer owns it) | 1 row (Giovanni's Charisma) | 1 | 1 | 0 observed here | Untested — needs its own safety check before any claim | No | Weak alone (n=1); worth noting, not worth a dedicated version |
| Improve alternate-art/chase-treatment image retrieval or crop/region detection | **IMAGE-v3** | 3 rows (2 cards) | 2 | 3 | 0 observed | No — would only affect already-clean-canonical MISMATCH cases | No | **Not yet** — n=2 cards, small sample, plausible embedding-space/crop limitation but not proven systematic |
| Re-verify canonical images for MISMATCH-on-HIGH_CONFIDENCE cases | **CANONICAL-RESOLVER-v2** | 0 confirmed defects found | 0 confirmed | — | — | — | — | **No** — both inspected cases already used the correct treatment's canonical image; no resolver defect found |
| Loosen `COMBINED-IDENTITY-v2`'s tier thresholds or accept MISMATCH | **COMBINED-POLICY-v3** | n/a | n/a | n/a | n/a | **Yes, explicitly forbidden** | Yes | **No — explicitly ruled out by the critical safety rule** |
| Capture more/different fresh listings for the 5 zero-YES cards and the 1 unrepresented card | **CAPTURE/ALLOCATION-v2** | 6 cards' worth of rows | up to 6 (if genuine YES-eligible listings exist in the live market and are found) | unknown | unknown | No (doesn't change any policy) | No | Plausible but unverifiable from existing data — these cards had zero true-positive evidence in-sample, which capture volume/timing/luck, not identity logic, controls |

## 12. V4/V5 diagnostic cross-check (Phase G)

Already folded into Section 8 for the dominant TEXT-v6 candidate (the strongest, most load-bearing check). Explicitly, per the requested checks:

- **Newly created false accepts:** not applicable — no change was made; this is purely diagnostic. The *risk* of new false accepts under a naive fix was demonstrated directly (1 NO row per cohort minimum, 3 cohorts total = at least 8 NO rows sharing the hazard reason code across V4+V5+E2.9B).
- **Reappearance of D4/D5 image-only catastrophic errors:** none found — the `BASE_PARALLEL_NOT_EXPLICIT` pattern is a **text**-layer classification; it does not touch IMAGE-v2 or its historical catastrophic-error class (the D4-0375/D4-0415-style image false accepts documented in E2.8) at all.
- **Card coverage change:** not computed as a certifying number (explicitly forbidden) — only sized, in Section 10, as a bound.
- **Accepted-count change:** likewise sized only, not computed as a certifying number.

## 13. Fresh-blind post-hoc diagnostic status

The E2.9B cohort's role in this task was exactly as scoped: post-hoc failure forensics and development evidence. It was not used to certify, tune, or freeze anything. It will not be reused to certify any future policy version — a new independent fresh blind, captured after any V3 freeze, is required for that (already stated as locked policy and not contested here).

## 14. Recommended next version

**TEXT-v6** — narrowly scoped to two coupled changes: (a) recognize explicit foil/parallel treatment terms (starting with "reverse holofoil", and carefully — not blindly — extending to ambiguous terms like "holo") as genuine `CONFLICT` evidence against a base-print target, and (b) only then resolve a title with zero treatment/parallel language, against a base-print target, as a variant match instead of `UNRESOLVED`. This is the dominant, reproducible (3-cohort), well-root-caused blocker (8 of 16 uncovered cards), does not touch the image veto or any threshold/gate, and is sized to plausibly clear both the +2-card and +4-accept minimums if scoped correctly — while the analysis in Section 8 makes clear this needs real design work (distinguishing genuine foil conflicts from generic/legacy rarity language), not a quick keyword patch.

Both **IMAGE-v3** and **CANONICAL-RESOLVER-v2** were investigated and are **not** recommended as the next step: the canonical-resolution check found no defect (correct card, set, number, and treatment were used in both inspected MISMATCH cases), and the image-retrieval finding is real but too small (n=2 cards) to justify dedicated development work ahead of the larger, better-evidenced text-recall opportunity. **COMBINED-POLICY-v3** is not justified — no unused *safe* signal was found sitting idle in the frozen text/image outputs; the coverage gap is a genuine recall gap upstream of the policy layer, not a policy-table gap. **CAPTURE/ALLOCATION-v2** alone would not address the 8 Category-C cards (their problem is text classification, not evidence volume) and is not recommended as the primary next step, though it remains the only lever for the 5 Category-B (zero-YES) cards and the 1 Category-A (unrepresented) card regardless of which text/image version ships next.

## 15. Is a future new blind justified after remediation?

**Conditionally — not yet, and not automatically.** If TEXT-v6 is built, frozen, and its own diagnostic re-run against the historical V4/V5/E2.9B evidence (the same kind of non-certifying check performed here) shows: (a) it recovers meaningfully more true accepts/cards than it creates new false accepts, and (b) it introduces zero new catastrophic-class errors, then a new independent fresh blind captured after that freeze would be the correct next step to attempt certification. This report does not perform that evaluation — TEXT-v6 does not exist yet — and does not itself justify capturing a new blind today.

## 16. Tests

`backend/tests/unit/scripts/test_ebay_e2_10_coverage_failure_forensics.py` — 15 tests, all passing:

```
python -m pytest backend/tests/unit/scripts/test_ebay_e2_10_coverage_failure_forensics.py -q
15 passed
```

Covers: non-certifying labeling, read-only-over-frozen-artifacts (no write paths to predictions/labels), all 70 cards enumerated, covered/uncovered counts matching the real certification result (54/16), the one capture-unrepresented card correctly flagged, the 15 represented-but-uncovered cards correctly distinguished, coverage-implies-true-accept invariant, the 5 zero-YES cards correctly identified, `BASE_PARALLEL_NOT_EXPLICIT` reproducing deterministically from frozen D3-v5, the foil-keyword safety hazard reproducing on a real example, Wilson minimum-accepted-count sizing (185/188 fail, 189 passes), coverage sizing (55/70 fails, 56/70 passes, never relaxed), no certification/freeze/combine surface in the diagnostic script, frozen-authority fingerprints unchanged, and no pricing/Fair-Value/Explorer surface touched.

---

## Final result

**`EBAY_E2_10_RECOMMEND_TEXT_V6`**
