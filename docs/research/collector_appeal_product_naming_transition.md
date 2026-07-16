# Collector Appeal: two metrics, one product name

**Status:** research note. **No public rename or migration is authorized.**
Nothing in this document has been implemented against a public field, API
response, or frontend contract.

## The collision in one line

`collector_appeal_score` — the field that ships today — is **Pure/Universal
Desirability**. The metric we now *call* Collector Appeal in research (**CA7**)
is a different construct that produces different numbers. Both currently want the
name "Collector Appeal".

## What the public metric actually is

The shipping field is fed from Pure Desirability. From
`backend/desirability/opening_desirability_presenter.py`:

```python
_first_present(row, "collector_appeal_score", "pure_desirability_score")
```

So the public "Collector Appeal":

- is **D** — Universal Set Desirability v3, a roster-quality measure;
- asks *"how desirable are the Pokemon in this set?"*;
- contains **no structural component whatsoever** — no accessibility, no
  scarcity, no pack model, no dual-path structure;
- is consumed by RIP at 10% and rendered on the set detail page.

The name "Collector Appeal" was applied to it as a **display label**. The
underlying construct never changed to match the label, and the label was never
narrowed to match the construct.

## What CA7 is

CA7 = `D + 0.50 * P * (1 - D)`, where **P** is Dual-Path Depth: the
share-weighted degree to which a set's desirable subjects offer *both* a
reachable printing *and* an elite chase.

CA7 asks a strictly larger question: *"how appealing is this set to open?"* —
roster quality **plus** the structure of how you get at it.

## Why both cannot keep the name

They are not two implementations of one idea. They **disagree numerically on real
sets**:

Measured on the current dry run (`collector_appeal_production_dry_run.json`):

| Set | D — public "Collector Appeal" | P | CA7 |
|---|---|---|---|
| Shrouded Fable | 0.5107 | 0.2337 | **0.5679** |
| Scarlet and Violet Base Set | 0.7560 | 0.3340 | **0.7968** |
| Ascended Heroes | 0.9548 | 0.2714 | **0.9609** |

The two agree only where `P = 0`. Every set with dual-path structure is scored
differently by the two definitions — under one name.

Three concrete failures if the name is shared:

1. **Ambiguity becomes permanent on first read.** Once any consumer stores,
   caches, ranks, or screenshots a "Collector Appeal" number, there is no way to
   recover which definition produced it. The data does not carry the distinction.
2. **Silent redefinition looks like a data change.** Pointing the existing field
   at CA7 would move every set's score with no schema change, no version bump,
   and no visible cause. Users would read it as the market moving.
3. **Two different rankings, one column.** RIP ranks on D. A leaderboard mixing
   D-derived and CA7-derived rows would compare sets scored by different
   constructs — and would look perfectly normal while doing it.

## What was done instead (this task)

CA7 is stored, if ever, as an **internal candidate under its own key**:

```json
{
  "metric_name": "collector_appeal_ca7",
  "product_status": "internal_candidate",
  "formula": "CA7"
}
```

at `diagnostics_json.collector_appeal_ca7` — never `diagnostics_json.collector_appeal`.

Unchanged and untouched:

- the `collector_appeal_score` / `collector_appeal_rank` columns;
- every API response field, including `collectorAppealScore`;
- the frontend contract;
- RIP, which still consumes Universal Desirability v3 at 10%.

`backend/tests/unit/desirability/test_collector_appeal_naming_collision.py`
fails if any of that erodes — including a test that pins the
`pure_desirability_score` fallback as a fact, so a silent redefinition of the
public field breaks the build rather than the users' trust.

## Recommended future migration (NOT authorized here)

The old metric should be renamed to what it measures:

> **Collector Appeal (public, today) → Roster Desirability**

"Roster Desirability" is accurate and self-describing: it is the desirability of
the roster, with no claim about the opening experience. This frees the
"Collector Appeal" name for CA7, which is the metric that actually answers what a
user means when they ask how appealing a set is to open.

Sequencing, for whoever picks this up:

1. Rename the public metric to **Roster Desirability** across the column, API
   field, and frontend — a pure relabelling; **no number moves**.
2. Let the rename settle, so no consumer is still holding a "Collector Appeal"
   that means D.
3. Only then promote CA7 out of `internal_candidate` and into the freed name.
4. **Do not do 1 and 3 in one release.** A release where "Collector Appeal"
   changes both its definition *and* its values, with the old name still in
   flight, is indistinguishable from a bug.

**Blocked on:** CA7 covers only 20 of the 33 RIP-consumed sets
(`collector_appeal_production_dry_run.md`). Promoting it to a public name while a
third of the ranked cohort has no value would force a fallback to D — which is
precisely the two-constructs-one-column failure this note exists to prevent.
