# EBAY_E2_11 — D3 TEXT-v6 Base/Parallel Treatment Evidence Remediation

**Final result:** `EBAY_D3_V6_NOT_READY_INSUFFICIENT_RECALL_RECOVERY_SAFE_SUBSET_ONLY`

D3-v6 was designed, implemented, and measured against real V4/V5/consumed-E2.9B evidence. It is **safe** (zero new false accepts, all mandated hard negatives pass, all unrelated behavior unchanged) but **not frozen**, because it recovers **zero** coverage or Wilson improvement — the higher-value fix that could have closed the gap was investigated and found **unsafe** by real corpus evidence, not merely assumed unsafe.

---

## 1. Exact V5 root cause (Phase A)

`BASE_PARALLEL_NOT_EXPLICIT` originates in `backend/scripts/ebay_d2m_matcher.py::variant_evidence()` (the base layer D3-v3/v4/v5 all inherit unchanged):

```python
TREATMENT_TERMS = { ... }          # premium-treatment phrase dictionary (SIR, IR, MHR, UR, etc.)
PARALLEL_TERMS = (
    "reverse holo", "reverse foil", "pokeball", "poke ball", "master ball",
    "masterball", "stamped", "pokemon center",
)
BASE_TREATMENTS = frozenset({"common", "uncommon", "rare"})

def variant_evidence(title, treatment):
    ...
    if treatment in BASE_TREATMENTS:
        state = "CONFLICT" if parallels else "UNRESOLVED"
    ...
```

- **Target fields inspected:** only `treatment` (the canonical target's declared treatment string).
- **Listing fields inspected:** only `title` (normalized).
- **Current treatment ontology:** `TREATMENT_TERMS` (8 premium-treatment classes) + `PARALLEL_TERMS` (8 phrases) + `BASE_TREATMENTS` (3 plain rarities).
- **Current positive markers:** for a *non-base* target, an entry in `TREATMENT_TERMS[treatment]` (e.g. "sir", "special illustration rare") found in the title.
- **Current contradiction markers:** `PARALLEL_TERMS` phrases, matched via `_phrase()` — a **strict word-boundary regex**: `(?<![a-z0-9]){phrase}(?![a-z0-9])`.
- **Why the row is capped:** for a base-treatment target, the function only ever returns `CONFLICT` or `UNRESOLVED` — **never `MATCH`** — so `classify_listing()` (in `ebay_d2m_matcher.py`, inherited unchanged through v3/v4/v5) can never call a base-treatment row's variant evidence "resolved," capping the overall `identity_state` at `MEDIUM_CONFIDENCE` (reason `BASE_PARALLEL_NOT_EXPLICIT`) even when name/number/set/language/product-object are all clean.

**The exact bug enabling the E9B-0165 hazard:** `_phrase()`'s word-boundary check requires a non-alphanumeric character immediately after the matched phrase. `"reverse holo"` matched against normalized `"...reverse holofoil..."` fails, because `"holofoil"` continues with `f` (alphanumeric) right where the boundary check needs a break. **"Reverse Holofoil" — an explicit, unambiguous parallel-print claim — is silently invisible to `PARALLEL_TERMS`,** landing the row in the same `UNRESOLVED` bucket as a genuinely blank title.

## 2. Canonical treatment authority (Phase B)

Searched for an existing inDex/database treatment-variant authority to reuse rather than build an isolated eBay-only dictionary. **`ebay_d2m_matcher.py`'s `TREATMENT_TERMS`/`PARALLEL_TERMS`/`BASE_TREATMENTS` constants ARE that authority** — they are already the single, shared source every D3 matcher version (v3 → v4 → v5) inherits unchanged, and the target `treatment` values themselves (`common`, `uncommon`, `rare`, `special_illustration_rare`, `mega_hyper_rare`, etc.) come from `ebay_pilot_cohort.json`'s canonical card records, which in turn trace to `pokemon_canonical_cards`-style identity (the same authority IMAGE-v2's canonical resolution and D3's own target fields already use — no separate database table for "variant identity" beyond this was found in the repository). **D3-v6 does not build a new dictionary** — it adds two phrases to a small, explicitly-scoped supplemental constant that lives beside, and is documented as a gap-fix for, this exact existing authority; `ebay_variant_identity_rules.json` (a separate, older D2m-era artifact) was checked and found to be about seller/listing variant *field* rules, not a treatment-name ontology, so it was not the right place to extend.

## 3. Affected-row corpus (Phase C)

Built once, from real committed evidence only (V4 queue, V5 queue, consumed E2.9B queue — all frozen, all read-only in this task): every row where the target treatment is a `BASE_TREATMENTS` member and `variant_evidence().state == "UNRESOLVED"`.

| Cohort | Rows (BASE_TREATMENTS + UNRESOLVED) | YES | NO |
|---|---|---|---|
| V4 | — | — | — |
| V5 | — | — | — |
| E2.9B | — | — | — |
| **All three combined** | **94** | **47** | **47** |

Narrowing further to rows where `BASE_PARALLEL_NOT_EXPLICIT` is the *actual* blocking reason (every other identity gate — name, number, set, language, product-object — already clean; the row's `variant` evidence is the sole obstacle):

| Cohort | Rows | YES | NO |
|---|---|---|---|
| V4 | 15 | 12 | 3 |
| V5 | 13 | 9 | 4 |
| E2.9B | 15 | 14 | 1 |
| **Total** | **43** | **35** | **8** |

All 43 rows' full fields (target identity, treatment, title, human truth, D3-v5 reason, full evidence dict) were preserved during analysis; this is the corpus the taxonomy and rule design below are built from.

## 4. Treatment-language taxonomy (Phase D), derived from the actual 43-row corpus (+ the broader 657-row holo-family scan used to find hard negatives)

| Class | Real examples found | Disposition |
|---|---|---|
| **Explicit parallel contradiction** | `"reverse holo"`, `"reverse foil"` (already recognized by D3-v5); `"reverse holofoil"`, `"reverse holographic"` (NOT recognized — the gap) | Should reject a base target |
| **Generic / non-dispositive language** | bare `"holo"`, `"holo rare"` (legacy rarity name, not necessarily a foil claim) | **Ambiguous — see Phase G finding; must NOT be treated as safe-to-promote nor as a contradiction** |
| **Target-supportive language** | none observed in the corpus — sellers essentially never write "non-holo"/"base" for a plain common/uncommon | N/A in practice |
| **No treatment evidence at all** | e.g. `"Team Rocket's Giovanni 204/217 Uncommon Ascended Heroes Pokemon Near Mint"` | **The originally-hypothesized "safe to promote" class — see Phase G, this is NOT safe** |
| **Unrelated lot/marketing language mistaken for "no evidence"** | `"...Buy 3 Get 2 Free"` (no holo word, but a bundle offer D3-v5's lot-detector currently misses) | A separate, unaddressed gap — flagged, not fixed in this task |

## 5. Hard-negative evidence (Phase G) — the decisive finding

All 8 NO rows sharing the exact `BASE_PARALLEL_NOT_EXPLICIT` reason, across all three cohorts, were inspected individually against their **human-supplied structural label fields** (not just the title text):

| Row | Cohort | Title | Human-flagged field |
|---|---|---|---|
| D4-0230 | V4 | "Arbok 101/162 Temporal Forces Pokemon TCG Common **Reverse Holofoil** NM" | `variant_treatment=INCONSISTENT` |
| D4-0271 | V4 | "2024 Scarlet & Violet Series - Temporal Forces Bronzor Common #68" | `variant_treatment=INCONSISTENT` |
| D4-0405 | V4 | "Coalossal 95/162 - Temporal Forces Pokémon TCG" | `variant_treatment=INCONSISTENT` |
| D5-0166 | V5 | "Lt. Surge's Bargain [MEG - 120/132] Uncommon **Reverse Holofoil** NM Mega Evolution" | `variant_treatment=INCONSISTENT` |
| D5-0225 | V5 | "Pokemon Arbok 101/162 Temporal Forces **Reverse Holofoil**" | `variant_treatment=INCONSISTENT` |
| D5-0268 | V5 | "**Holo** Bronzor 68/162 Temporal Forces MINT Condition" | `variant_treatment=INCONSISTENT` |
| D5-0402 | V5 | "Pokemon Coalossal Uncommon SV05: Temporal Forces 095/162 NM - Buy 3 Get 2 Free" | `variant_treatment=INCONSISTENT` |
| **E9B-0165** | **E2.9B** | "Lt. Surge's Bargain 120/132 Mega Evolution **Reverse Holofoil** Pokemon (MP-NM)" | `variant_treatment=INCONSISTENT` |

**Every single one of these 8 rows is a real, human-confirmed wrong-variant listing** (`variant_treatment=INCONSISTENT` — not lot, not graded, not sealed, not a number/set/language issue). This is the ground truth the design must respect. Splitting them:

- **4 rows** (`D4-0230`, `D5-0166`, `D5-0225`, `E9B-0165`) contain the explicit phrase "Reverse Holofoil" — these are exactly the `PARALLEL_TERMS` boundary-matching gap identified in Phase A. **Safely fixable.**
- **3 rows** (`D4-0271`, `D4-0405`, `D5-0402`) contain **zero** treatment/parallel/lot language of any kind in the title — textually indistinguishable from a genuine true-positive blank-title row (compare `D4-0271`: *"2024 Scarlet & Violet Series - Temporal Forces Bronzor Common #68"* against the genuinely-correct `E9B-0396`: *"Coalossal 095/162 Uncommon Temporal Forces Pokemon Near Mint"* — structurally identical "clean title" pattern, opposite ground truth). **This proves the originally-hypothesized fix — "promote to HIGH_CONFIDENCE when no treatment language is present" — is unsafe**: no text-only rule can distinguish these from the 35 genuine true positives in the same bucket.
- **1 row** (`D5-0268`) contains only the bare word "Holo" and is a confirmed wrong-variant NO. This directly falsifies "bare Holo is always safe" — it is genuinely ambiguous, exactly as the task's critical safety finding warned, just discovered from the *opposite* direction (a NO row with bare Holo, not only the two YES rows already known).

## 6. E9B-0165 analysis

Covered above (row 1 of the hard-negative table) — the fresh blind's own instance of the exact `PARALLEL_TERMS` boundary gap. IMAGE-v2 independently returns `MATCH` on this row (target rank 1, similarity 0.836), confirming the image layer does not catch this either — this was purely a text-layer gap.

## 7. Generic-Holo true-positive analysis

Two genuinely correct (`human=YES`) rows in the E2.9B corpus contain generic "Holo" language: `E9B-0084`/`E9B-0087`/`E9B-0088` (Dhelmise, "…- Holo", target treatment `common`) and `E9B-0175` (Victini, "…BWR Holo Rare…", target treatment `rare`). Combined with `D5-0268` (Section 5) — a confirmed wrong-variant NO row containing only bare "Holo" — this establishes that **bare "Holo"/"Holo Rare" is a genuinely ambiguous signal for a base-treatment target**: sometimes an inaccurate/generic seller descriptor on an otherwise-correct base card, sometimes an accurate description of an actual holo-parallel copy of a card whose target print is non-holo. **D3-v6 does not attempt to resolve this ambiguity** — these rows simply stay at their current, correct `MEDIUM_CONFIDENCE` (neither rejected nor promoted), which fully satisfies the task's Phase G requirement ("must not be rejected merely for containing Holo") without needing to promote them.

## 8. D3-v6 rule (Phase F)

`backend/scripts/ebay_d3_matcher_v6.py` — a thin, purely-defensive wrapper around unmodified, unchanged D3-v5:

```
IF v5's identity_state == MEDIUM_CONFIDENCE AND reason == BASE_PARALLEL_NOT_EXPLICIT:
    IF title contains "reverse holofoil" OR "reverse holographic" (normalized substring):
        DOWNGRADE to REJECTED, reason WRONG_VARIANT_V6_EXPLICIT_PARALLEL_SUPPLEMENTAL
    ELSE:
        pass through v5's result unchanged (no promotion attempted)
ELSE:
    pass through v5's result completely unchanged
```

This implements exactly the "explicit contradictory parallel evidence → preserve rejection, never promote" branch of the task's Phase F design. The "explicit target-consistent treatment evidence → allow promotion" and "neutral/non-dispositive → allow promotion only if evidence supports it" branches were investigated (Sections 4, 5, 7) and **found unsupported by real evidence** — no case of genuine target-supportive language was found, and neutral/non-dispositive language (bare Holo) was shown ambiguous, not safe. D3-v6 therefore implements only the branch the evidence actually supports.

## 9. V5 vs V6 development metrics (Phase H) — measured, not estimated

`backend/scripts/run_ebay_d3_v6_development_metrics.py`, run against the real V4, V5, and consumed E2.9B queues:

| Cohort | Reason-code transitions | New HIGH_CONFIDENCE (recall gain) | New REJECTED |
|---|---|---|---|
| V4 | `MEDIUM_CONFIDENCE → REJECTED`: 1 | YES: 0, NO: 0 | correct NO: 1 (`D4-0230`), incorrect YES: 0 |
| V5 | `MEDIUM_CONFIDENCE → REJECTED`: 2 | YES: 0, NO: 0 | correct NO: 2 (`D5-0166`, `D5-0225`), incorrect YES: 0 |
| E2.9B | `MEDIUM_CONFIDENCE → REJECTED`: 1 | YES: 0, NO: 0 | correct NO: 1 (`E9B-0165`), incorrect YES: 0 |
| **Total** | **4** | **0 / 0** | **4 correct, 0 incorrect** |

## 10. New false accepts

**Zero**, across all three cohorts — verified directly (Section 9) and re-confirmed independently by re-running the full IMAGE-v2 + COMBINED-IDENTITY-v2 stack with D3-v6 in place of D3-v5 (Section 14-16): the accepted-row set is byte-identical to the D3-v5 baseline in every cohort, because D3-v6 only ever moves rows *between two states that were already ineligible* (`MEDIUM_CONFIDENCE` → `REJECTED`, both mapped to non-acceptance by `COMBINED-IDENTITY-v2`'s `combine()`).

## 11. Cards recovered

**Zero.** D3-v6 creates zero new `HIGH_CONFIDENCE` rows (Section 9), so it cannot recover any card coverage — confirmed directly in Section 14-16's combined diagnostic (54/70 unchanged for E2.9B).

## 12. Accepted rows recovered

**Zero**, same reason — E2.9B's `accepted_count` stays at 185 under the combined stack with D3-v6 (Section 16).

## 13. Freeze fingerprint

**Not applicable — D3-v6 was not frozen** (Phase J's gate condition 5 is not met; see Section 17/20). `rule_fingerprint()` is implemented and deterministic (`93301e5d...` v5 base folded into a v6-specific hash), but no `ebay_d3_v6_freeze_manifest.json` was written in this task.

## 14. V4 post-hoc combined diagnostic (D3-v6 + unchanged IMAGE-v2 + unchanged COMBINED-v2)

| Metric | Value |
|---|---|
| Accepted count | 203 |
| True accepts | 203 |
| False accepts | 0 |
| Precision | 1.0 |
| Wilson lower | 0.98143 |
| Card coverage | 56/70 = 0.80 |
| Catastrophic | 0 |

Identical to the pre-existing E2.9A historical result — D3-v6 changes nothing for V4 (its one affected row was already NO/non-accepted).

## 15. V5 post-hoc combined diagnostic

| Metric | Value |
|---|---|
| Accepted count | 206 |
| True accepts | 206 |
| False accepts | 0 |
| Precision | 1.0 |
| Wilson lower | 0.98169 |
| Card coverage | 56/70 = 0.80 |
| Catastrophic | 0 |

Identical to the pre-existing E2.9A historical result, for the same reason.

## 16. E2.9B post-hoc combined diagnostic (the actual target cohort)

| Metric | Value |
|---|---|
| Accepted count | **185** (unchanged from E2.9C) |
| True accepts | 185 |
| False accepts | 0 |
| Precision | 1.0 |
| Wilson lower | **0.97966** (unchanged — still FAILS ≥0.98) |
| Card coverage | **54/70 = 0.7714** (unchanged — still FAILS ≥0.80) |
| Catastrophic | 0 |

Verified byte-identical to the original E2.9C certification result (`accepted_count`, `distinct_cards_covered`, and the Wilson lower bound all match exactly) by direct test assertion, not by argument alone.

## 17. Four-gate diagnostic results

| Gate | V4 | V5 | E2.9B |
|---|---|---|---|
| Precision ≥ 0.99 | PASS | PASS | PASS |
| Wilson lower ≥ 0.98 | PASS | PASS | **FAIL** |
| Coverage ≥ 0.80 | PASS | PASS | **FAIL** |
| Catastrophic = 0 | PASS | PASS | PASS |

V4 and V5 already passed all four gates historically (this was known from E2.9A) and D3-v6 does not change that. **E2.9B — the genuinely independent fresh-blind test this whole remediation effort was measured against — still fails two of four gates, unchanged.**

## 18. Is a new blind capture justified?

**No.** Per the task's own Phase J rule, freeze condition 5 ("post-hoc combined metrics plausibly clear precision ≥0.99, Wilson ≥0.98, coverage ≥0.80, catastrophic=0") is not met for E2.9B. D3-v6 is not frozen, so per the standing rule (a changed policy may never certify on the cohort used to design it, and only a frozen version is eligible for a new blind capture decision at all) — no new blind cohort should be captured on the basis of this task's output.

## 19. Tests

`backend/tests/unit/scripts/test_ebay_d3_matcher_v6.py` — 27 tests, all passing, covering all 24 required areas (several map to more than one test): base/parallel safe-case non-promotion, explicit Reverse Holo (already-working v5 path), explicit Reverse Holofoil (the actual fix), RH abbreviation correctly NOT treated as explicit (deliberately conservative), generic-Holo legitimate case not rejected, set/target-conditioned semantics, ambiguity remains capped, other-reason-code pass-through, wrong-number/set/graded/lot/sealed/autograph all unaffected, the real `E9B-0165` regression, three real V4/V5 hard negatives, no image-module dependency (source-scanned), D3-v5 immutability (git-diff-based), deterministic fingerprint, confirmation no freeze manifest was written, prospective-diagnostic non-certifying labeling, no production-writes source scan, and — most importantly — two tests asserting the **real, measured** development-metrics and prospective-diagnostic artifacts directly (zero new false accepts, zero new true positives, E2.9B numbers byte-identical to the original certification).

```
python -m pytest backend/tests/unit/scripts/test_ebay_d3_matcher_v6.py -q
27 passed

python -m pytest backend/tests/unit/scripts/test_ebay*.py -q
667 passed, 1 failed (pre-existing, unrelated CRLF byte-hash artifact,
already documented in E2.9/E2.9C reports, reproduces unchanged from HEAD)
```

## 20. Next step

The dominant coverage-recovery hypothesis from E2.10 (promote blank-treatment-language base rows) is now **disproven by real evidence**, not merely unattempted — 3 of 8 real hard negatives are textually indistinguishable from true positives. Closing the actual coverage/Wilson gap safely likely requires evidence D3-v6 (a pure text-layer change) structurally cannot use — e.g. eBay item-specific "aspects"/condition fields beyond the free-text title (if available and not yet consumed), or accepting that this specific recall class is not safely recoverable from title text alone and must remain a permanent coverage ceiling for text-only identity. Any future attempt should independently re-derive the corpus (Section 3 method) against fresh evidence rather than assume this report's 43-row snapshot is exhaustive. The safe supplemental-parallel-term fix in `ebay_d3_matcher_v6.py` is available to adopt at will as a zero-risk quality improvement (it only ever prevents a wrong-variant listing from lingering at `MEDIUM_CONFIDENCE`) independent of whether further recall work continues.

---

## Final result

**`EBAY_D3_V6_NOT_READY_INSUFFICIENT_RECALL_RECOVERY_SAFE_SUBSET_ONLY`**

D3-v6 is real, implemented, and verified safe against the full development corpus and every mandated hard negative (E9B-0165 included) — zero new false accepts, zero unrelated behavior changes, D3-v5 untouched. It is not frozen because it recovers zero coverage or Wilson improvement: the only remediation that could have closed E2.9B's gap (promoting blank-treatment-language rows) was investigated using real corpus evidence and found unsafe, not merely deferred. No new blind cohort is justified on this basis.
