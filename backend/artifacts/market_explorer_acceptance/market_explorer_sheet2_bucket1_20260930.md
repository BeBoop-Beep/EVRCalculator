# Market Explorer Fix Sheet 2 — Bucket 1 database closure

Date: 2026-09-30

Production project inspected read-only: `zwxzxuuawalvwioadhmf`

Branch: `fix/market-explorer-sheet2-db-20260930`

Starting `develop`: `d318ee7b913126edec657cf8da62cdf66d621b2c`

## Outcome

The Screen defect is reproduced on the serving V2 generation
`81400ef7-dcdb-4eda-923d-381c84f5b936` (comparison date 2026-09-29).
All nine card Rarity and all six card Quick rows have 7D and 90D movement,
but have null 30D movement. Rarity Leaders consequently returns no rows and
card-filtered Momentum returns no rows; unfiltered Momentum is ten sealed
rows. The serving RPC—not the retained legacy prepared table—is authoritative
for this defect.

Root cause: `finalize_pokemon_market_explorer_surface_metrics_v2` required an
observation on the exact elapsed target. The 30D target is 2026-08-30. Card
Quick/Rarity history has neither August 29 nor August 30; its latest real point
on or before target is August 28. Sealed Quick/Type has real August 29 and 30
points. The endpoint and `comparison_as_of` are September 29; August 30 is the
elapsed target; August 28 is the resolved card baseline. These dates are not
interchangeable.

The staged migration adds one auditable movement primitive and makes the V2
finalizer consume it. Fixed windows retain true elapsed targets and select the
newest observed point on or before the target, matching the existing canonical
constituent movement contract. It inserts no dates, carries no future value,
and requires an exact publication endpoint. 1Y remains null because tracking
does not reach its target; drawdowns remain computed from observed history.
No current serving generation was mutated: the fix becomes visible only after
a normal candidate build, validation, and atomic promotion.

## Screen and ranking evidence

- Eligible rows: Cards Quick 6, Cards Rarity 9, Sealed Quick 6, Sealed Type 35.
- Current nulls: 7D 0/56, 30D 15/56 (all card Quick/Rarity), 90D 0/56,
  1Y 56/56, current drawdown 0/56.
- Top Performers is capped at ten and contains both cards and sealed. Worst
  Performers is capped at ten and contains both cards and sealed.
- Current asset-specific Top calls incorrectly re-rank within the filtered
  asset (for example, global rank 5 becomes Cards rank 1). The staged RPC
  replacement ranks the eligible global universe once and filters afterward,
  preserving the original global rank and the global max-ten boundary.
- `graded` is accepted as a filter but no graded directory rows or fabricated
  empty-success data were introduced.

## Sealed identity reconciliation

The three reported counts reconcile end to end in the serving generation:

| Cohort | Catalogue/priced retail rows | V2 roster rows | Classification |
|---|---:|---:|---|
| Two-Pack Blister | 6 | 6 | `two_pack_blister` |
| Emerald set | 3 | 3 | one loose pack, two theme decks |
| Arceus set | 1 | 1 | loose booster pack |

`Prismatic Evolutions 2-Pack Blister Case` is a separately priced catalogue
row classified as `case`; it correctly appears in the Case type market and is
excluded from consumer parent markets. No product, set identity, or price was
invented. The broader current sealed parent contains 1,377 distinct priced
retail instruments. Coverage additions remain evidence-dependent: catalogue
rows without positive USD observations, unresolved set identity, or bulk
container classification must not be promoted merely to increase counts.

## Parent composition and paging

The September 29 generation reconciles exactly:

| Parent | declared total | physical rows | distinct instruments | rank range |
|---|---:|---:|---:|---:|
| Raw | 20,315 | 20,315 | 20,315 | 1–20,315 |
| Total Sealed | 1,377 | 1,377 | 1,377 | 1–1,377 |

These are audit observations, not constants. The bounded RPC requires the
caller’s generation UUID, accepts limits only through 100, orders by stored
rank, and rejects expired/cross-generation reads. Counts show no duplicate,
missing, or rank-gap evidence. No giant bootstrap load or graded placeholder
was added.

## FMA evidence contract

The FMA handoffs and `market_activity_v1.1` contract were reviewed. For
Prismatic Evolutions, the serving generation pins the same surface generation
and contains 174 roster members. Current facts are: 19 observed constituents,
155 not collected, zero window-proven constituents, supply through September
23, two supply variants, 38 listing offers, and 40 listed copies. Offers and
quantity remain distinct units. Missing is not zero.

The historical sheet snapshot’s observed sold lower bound was 488. The current
immutable serving evidence totals 1,583 observed sales over the 180-day sparse
series; this is a newer lower bound, not proof of completeness or total market
sales. Sales condition is `UNKNOWN_CONDITION`; supply is Near Mint listed and
USD. Activity is cards-only. No OHLC, inferred transaction, current-inventory,
or sealed Activity claim is made. All 174 instrument payload rows exist; the
group payload’s 19 is `observedConstituentCount`, not roster or payload count.
That response-shape ambiguity is recorded for the later backend normalization
bucket and is not changed here.

## Freshness

Production quality now marks September 30 `READY` for all 156/156 cohort sets,
while the serving surface remains September 29. Earlier
`CARD_DAILY_NOT_CURRENT` evidence therefore describes the dependency gate that
prevented advancement, not permission to relabel September 29 as September 30.
No competing writer, refresh, candidate build, or promotion was started in
this bucket. The safe next operation is the existing bounded publication path
after this migration is reviewed and applied.

## Cost, tests, and writes

The movement resolver performs bounded index-backed lookups per directory
market against the existing `(generation_id, market_key, market_date)` primary
key. A read-only `EXPLAIN (ANALYZE, BUFFERS)` of endpoint plus 30D resolution
over all 392 serving directory rows used index-only scans, returned in 611 ms
on a cold-cache sample, and wrote/dirtied zero blocks. It is publication-time
only, has a five-second statement timeout, and is materialized once inside the
finalizer. No index is required.

Repository writes are limited to the byte-identical migration pair, a focused
SQL contract unit test, this report, and the backlog. Production access in this
bucket was read-only; live writes: **none**.

## Staged objects

- `get_pokemon_market_explorer_surface_movement_v1(uuid,date)`
- replacement `finalize_pokemon_market_explorer_surface_metrics_v2(uuid,date)`
- replacement `get_pokemon_market_explorer_performance_screen_v1(text,text,uuid,integer)`
- migration `20260930230000_market_explorer_surface_canonical_movement_v1.sql`
