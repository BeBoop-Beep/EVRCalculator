# EBAY_E2_9 — Image-Veto + Tiered-Identity Coverage Recovery + Conditional New-Blind Prep

**Status label:** `EBAY_COMBINED_IDENTITY_V2_NOT_READY_CARD_COVERAGE_UNMEASURED`

**Worktree:** `D:\EVRCalculator-ebay-e2.9`, branch `feature/ebay-e2.9-image-veto-tiered-identity`, based on `aee7f131` (contains E2.5–E2.8 + PR #190; deliberately NOT synced to origin/develop's newer PR #191). All work below is uncommitted in this worktree.

D3-v5, IMAGE-v2, and D3-v5's/IMAGE-v2's frozen thresholds were **not modified**. No E3 work, no pricing, no publication, no new blind-cohort labeling was performed.

---

## 1. What EBAY_E2_9 actually measured vs. what it could not

Two data sources exist for the consumed V4/V5 cohorts:

1. `ebay_combined_identity_v1_historical_post_hoc_diagnostic.json` — a real, already-frozen **aggregated cross-tab** (`text_state × image_state × human_label → count`) produced by E2.8's one-time run of frozen D3-v5 + frozen IMAGE-v2 against the 420 (V4) / 417 (V5) consumed rows.
2. The raw per-listing queue CSVs (`ebay_d3_v4_fresh_blind_queue.csv`, `ebay_d3_v5_fresh_blind_queue.csv`) — real per-row data (listing title, canonical target fields, human label) but **no persisted per-row `image_state`**. E2.8's canonical-image resolution manifest lived in a prior session's temp scratch directory and no longer exists; it was never committed.

This means:

- Every metric that can be computed from the **aggregated** cross-tab (Sections 2–7 below) is **exact, real, measured data** — not estimated.
- Metrics that require knowing **which specific rows/cards** carry which image state (Tier-B/combined **card coverage**, the per-row forensic characterization of the 28 MISMATCH/YES rows, and the canonical-resolution audit) require re-running frozen IMAGE-v2 against real listing + canonical photos, which is a bounded but real network+ML job (identified precisely in Section 9, ~437 rows) that was **not executed in this pass**. I did not attempt a rushed reimplementation of canonical-image resolution under time pressure, because a resolution error there would silently corrupt exactly the safety numbers this task exists to protect — that would be worse than reporting the gap honestly.

Nothing below is guessed to fill that gap. Where a number could be bounded without new inference, I did so and show the bound; where it could not, it is marked `UNMEASURED`.

---

## 2. Complete V4 failure matrix (real, from the frozen E2.8 cross-tab)

420 total rows, 420 definitive (0 uncertain).

| Text state | Image state | Human | Combined state (v1) | Count |
|---|---|---|---|---|
| HIGH_CONFIDENCE | MATCH | YES | VERIFIED_MATCH | 115 |
| REJECTED | UNVERIFIED | NO | REJECTED_TEXT | 97 |
| HIGH_CONFIDENCE | UNVERIFIED | YES | TEXT_MATCH_IMAGE_UNVERIFIED | 88 |
| REJECTED | MISMATCH | NO | REJECTED_TEXT | 46 |
| REJECTED | MATCH | NO | REJECTED_TEXT | 24 |
| HIGH_CONFIDENCE | MISMATCH | YES | REJECTED_IMAGE_CONTRADICTION | 13 |
| REJECTED | UNVERIFIED | YES | REJECTED_TEXT | 11 |
| MEDIUM_CONFIDENCE | MATCH | YES | TEXT_AMBIGUOUS_NOT_PROMOTED | 9 |
| REJECTED | MATCH | YES | REJECTED_TEXT | 6 |
| MEDIUM_CONFIDENCE | UNVERIFIED | YES | TEXT_AMBIGUOUS_NOT_PROMOTED | 3 |
| MEDIUM_CONFIDENCE | MATCH | NO | TEXT_AMBIGUOUS_NOT_PROMOTED | 2 |
| AMBIGUOUS | MATCH | YES | TEXT_AMBIGUOUS_NOT_PROMOTED | 1 |
| AMBIGUOUS | UNVERIFIED | YES | TEXT_AMBIGUOUS_NOT_PROMOTED | 1 |
| REJECTED | MISMATCH | YES | REJECTED_TEXT | 1 |
| AMBIGUOUS | MISMATCH | NO | REJECTED_TEXT | 1 |
| HIGH_CONFIDENCE | MISMATCH | NO | REJECTED_TEXT | 1 |
| MEDIUM_CONFIDENCE | UNVERIFIED | NO | TEXT_AMBIGUOUS_NOT_PROMOTED | 1 |

Sum = 420 ✓ (verified by `test_failure_matrix_accounting_complete`).

**HIGH_CONFIDENCE row appears with human=NO exactly once, and only paired with MISMATCH** (the row above: HIGH_CONFIDENCE/MISMATCH/NO, count 1) — i.e. the text+image combination correctly rejected it. There is **no** HIGH_CONFIDENCE + MATCH + NO row and **no** HIGH_CONFIDENCE + UNVERIFIED + NO row in V4.

## 3. Complete V5 failure matrix (real, from the frozen E2.8 cross-tab)

417 total rows, 417 definitive (0 uncertain, per E2.8's coercion note — see original E2.8 report for the 1 UNCERTAIN row's handling).

| Text state | Image state | Human | Combined state (v1) | Count |
|---|---|---|---|---|
| HIGH_CONFIDENCE | MATCH | YES | VERIFIED_MATCH | 107 |
| HIGH_CONFIDENCE | UNVERIFIED | YES | TEXT_MATCH_IMAGE_UNVERIFIED | 99 |
| REJECTED | UNVERIFIED | NO | REJECTED_TEXT | 91 |
| REJECTED | MISMATCH | NO | REJECTED_TEXT | 47 |
| REJECTED | MATCH | NO | REJECTED_TEXT | 18 |
| HIGH_CONFIDENCE | MISMATCH | YES | REJECTED_IMAGE_CONTRADICTION | 15 |
| REJECTED | UNVERIFIED | YES | REJECTED_TEXT | 9 |
| MEDIUM_CONFIDENCE | MATCH | YES | TEXT_AMBIGUOUS_NOT_PROMOTED | 7 |
| REJECTED | MATCH | YES | REJECTED_TEXT | 5 |
| REJECTED | MISMATCH | YES | REJECTED_TEXT | 4 |
| MEDIUM_CONFIDENCE | MATCH | NO | TEXT_AMBIGUOUS_NOT_PROMOTED | 4 |
| HIGH_CONFIDENCE | MISMATCH | NO | REJECTED_TEXT | 3 |
| AMBIGUOUS | UNVERIFIED | YES | TEXT_AMBIGUOUS_NOT_PROMOTED | 3 |
| MEDIUM_CONFIDENCE | UNVERIFIED | YES | TEXT_AMBIGUOUS_NOT_PROMOTED | 2 |
| AMBIGUOUS | MATCH | NO | TEXT_AMBIGUOUS_NOT_PROMOTED | 1 |
| AMBIGUOUS | MATCH | YES | TEXT_AMBIGUOUS_NOT_PROMOTED | 1 |

Sum = 417 ✓. Here HIGH_CONFIDENCE + human=NO occurs 3 times, **all three paired with MISMATCH**, none with MATCH or UNVERIFIED.

## 4. THE central question, answered exactly

> How many `HIGH_CONFIDENCE text + UNVERIFIED image + human NO` rows exist?

**V4: 0. V5: 0. Combined: 0 / 837 consumed rows.**

Every HIGH_CONFIDENCE-text row that IMAGE-v2 returned UNVERIFIED for was a genuine human-YES listing, in both cohorts, with no exceptions. Every HIGH_CONFIDENCE-text human-NO row that exists (1 in V4, 3 in V5 — 4 total) was caught by IMAGE-v2 returning **MISMATCH**, not UNVERIFIED. This is the empirical basis for treating IMAGE-v2 UNVERIFIED as a distinct, eligible-but-lower-trust tier rather than a discard: in the measured historical evidence, UNVERIFIED never hid a false accept, and MISMATCH is what actually did the catching.

This does **not** prove UNVERIFIED can never hide a false accept in general — n=88+99=187 is the observed sample, not a population guarantee — but it is the strongest evidence available and directly informs the Wilson-interval-based gates below rather than a bare assumption.

## 5. Tier A metrics (identical population to v1's VERIFIED_MATCH — v2 does not change Tier A)

| | V4 | V5 |
|---|---|---|
| accepted_count | 115 | 107 |
| true_accepts | 115 | 107 |
| false_accepts | 0 | 0 |
| precision | 1.0000 | 1.0000 |
| Wilson lower (95%) | 0.9677 | 0.9653 |
| card coverage | 48/70 = 0.6857 | 44/70 = 0.6286 |
| catastrophic false accepts | 0 | 0 |

(Reproduced from the frozen E2.8 numbers; `run_ebay_combined_identity_v2_historical_final_check.py` re-derives the same values from the same source cross-tab.)

## 6. Tier B metrics (TIER_B_TEXT_VERIFIED_IMAGE_UNVERIFIED — never called image-verified)

| | V4 | V5 |
|---|---|---|
| accepted_count | 88 | 99 |
| true_accepts | 88 | 99 |
| false_accepts | 0 | 0 |
| precision | 1.0000 | 1.0000 |
| Wilson lower (95%) | 0.9582 | 0.9626 |
| card coverage | **UNMEASURED** (no per-row card join available) | **UNMEASURED** |
| catastrophic false accepts | 0 | 0 |

Tier B individually clears the ≥0.99 precision bar (1.0) but its own Wilson lower bound (0.9582 / 0.9626) does **not** individually clear ≥0.98 at this sample size — flagged separately per instructions, not hidden inside Tier A's stronger numbers.

## 7. Tier-B false-accept rows / Tier-B catastrophic analysis

**Zero** false-accept rows exist in Tier B for either cohort (Section 4). There is therefore nothing to characterize in a false-accept taxonomy, and no catastrophic Tier-B error exists in the measured data. `test_tier_b_catastrophic_metrics_zero` and `test_tier_b_precision_metrics_from_real_data` lock this in.

Because Tier B's false-accept count is 0/88 and 0/99, the question "can Tier B contain a catastrophic identity error, and is there a deterministic diagnostic that would distinguish it" is **unanswered by this data** — there is no observed catastrophic Tier-B error to test a diagnostic against. This is a limitation of the sample, not a claim that no such diagnostic is needed.

## 8. Combined candidate comparison (Candidate 0 / 1 measured; Candidate 2 not built)

| Candidate | V4 combined accepted | V4 precision | V4 Wilson lower | V5 combined accepted | V5 precision | V5 Wilson lower |
|---|---|---|---|---|---|---|
| 0 — CURRENT STRICT (= Tier A only) | 115 | 1.0000 | 0.9677 | 107 | 1.0000 | 0.9653 |
| 1 — IMAGE VETO (Tier A + Tier B) | **203** | **1.0000** | **0.9814** | **206** | **1.0000** | **0.9817** |
| 2 — SELECTIVE UNVERIFIED SALVAGE | not built — see Section 12 | | | | | |

Candidate 1 (implemented as `ebay_combined_identity_policy_v2.py`) is the only tiered candidate with real measured evidence supporting it. Its combined Wilson lower bound clears the ≥0.98 gate in **both** cohorts (0.9814, 0.9817) — precision and statistical-lower-bound gates pass. Card coverage is the only unresolved gate (Section 9).

## 9. Card coverage: bounded, not resolved

Recomputing D3-v5's frozen `classify_listing()` locally (no network, no image inference — pure, deterministic, frozen text logic) against every real queue row and cross-tabulating by `canonical_card_id` gives, for the population of all HIGH_CONFIDENCE + human-YES rows (i.e. exactly the union of what Tier A, Tier B, and the MISMATCH-rejected rows draw from):

| | V4 | V5 |
|---|---|---|
| HIGH_CONFIDENCE + human-YES row count | 216 | 221 |
| Distinct canonical cards among them | 57 | 58 |
| Upper-bound combined coverage | 57/70 = **0.8143** | 58/70 = **0.8286** |

(Cross-check: 216 = 115 + 88 + 13 and 221 = 107 + 99 + 15 — matches the frozen aggregate exactly, confirming this recomputation is consistent with the E2.8 cross-tab.)

Combined with Tier A's own known card coverage, this bounds true combined (Tier A + Tier B) card coverage as:

- **V4: between 0.6857 (48/70) and 0.8143 (57/70)**
- **V5: between 0.6286 (44/70) and 0.8286 (58/70)**

Both ranges **straddle the 0.80 gate**. The true value depends on whether the ≤9 (V4) / ≤14 (V5) cards outside Tier A's 48/44 are reached via Tier-B UNVERIFIED rows (which would count toward coverage) or exclusively via the 13/15 MISMATCH-rejected rows (which would not) — and that split requires the real per-row image state that is not available from committed artifacts. **This is not resolvable without new measurement**; I am reporting the bound rather than picking a point estimate inside it.

**Scoped follow-up** (not executed here): re-run frozen IMAGE-v2 against exactly the 216 (V4) + 221 (V5) = 437 already-identified HIGH_CONFIDENCE+YES `benchmark_row_id`s (not all 837 rows) to assign each to Tier A / Tier B / MISMATCH and compute exact card coverage. This is roughly half the original E2.8 image-inference workload and is precisely scoped by row ID; I did not run it in this pass because the canonical-image resolution logic (Pokemon TCG API lookup by name+set+number) that supported the original E2.8 run only existed as an uncommitted scratch script from a prior session, and reimplementing it under time pressure without cross-checking against the original resolution risks introducing wrong canonical images — which would corrupt the same safety numbers this task protects, silently.

## 10. The 28 IMAGE-MISMATCH false-rejection rows (Phase E) — NOT characterized this pass

13 (V4) + 15 (V5) = 28 real human-YES listings where frozen IMAGE-v2 returned MISMATCH are confirmed to exist (Section 2–3). Per-row forensic characterization (collage/crop failure/alternate art/wrong canonical image/etc., per the requested taxonomy) requires the specific `benchmark_row_id`s and their listing+canonical images, which are not preserved in any committed artifact from the original E2.8 run (only the aggregate count survives). This phase is **not completed** in this pass. It should be run together with the Section 9 follow-up, since both need the same real per-row image-state rerun; the two `benchmark_row_id` sets partially overlap (the MISMATCH rows are a subset of the 437-row HIGH_CONFIDENCE+YES population already identified).

## 11. Canonical-resolution audit (Phase F) — NOT completed, same dependency as Section 10

Verifying canonical card identity / set / collector number / treatment / canonical image URL for the 28 MISMATCH/YES rows requires knowing which 28 specific rows they are (Section 10's blocker). The raw queue CSVs do carry `target_card_name`, `target_set_name`, `target_card_number`, `target_treatment`, and `canonical_card_id` per row, so once the 28 rows are identified this audit is mechanical (cross-check each against the Pokemon TCG API record for that `canonical_card_id`) — but it was not run against an unidentified row set, to avoid guessing which 28 of the 437 candidate rows they are.

## 12. Selected policy: Candidate 1 (Image Veto / Tiered Identity)

`backend/scripts/ebay_combined_identity_policy_v2.py` implements exactly Candidate 1:

```
HIGH_CONFIDENCE + no contradiction + MATCH       -> TIER_A_IMAGE_VERIFIED
HIGH_CONFIDENCE + no contradiction + UNVERIFIED  -> TIER_B_TEXT_VERIFIED_IMAGE_UNVERIFIED
HIGH_CONFIDENCE + no contradiction + MISMATCH    -> REJECTED_IMAGE_CONTRADICTION   (hard veto, unchanged)
text contradiction present                       -> REJECTED_TEXT                  (unconditional, unchanged)
text REJECTED                                    -> REJECTED_TEXT
MEDIUM_CONFIDENCE / AMBIGUOUS                     -> TEXT_AMBIGUOUS_NOT_PROMOTED     (unchanged)
```

Candidate 2 (selective UNVERIFIED salvage using target-rank/margin diagnostics) was **not implemented**: the consumed cohorts have no persisted per-row IMAGE-v2 diagnostic join, so there is no measured evidence to support (or design) a graded Tier B. `combine()` therefore takes no diagnostic-dependent parameters (locked by `test_combine_has_no_diagnostic_dependent_kwargs`), and Tier B is a single flat tier, not stratified by confidence.

`Tier B is never labeled image-verified` — enforced by the `is_image_verified` property returning `False` for every Tier-B result, and locked by `test_tier_b_never_labeled_image_verified`.

## 13. Frozen-policy fingerprint

`backend/scripts/freeze_ebay_combined_identity_v2.py` produced `backend/artifacts/index_fair_value/ebay_combined_identity_v2_freeze_manifest.json`:

| Field | Value |
|---|---|
| policy_source_sha256 | `59e32c0a8a0310bf9a27417a78d566942f303cb543c4e3165f1ead39954abf07` |
| policy_fingerprint | `7105b731d40b121d5e74089a92c065bfc8b86795281262d275192bf6049c1018` |
| text_matcher_version / fingerprint | `index_fair_value_ebay_d3_v5` / `93301e5d...4581c69` |
| image_verifier_version / model | `ebay_image_retrieval_verifier_v2` / `facebook/dinov2-small` |
| image_verifier_fingerprint | `bf50ee1f...4c680ea1` |
| production_authority | `false` |
| shadow_research_only | `true` |
| certified_against_new_blind | `false` |

**Note on fingerprint fragility discovered during this task:** `ebay_image_retrieval_verifier.source_sha256()` hashes raw file bytes, which differ between CRLF and LF checkouts of the same committed content. Comparing this session's freshly-computed hash against the E2.7-era `ebay_image_retrieval_verifier_v2_freeze_manifest.json`'s recorded value produced a mismatch that `git status`/`git diff` confirm is **not** a real content change (the file is byte-identical to HEAD) — it is a checkout-environment artifact of the hash function itself. IMAGE-v2's immutability is verified in this task via `git diff --quiet HEAD` (content-true) rather than via `source_sha256()` equality across sessions (checkout-fragile). This is a pre-existing weakness in `source_sha256()`/`rule_fingerprint()`-style byte-hashing across this repo (an identical pattern already causes one pre-existing, unrelated test failure — `test_ebay_d2v_validation.py::test_exact_frozen_matcher_and_config_are_unchanged` — confirmed present on this branch before any E2.9 edit and out of scope to fix here).

## 14. Final V4 historical diagnostic (Phase H — run exactly once)

`backend/scripts/run_ebay_combined_identity_v2_historical_final_check.py` → `ebay_combined_identity_v2_historical_final_check.json`, V4 section:

| Metric | Tier A | Tier B | Combined |
|---|---|---|---|
| accepted_count | 115 | 88 | 203 |
| true_accepts | 115 | 88 | 203 |
| false_accepts | 0 | 0 | 0 |
| precision | 1.0000 | 1.0000 | 1.0000 |
| Wilson lower (95%) | 0.9677 | 0.9582 | **0.9814** |
| card coverage | 0.6857 | UNMEASURED | UNMEASURED (bounded 0.6857–0.8143) |
| catastrophic | 0 | 0 | 0 |

## 15. Final V5 historical diagnostic (Phase H)

| Metric | Tier A | Tier B | Combined |
|---|---|---|---|
| accepted_count | 107 | 99 | 206 |
| true_accepts | 107 | 99 | 206 |
| false_accepts | 0 | 0 | 0 |
| precision | 1.0000 | 1.0000 | 1.0000 |
| Wilson lower (95%) | 0.9653 | 0.9626 | **0.9817** |
| card coverage | 0.6286 | UNMEASURED | UNMEASURED (bounded 0.6286–0.8286) |
| catastrophic | 0 | 0 | 0 |

## 16. Four-gate comparison

| Gate | Threshold | V4 combined | V5 combined | Result |
|---|---|---|---|---|
| accepted precision | ≥ 0.99 | 1.0000 | 1.0000 | **PASS** (both) |
| Wilson lower | ≥ 0.98 | 0.9814 | 0.9817 | **PASS** (both) |
| card coverage | ≥ 0.80 | UNMEASURED (bound 0.686–0.814) | UNMEASURED (bound 0.629–0.829) | **UNMEASURED** (both) |
| catastrophic false accepts | == 0 | 0 | 0 | **PASS** (both) |
| Tier A catastrophic | == 0 | 0 | 0 | **PASS** (both) |
| Tier B catastrophic | == 0 | 0 | 0 | **PASS** (both) |

Precision, the Wilson lower bound, and both tiers' catastrophic counts all **pass, decisively, on both cohorts** — a materially stronger result than E2.8's Candidate 0 (which failed Wilson and coverage on both cohorts). Coverage is the single remaining unresolved gate, and it is unresolved rather than failing.

## 17. Was another blind cohort justified?

**No — not yet, and not for a precision reason.** Per the explicit decision-gate instructions ("do NOT make Donny label another cohort unless a frozen policy candidate meets ... on BOTH V4 and V5"), all four gates must be verifiably met. Card coverage is not verified (it is bounded, and that bound straddles the required 0.80 threshold in both cohorts), so the full gate set is not met. **No new blind cohort was captured** (Phase I was not executed), consistent with that gate result.

## 18. Conditional capture details

Not applicable — Phase I did not run. `test_no_new_blind_queue_captured` locks in that no new blind-queue artifact was produced by this task.

## 19. Tests

`backend/tests/unit/scripts/test_ebay_combined_identity_policy_v2.py` — 28 tests, all passing, covering the 21 required areas (several required-areas map to more than one parametrized test):

1. Tier A contract
2. Tier B contract
3. image mismatch remains rejection
4. text contradiction remains rejection (parametrized over image state)
5. medium/ambiguous text never promoted (parametrized over text × image state)
6. Tier B never labeled image-verified (incl. all UNVERIFIED_* variants)
7. complete failure-matrix accounting (against the real frozen cross-tab)
8. Tier-B precision metrics (real data: 0 NO rows measured)
9. Tier-B catastrophic metrics (0, real)
10. combined metrics (Tier A + Tier B accounting, precision, catastrophic)
11. target-rank diagnostic handling (`combine()` takes no diagnostic kwargs — Candidate 2 not built, verified by signature)
12. canonical resolver checks (policy v2 has no resolution logic of its own)
13. consumed cohorts treated as policy-development only (both diagnostics labeled NON_CERTIFYING)
14. policy freeze (manifest fields match live fingerprint functions)
15. no post-freeze mutation (re-hash matches frozen manifest)
16. new blind capture only when all gates pass (asserts current gate result is NOT_READY)
17. queue contains no policy output (no new blind-queue file exists)
18. D3-v5 immutable (fingerprint match)
19. IMAGE-v2 immutable (git-diff-based, not the checkout-fragile byte hash — see Section 13)
20. no pricing/publication changes (source-text scan of the policy module)
21. full ebay/fair_value suite: `python -m pytest backend/tests/unit/scripts/test_ebay*.py` → **481 passed, 1 pre-existing unrelated failure** (`test_ebay_d2v_validation.py`, same CRLF byte-hash fragility as Section 13, confirmed present against HEAD before any E2.9 edit — out of scope for this task)

```
python -m pytest backend/tests/unit/scripts/test_ebay_combined_identity_policy_v2.py -q
28 passed

python -m pytest backend/tests/unit/scripts/test_ebay*.py -q
481 passed, 1 failed (pre-existing, unrelated: test_ebay_d2v_validation.py)
```

## 20. Fair Value / Explorer blocker status

**Fair Value: BLOCKED** (not unblocked-for-next-phase). Identity evidence is materially stronger than E2.8's (precision and Wilson gates now pass combined, on both cohorts), but the coverage gate — the same category of gate that blocked E2.8 — remains unresolved, not passed. E3 (source-estimate/price-weighting logic) should not begin until either (a) the Section 9 follow-up measurement resolves coverage above 0.80 on both cohorts, or (b) a deliberate decision is made that partial coverage below 0.80 is acceptable for E3's purposes — which this task was not asked to decide.

**Market Explorer dependent valuation: BLOCKED**, same reason, no independent blocker.

---

## Final result

**`EBAY_COMBINED_IDENTITY_V2_NOT_READY_CARD_COVERAGE_UNMEASURED`**

COMBINED-IDENTITY-v2 is frozen and its precision/Wilson/catastrophic gates pass decisively on both consumed historical cohorts — a real, measured improvement over v1. It is not certified ready because combined card coverage, the fourth required gate, is honestly unmeasured (bounded between roughly 0.63–0.81 for V4 and 0.63–0.83 for V5) rather than verified ≥0.80, due to a real, identified, but unexecuted data gap (Section 9). No new blind cohort should be captured, and none was, until that specific measurement is made.
