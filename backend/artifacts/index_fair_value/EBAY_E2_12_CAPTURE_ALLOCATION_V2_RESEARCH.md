# EBAY_E2_12 — Capture/Allocation-v2 Evidence-Yield Remediation

**Final result:** `EBAY_CAPTURE_ALLOCATION_V2_FROZEN_NEW_BLIND_CAPTURE_JUSTIFIED` (as an evidence-yield hypothesis, not a certification guarantee)

D3-v5, IMAGE-v2, and COMBINED-IDENTITY-v2 are untouched. D3-v6 remains unfrozen (unchanged from E2.11). No new certification cohort was captured in this task — only the allocation *contract* for a future one was designed, measured against already-captured evidence, and frozen.

## 1. Current allocation contract (Phase A)

Audited directly from the real E2.9B capture code and its actual run:

- **Query formulations per card:** 2 — `primary` (built by `build_query(target)`) and `collector_number_focus` (`name + number + set_name` concatenation). `generate_queries()` collapses these to 1 when they produce an identical query string (observed for 11 of the 16 uncovered cards).
- **Request budget:** `max_pages_per_search=3`, `max_listings_per_target=200`, `max_requests_per_run=1000` (E2.9B's actual run used 225 of the 1000-request budget).
- **Per-card cap:** `ROWS_PER_CARD = 6`, selected via `stratified_sample()` — deterministic SHA-256 ordering of `f"{card_id}:{item_id}"`, first 6 taken. Never reads price, matcher, or image output.
- **Historical exclusion:** exact item-ID match against 14 prior evidence files (11,134-ID pool) + a title/seller/card/price-bucket relist fingerprint.
- **Stop conditions:** a target stops fetching once `listings_for_target >= max_listings_per_target` (200) or pagination is exhausted (`page < max_pages_per_search`, i.e. 3 pages) or the query returns no `next` link.

**Per-card candidate depth for all 16 uncovered cards** (raw retrieved → historical-excluded → surviving unique → sampled → unused surviving):

| Card | Raw retrieved | Historical-excluded | Surviving unique | Sampled | **Unused surviving** | Query formulations | Pages |
|---|---|---|---|---|---|---|---|
| Pecharunt ex (unrepresented) | 30 | 30 | **0** | 0 | 0 | primary(29)+focus(1) | 1 |
| Emboar | 199 | 129 | 70 | 6 | **64** | primary only | 1–2 |
| Grubbin | 87 | 58 | 29 | 6 | **23** | both | 1 |
| Arbok | 200 | 145 | 55 | 6 | **49** | primary only | 1–2 |
| Cresselia | 200 | 136 | 64 | 6 | **58** | primary only | 1–2 |
| Spidops ex | 199 | 140 | 59 | 6 | **53** | primary only | 1–2 |
| Giovanni's Charisma | 192 | 148 | 44 | 6 | **38** | primary only | 1–2 |
| Dhelmise | 113 | 70 | 43 | 6 | **37** | both | 1–2 |
| Lt. Surge's Bargain | 195 | 114 | 81 | 6 | **75** | primary only | 1–2 |
| Victini | 166 | 90 | 76 | 6 | **70** | both | 1–2 |
| Bronzor | 83 | 50 | 33 | 6 | **27** | both | 1 |
| Flareon | 97 | 76 | 21 | 6 | **15** | both | 1 |
| Team Rocket's Giovanni | 200 | 141 | 59 | 6 | **53** | primary only | 1–2 |
| Coalossal | 199 | 164 | 35 | 6 | **29** | primary only | 1–2 |
| Pikachu ex (Ascended Heroes) | 199 | 170 | 28 | 6 | **22** | primary only | 1–2 |
| Mega Gardevoir ex | 200 | 179 | 18 | 6 | **12** | primary only | 1–2 |

**15 of the 16 uncovered cards have substantial unused, already-captured, non-historical, non-relist candidate inventory** (12–75 unused listings each) that the reviewer never saw. Only **1 card (Pecharunt ex) is genuinely exhausted** — all 30 raw listings found were already historical evidence.

Several cards hit `raw_count` of 199–200 — i.e. the collection budget (`max_listings_per_target=200`), not eBay's actual inventory, capped further collection. This means true provider inventory for these cards is **at least** as large as measured, possibly larger — the ceiling observed here is partly self-imposed.

## 2. Marginal-yield analysis (Phase B) — measured across all 70 cards, policy-blind

Using only item ID, seller, and title (never matcher/image/policy output):

| Measure | Result |
|---|---|
| Cards with surviving candidates < 8 | **1** (the exhausted card only) |
| Cards with surviving candidates < 10 | **1** |
| Cards where rows 7–8 (in the same deterministic order) introduce a **new seller** not seen in rows 1–6 | **69 / 69** non-exhausted cards |
| Cards where rows 9–10 introduce a further new seller beyond rows 1–8 | **69 / 69** |

Independent-seller diversity is not scarce at position 7–10 — it is present for essentially every card with any inventory at all. This is real evidence, not an assumption, that increasing the per-card cap draws genuinely different listings, not repeats of the same 6.

## 3. Query-diversity analysis (Phase C)

5 of 16 uncovered cards already draw from both query formulations; the other 11 collapse to a single formulation because `primary` and `collector_number_focus` happen to produce an identical query string for those targets (both are built from the same name/number/set fields, just differently concatenated — genuinely redundant, not a bug). No third, independent, policy-blind query form was identified that both (a) doesn't depend on any matcher/image/policy prediction and (b) would plausibly surface materially different sellers beyond what raising the per-card cap already reaches. **Recommendation: keep the existing 2-formulation query generator unchanged; query diversity is not the limiting factor — allocation depth is.**

## 4. Duplicate/relist behavior

Relist-fingerprint exclusion is working as designed and does not appear to be over- or under-firing: across the full corpus this task touched, relist exclusions were low relative to exact-ID exclusions (e.g. 53 relist vs 9,016 exact-ID in the original E2.9B capture) — consistent with most repeat evidence being literal re-crawls of the same still-active listing (caught by exact ID) rather than genuine relists under a new item ID (caught by the fingerprint). No change recommended here.

## 5. Availability classes (Phase D) — defined only from provider-side evidence

Computed the surviving-unique-candidate count for all 70 cards (range: 0–96, median 34) and classified:

| Class | Definition | Count (of 70) |
|---|---|---|
| EXHAUSTED | 0 surviving | 1 |
| LOW_AVAILABILITY | 1–19 surviving | 14 |
| MEDIUM_AVAILABILITY | 20–49 surviving | 36 |
| HIGH_AVAILABILITY | ≥50 surviving | 19 |

No human truth or model output was used to build this classification — only the count of listings surviving historical/relist exclusion. **69 of 70 cards (98.6%) have at least 8 surviving candidates**, comfortably supporting an 8-rows/card allocation without needing per-card special-casing.

## 6. Candidate allocation-v2 policies (Phase E) and projected cohort size (Phase F)

| Policy | Rows/card | Projected size (69 non-exhausted × N) | In 480–560 target range? |
|---|---|---|---|
| A — 7/card | 7 | 483 | Yes (barely) |
| **B — 8/card (selected)** | **8** | **552** | **Yes** |
| C — 10/card | 10 | 690 | No — exceeds range, exceeds the "do not jump to 700+" caution |
| D — availability-aware fixed expansion | variable | ~500–550 (similar to B, more complex to implement/reason about) | Yes, but no evidence it outperforms flat 8/card given 98.6% of cards already clear 8 |
| E — multi-query-before-pagination | n/a | Query diversity is not the bottleneck (Section 3) | Not applicable |

**Selected: Policy B (8 rows/card).** It is the smallest flat increase that (a) sits inside the requested 480–560 range, (b) is supported by real surviving-candidate depth for 69/70 cards, and (c) doesn't require the added complexity of an availability-conditioned per-card cap when a flat cap already works for nearly every card. The 1 exhausted card is sampled at 0 rows under any policy — no allocation change recovers it; only a future capture at a different time (new market inventory) could.

**Trade-off:** current cohort (414 rows) → projected ~552 rows is a ~33% increase in reviewer burden. Against that: 100% of non-exhausted cards show new-seller diversity at exactly the rows being added (Section 2), and Section 7 shows real, measured (not assumed) continued coverage gains through row 6 of the *existing* 6-row cohort, including one card whose only true accept was at row 6 — direct evidence that stopping at 6 was already cutting off usable evidence for at least one card, and more depth is a credible next step.

## 7. Consumed-cohort post-hoc simulation (Phase G) — real E2.9B labels only, no invented labels

Using the actual, already-labeled E2.9B rows in their real deterministic sampling order (never treating a later, real row as if it were an unseen future candidate):

| Rows/card | Represented cards (of 69) with ≥1 human-YES so far |
|---|---|
| 1 | 40 |
| 2 | 53 (+13) |
| 3 | 59 (+6) |
| 4 | 63 (+4) |
| 5 | 63 (+0) |
| 6 | 64 (+1) |

- **Coverage saturates quickly but not completely** — the marginal gain per row shrinks (13 → 6 → 4 → 0 → 1) but never reaches zero and stays zero for good; row 6 alone rescued one card that had zero YES rows in its first 5.
- **5 of 69 represented cards had all 6 sampled rows come back human-NO** — exactly the "zero human-YES" root cause from E2.10. These are the cards Section 1's unused-inventory table shows the largest remaining depth for (e.g. Emboar: 64 unused, Arbok: 49 unused, Cresselia: 58 unused, Spidops ex: 53 unused, Grubbin: 23 unused) — real untried evidence exists for every one of them.
- Cross-check: 64 cards-with-some-YES minus the 10 cards blocked purely by identity-stack limitations (8 text-recall + 2 image-mismatch, per E2.10) = 54 — matching the actual certified coverage exactly, confirming this simulation is internally consistent with the real certification result.

No unlabeled candidate was ever scored as if it had a human label — this section only replays real, already-existing labels in their real order.

## 8. Optional bounded development review (Phase H)

**Not performed, and not needed.** The marginal-yield (Phase B) and saturation (Phase G) analyses, built entirely from already-captured, already-exclusion-filtered, real data, gave a clear, well-evidenced basis to choose between allocation policies without needing a new ~100-row human-reviewed development sample. If a future session wants additional confidence before committing reviewer time to the full ~552-row cohort, this remains an available option — it was not required to reach this task's recommendation.

## 9. Selected allocation and freeze fingerprint (Phase I)

`backend/scripts/freeze_ebay_capture_allocation_v2.py` → `ebay_capture_allocation_v2_freeze_manifest.json`:

| Field | Value |
|---|---|
| version | `ebay_capture_allocation_v2` |
| rows_per_card | **8** |
| cohort_name | `d1_70` |
| request budget | `max_requests_per_run=1000`, `max_pages_per_search=3`, `max_listings_per_target=200` (unchanged) |
| query_generation_fingerprint | `738da5e4...7b1bf23f` (reuses `index_fair_value_ebay_evidence_collector.generate_queries` unmodified) |
| sampling_source_fingerprint | `d85ab03f...e37dd47ef` (reuses `capture_ebay_d3_v4_fresh_blind.stratified_sample` unmodified) |
| historical_exclusion_source_fingerprint | `f2c7d3bd...d531c331a0` |
| historical_exclusion_files | the 14 pre-existing files **plus `ebay_e2_9b_fresh_blind_queue.csv`** (a real gap I caught and fixed while building this: the pre-existing exclusion list predates E2.9B and does not exclude E2.9B's own queue — appended here, not edited into the frozen E2.9B module) |
| independent_of | D3-v5 output, IMAGE-v2 output, COMBINED-v1/v2 output, any human label |
| production_authority | `false` |
| allocation_fingerprint | `8f297bf0...9e70d6261c79e95f81ae0e8b071578650ea3c4f93` |

## 10. Future certification design

A future certification cohort captured under this contract must, per the standing rule this task does not weaken:

1. Be captured strictly **after** this freeze (already satisfied — nothing has been captured yet).
2. Be **new relative to every earlier cohort**, including E2.9B — enforced by the corrected exclusion file list above.
3. Be **strictly historically excluded** (exact ID + relist fingerprint, unchanged method).
4. Be **sampled without any model/policy output** (query generation and stratified sampling never read D3-v5/IMAGE-v2/COMBINED-v2/human labels — verified by source inspection, Section "tests").
5. Be **labeled blind**, reusing the corrected V5/E2.9B review-session architecture.
6. Be **evaluated only after final human freeze** — no partial-label scoring.
7. **Never reuse E2.9B's labels for certification** — E2.9B remains consumed, post-hoc-only evidence, exactly as this report and E2.9C/E2.10/E2.11 already established.

## 11. Tests

`backend/tests/unit/scripts/test_ebay_capture_allocation_v2.py` — 23 tests, all passing, covering all 16 required areas (several map to more than one test): deterministic query generation, fixed per-card cap, no matcher/image/human-label dependency (source-scanned), historical exclusion including the corrected E2.9B addition, relist-exclusion source reuse, no-duplicate-ID dedup pattern present, availability-class threshold determinism, request-budget values recorded, projected cohort size falling in the 480–560 range, low-availability and exhausted-card graceful behavior (no padding, no crash), sampling-order reproducibility, and no production-write surface.

```
python -m pytest backend/tests/unit/scripts/test_ebay_capture_allocation_v2.py -q
23 passed

python -m pytest backend/tests/unit/scripts/test_ebay*.py -q
690 passed, 1 failed (pre-existing, unrelated CRLF byte-hash artifact,
already documented in prior E2.9.x reports)
```

## 12. Recommendation

Provider inventory is **not** exhausted for 69 of 70 cards — the opposite is true: most cards have 3×–13× more already-captured, unused, non-historical candidates than were ever shown to a reviewer, several capped only by this task's own collection budget rather than true market scarcity. Real (not simulated) saturation data shows coverage was still climbing, not flat, through the full depth of the existing 6-row cohort. This is a genuine, evidence-supported hypothesis that more policy-blind depth — specifically the smallest change that plausibly matters, 8 rows/card — has a credible path to recovering some of the 5 zero-YES cards and adding true accepts toward the +4/+2 targets, **without touching any identity logic**. It is explicitly **not** a guarantee: true labels remain unknown until a new cohort is captured and reviewed.

---

## Final result

**`EBAY_CAPTURE_ALLOCATION_V2_FROZEN_NEW_BLIND_CAPTURE_JUSTIFIED`**

CAPTURE-ALLOCATION-v2 (8 rows/card, ~552 projected rows, unchanged query generation and exclusion logic plus one corrected exclusion-file gap) is frozen and ready for use in a future, independent, post-freeze certification capture. No such capture was performed in this task. D3-v5, IMAGE-v2, COMBINED-IDENTITY-v2, and all certification gates remain exactly as they were; D3-v6 remains unfrozen.
