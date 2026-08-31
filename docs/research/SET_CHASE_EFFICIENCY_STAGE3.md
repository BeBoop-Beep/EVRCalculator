# Set-Level Chase Efficiency — Stage III: Human Ground-Truth Labeling Experiment

**Chase-universe status: `HUMAN_LABELS_NOT_YET_AVAILABLE`**

No human labels have been supplied. None were fabricated. The depth and Beat-the-Buy
decisions are **deliberately not issued** — both require re-running metrics against a
human-defined universe (Phases 12–14), which cannot happen before labels exist.
Issuing them now would be inventing findings.

| | |
|---|---|
| Branch | `fix/public-rankings-entitlement-regression` |
| Market date | 2026-08-28 |
| Cohort | 10 sets, selected for structural diversity |
| Candidate cards | **448**, one row per distinct `(set_id, card_variant_id)` |
| Schema | `chase-labeling-v1` |
| Artifacts | `docs/research/chase_labeling_v1/` |
| Production impact | **None.** No score, ranking, snapshot, migration, endpoint or schema changed. |

```
python -m backend.scripts.build_chase_labeling_packet
python -m pytest backend/tests/unit/research/test_chase_labeling.py       # 36 passed
python -m pytest backend/tests/unit/research/test_set_chase_efficiency.py \
                backend/tests/unit/research/test_beat_the_buy.py          # 95 passed
```

---

## 1. Why Stage III exists

Stage II tested four families of algorithmic chase definitions and rejected all of
them. Cross-method agreement on *which cards are chases* peaked at 0.69 Jaccard;
only 4 of 21 sets were universe-stable; K inside a single set ranged from 1 to 123.
The failure is not statistical but semantic — nothing in the data says what a chase
**is**. That circularity can only be broken from outside the data, so this stage
builds the apparatus for human labels and nothing else.

**The model may not label its own ground truth.** Every algorithmic output is
excluded from the packet by construction rather than convention.

---

## 2. The defect fixed in this continuation

The first packet build produced **806 rows over only 403 distinct printings** — every
card appeared exactly twice.

**Root cause.** `EVRInputPreparationService` populates `reverse_variant_id` on *every*
row, falling back to the **base** variant id for cards that have no separate reverse
printing. `cards_for_set` emitted a reverse row unconditionally, so those cards
produced an exact duplicate of their own base row.

**Fix, at source** (`backend/scripts/build_chase_labeling_packet.py`):

```python
reverse_variant = _text(row.get("reverse_variant_id"))
if reverse_variant and reverse_variant != base_variant:
    ...emit reverse printing...
```

**Backstop invariant** (`labeling.assert_packet_rows_are_unique`), enforced on **both**
writers: every `(set_id, card_variant_id)` must appear exactly once. Uniqueness is
per *(set, variant)*, not per variant alone, so the same variant id appearing in two
different sets remains legal.

Why the backstop matters beyond tidiness: a duplicated printing asks a human to label
the same card twice. That card would then carry double weight in the consensus,
inflate the labelled-card count, and — if the two copies were labelled differently —
manufacture a "disagreement" between a labeler and themselves that the agreement
statistics could not distinguish from a real one.

### Verification that no genuine reverse printing was lost

| Set | df rows | base | genuine reverse | echoed reverse (dropped) | emitted | distinct |
|---|---:|---:|---:|---:|---:|---:|
| Phantasmal Flames | 130 | 130 | 84 | 46 | **214** | 214 |
| Scarlet and Violet 151 | 208 | 208 | 153 | 55 | **361** | 361 |

Emitted equals `base + genuine reverse` exactly, every genuine reverse variant is
present, and the totals now reconcile with the Stage-II eligible-universe counts
(Phantasmal Flames 214, 151 361). Only the echoed self-duplicates were removed.

A second-order confirmation: no `(set_name, card_name, card_number)` appears on more
than one packet row, so a labeler is never shown two rows they cannot tell apart.

---

## 3. Labeling cohort (Phase 2)

Selected on **structural diversity**. Financial RIP rank played no part and is not
consulted anywhere in the labeling module — asserted by
`test_cohort_rationale_never_cites_financial_rip`.

| Set | Structure | Pool | Why selected |
|---|---|---:|---|
| Phantasmal Flames | hero_chase | 30 | Most concentrated set (effective EV count 1.40) and the **only** genuine price cliff ($275→$27, ratio 10.16). Algorithms already agree here, so human disagreement would falsify the labeling premise. |
| Paldean Fates | hero_chase_expensive | 42 | Second-most concentrated (2.57), $965 headline card, $23.11 pack. Largest Chase-EV-vs-BTB rank disagreement in Stage II (EV 4th, BTB 19th). |
| Scarlet and Violet 151 | unstable_expensive | 35 | Highest pack price ($29.81); **unstable** universe (0.346) with K from 1 to 35 and a Stage-II core of one card. |
| Ascended Heroes | deep_expensive_multihit | 31 | Nine-card Stage-II core, six cards over $300, multi-hit packs. Deep *and* expensive — unique in the cohort. |
| Prismatic Evolutions | godpack_unstable | 52 | God packs (up to 9 qualifying cards in one pack), highest Chase EV Return (0.408), unstable (0.333), widest value-vs-probability divergence (7.90 vs 25.33). |
| Paradox Rift | deep_cheap_unstable | 45 | Deepest pool measured (17.55) with a modest $120 top card. Largest-log-gap says K=1, ≥2×C says K=27 — a 5.7× BTB swing. |
| White Flare | adaptive_k_disagreement | 123 | Largest adaptive-K disagreement: K from 7 to 24 purely from the HHI reference pool; 123-card two-means universe. |
| Shrouded Fable | flat_curve_deep | 30 | Flattest price curve (75, 59, 58, 54, 49); highest BTB (0.263). Tests whether a flat curve has a chase line at all. |
| Pitch Black | stable_cheap | 30 | **Positive control** — most stable universe in Stage II (0.760) at a $4.75 pack. |
| Perfect Order | cheap_pack_moderate | 30 | Cheapest pack ($4.74); largest Stage-I rank mover. Tests whether a cheap pack shifts where humans draw the line. |

Coverage: hero **and** deep, cheap **and** expensive packs, stable **and** unstable
universes, with **and** without multi-hit mechanics.

---

## 4. Candidate pool (Phase 3) — recall over precision

Pool = union of four rules, deliberately over-inclusive:

* top 30 by current NM market value
* value ≥ **$10** absolute floor
* value ≥ **1×** pack-equivalent cost
* **every card selected by any Stage-II method**

The last term is not decoration. A benchmarked method whose picks were missing from
the pool would score a low recall for a reason having nothing to do with the method,
and the bias would be invisible in the results. `algorithmSelectedCoveredByPool` is
`true` for all 10 sets.

### Recall proof — the dearest excluded card is cheaper than the cheapest included one, in every set

| Set | Pool | Printings | Cheapest in pool | Dearest excluded | Headroom ratio | |
|---|---:|---:|---:|---:|---:|:--|
| Phantasmal Flames | 30 | 214 | $1.29 | $1.28 | 0.992 | PASS |
| Paldean Fates | 42 | 327 | $9.23 | $8.37 | 0.907 | PASS |
| Scarlet and Violet 151 | 35 | 361 | $9.06 | $7.81 | 0.862 | PASS |
| Ascended Heroes | 31 | 468 | $10.94 | $9.36 | 0.856 | PASS |
| Prismatic Evolutions | 52 | 448 | $10.14 | $9.71 | 0.958 | PASS |
| Paradox Rift | 45 | 428 | $7.86 | $7.11 | 0.905 | PASS |
| White Flare | 123 | 405 | $7.57 | $6.83 | 0.902 | PASS |
| Shrouded Fable | 30 | 162 | $7.45 | $5.58 | 0.749 | PASS |
| Pitch Black | 30 | 194 | $2.46 | $2.33 | 0.947 | PASS |
| Perfect Order | 30 | 202 | $1.66 | $1.61 | 0.970 | PASS |

Ratios near 1.0 (Phantasmal Flames 0.992) are expected and harmless: those sets are
pooled by the **top-30 rank rule**, so the boundary falls wherever rank 30 lands
rather than at an economic threshold. The proof required is ordinal — dearest excluded
< cheapest included — and it holds in all 10.

White Flare's 123-row pool is the deliberate cost of full recall: Stage-II's two-means
method selects 123 cards down to $7, and excluding them would make that method
unscoreable. Rows are sorted by price descending within each set so the cheap tail can
be swept quickly.

---

## 5. Blindness (Phase 4)

`PACKET_COLUMNS` is a **closed allow-list**; `assert_packet_is_blind` rejects any
column outside it and any column name matching a forbidden fragment (`hhi`,
`effective`, `chase_count`, `btb`, `beat_the_buy`, `chase_ev`, `rip`, `p95`, `p99`,
`jackpot`, `upside`, `score`, `rank`, `selected`, `universe`, `probability`, `pull`,
`recommend`, `predicted`, `algorithm`, `elbow`, `boundary`, `cluster`, `zscore`).

The labeler sees only: set, card name, card number, rarity, treatment, printing type,
current NM market price, pack price, and **value expressed in packs**. The last is a
real-world fact about the purchase — price divided by price — not a model output; a
labeler judging "is this a chase" reasonably wants to know whether a card is worth two
packs or two hundred.

**Verified on the final artifacts.** All 3,584 HTML data cells trace back to a blinded
packet field (the 21 apparent exceptions are HTML-escaped apostrophes in card names
such as `Team Rocket&#x27;s Mewtwo ex`). The only occurrence of the word "algorithm"
anywhere in the HTML is the disclosure sentence telling the labeler that no model
output is shown — which reveals nothing about which cards were selected.

---

## 6. Deliverable artifacts

| File | Rows | Purpose |
|---|---:|---|
| `chase_labeling_packet.csv` | 448 | Blinded packet, machine-readable |
| `chase_labels_template.csv` | 448 | Packet + empty `human_label`, `labeler_id`, `label_confidence`, `notes` — **the file a human fills in** |
| `chase_labeling_packet.html` | 10 sets | Self-contained review sheet, grouped by set, price-descending |
| `manifest.json` | — | Provenance, per-set pool proof, blindness and uniqueness guarantees |

Labels are **empty**. `write_label_template_csv` never writes a value into
`human_label`, and `test_template_has_label_columns_and_no_prefilled_labels` asserts it.

### How to label

Assign each card exactly one of:

* **`CORE_CHASE`** — a primary chase target of the set.
* **`EXTENDED_CHASE`** — a meaningful secondary chase; a hit you would be pleased with,
  but not a defining headline card.
* **`NOT_CHASE`** — not reasonably part of the chase pool.
* **`UNSURE`** — you cannot confidently classify it.

`label_confidence` is 1 (low), 2 (moderate) or 3 (high). `labeler_id` is required once
a label is present. **`UNSURE` is a real answer** — it is excluded from *both* targets
and analysed separately, rather than folded into either class.

---

## 7. Ground-truth targets (Phase 7)

| Target | Positive | Negative | `UNSURE` |
|---|---|---|---|
| **A — Core Chase** | `CORE_CHASE` | `EXTENDED_CHASE`, `NOT_CHASE` | excluded, inspected separately |
| **B — Meaningful Chase** | `CORE_CHASE` + `EXTENDED_CHASE` | `NOT_CHASE` | excluded, inspected separately |

Consensus across labelers is **majority with ties dropped** — a tied card is precisely
a card the humans do not agree is a chase, so breaking the tie would manufacture
agreement. A stricter `unanimous` rule is also available.

---

## 8. Multi-labeler support (Phase 6)

The schema supports 1 labeler now and more later; nothing needs to change to add them.
Once ≥2 labels exist, `agreement_report` produces raw agreement, Cohen's kappa per
pair, Fleiss' kappa at ≥3 labelers, agreement under **each binary target separately**,
and the full disputed-card list.

Reporting agreement per target matters: labelers can disagree sharply about
Core-versus-Extended while agreeing almost perfectly on chase-versus-not. Those are
different facts with different consequences for which target is publishable, and
`disputedCoreVsExtendedOnly` isolates them.

Kappa is returned as `None` — with a stated reason — when every labeler used a single
category, because expected agreement is then 1.0 and the statistic is undefined. That
is a real, reportable situation, not a divide-by-zero to paper over.

---

## 9. Benchmark framework (Phases 8–11), ready to run

`backend/research/set_chase_efficiency/benchmark.py`:

* per-method **precision, recall, F1, FPR, FNR, Jaccard, accuracy**, exact-K agreement
  and mean absolute K error
* **macro-averaged** across sets (unweighted mean of per-set scores), with pooled
  figures reported alongside so the gap is visible — sets range from 162 to 468
  printings and pooling would let the largest decide the winner
* per-set F1 standard deviation and worst-set F1, so a rule that is excellent on six
  sets and useless on four cannot hide behind its mean
* `leave_one_set_out` — refits on n−1 sets and scores the held-out one, with `fit` and
  `predict` as callbacks so the harness cannot privilege any particular rule
* `disagreement_profile` — dispute rate by price band (Phase 11)

**Anti-tautology guard:** every entry point returns `HUMAN_LABELS_NOT_YET_AVAILABLE`
and scores nothing when labels are absent. It never substitutes an algorithmic
universe for the missing human one.

### A real bug this stage's tests caught

`test_macro_average_does_not_let_the_largest_set_decide` failed on first run. F1 was
computed as the harmonic mean of precision and recall, which is **undefined whenever
precision is undefined** — and precision is undefined exactly when a rule selects
*nothing*. Such a set was dropped from the macro average entirely, so a rule that
missed every chase in a set was scored only on the sets where it happened to fire. A
rule perfect on a one-card set and useless on a 200-card set scored a macro F1 of
**1.000**.

Fixed by computing `F1 = 2TP / (2TP + FP + FN)`, which is `0.0` in that case — the
truthful answer — and undefined only when there is genuinely nothing to measure. The
same rule now scores **0.500**.

---

## 10. Verification summary

| Requirement | Result |
|---|---|
| Final row count = distinct `(set_id, card_variant_id)` | **448 = 448** |
| No genuine true reverse printing removed | **Verified** — emitted = base + genuine reverse, all genuine reverse variants present, totals reconcile with Stage-II eligible counts |
| All 10 selected sets represented | **10 / 10** |
| Permissive candidate-pool recall proof passes | **10 / 10**, all algorithm selections covered |
| Dearest excluded < cheapest included, per set | **10 / 10** |
| Packet blindness passes structurally | **PASS** — columns == allow-list; all HTML data cells traceable to blinded fields |
| No forbidden field leaks | **PASS** |
| Stage-I and Stage-II tests pass | **95 passed** |
| Stage-III labeling/benchmark tests pass | **36 passed** |
| Labels fabricated | **None** |

Three unrelated failures exist in `test_collector_appeal_v4_candidates.py`
(`collector_appeal_v4_h_only_...` promoted while the test still expects the v3
version string). They are **pre-existing and outside this work** — that module has
zero references to anything Stage III touches — and were left alone.

---

## 11. Decisions

### `HUMAN_LABELS_NOT_YET_AVAILABLE`

Correct and expected. The experiment is built, verified and ready; no human has
labelled it yet.

### Depth and Beat-the-Buy decisions: **not issued**

Both are gated on Phases 12–14, which require a human-defined universe. Stage II's
working hypotheses stand unchanged and unvalidated: depth (effective EV count)
correlated +0.92 with production `effective_chase_count` but only +0.21 with BTB,
suggesting it is a separate dimension; BTB correlated 0.68–0.997 with Chase EV Return,
suggesting it is an interpretable companion rather than an independent axis. **Neither
is a Stage-III finding.**

---

## 12. Next step

Hand `docs/research/chase_labeling_v1/chase_labels_template.csv` (or the HTML sheet)
to 1–3 human reviewers. On return:

1. `read_labels` ingests and validates, rejecting malformed rows with reasons rather
   than dropping them.
2. `agreement_report` measures whether the humans agree enough for the labels to be
   usable ground truth at all.
3. `benchmark` scores every Stage-II method against Targets A and B.
4. `leave_one_set_out` rejects any tuned rule whose held-out performance collapses.
5. Only then do Phases 12–14 (depth re-derivation, metric recomputation on the human
   universe, BTB publishing decision) become answerable.

**Financial RIP V11 remains out of scope and is not begun.**
