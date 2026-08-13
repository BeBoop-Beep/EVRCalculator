# Public Rankings Targets Payload Slimming

Follow-on to `PERFORMANCE_TARGETS_SNAPSHOT_READ_AUDIT.md`, which classified the
`/explore/rip-statistics/targets` bottleneck as **C — large JSON payload size**:
~600 ms of a ~667 ms PostgREST call is spent moving a 2.8 MB document across the DB
boundary, while SQL is 0.117 ms (48 ms with a forced detoast) and the lookup already
uses its `UNIQUE (tcg, scope)` primary key.

This pass removes three superseded public contracts from the **persisted `_latest`
Rankings artifact only**, after proving no consumer of that artifact reads them.

**Result: 2,796,342 → 1,811,726 bytes, −984,616 (−35.2%), measured in a real
publication dry-run. Zero consumer differences across 1,496 field comparisons.**

No production publication was performed — see *User publication commands*.

---

## Original payload anatomy

`ranking_payload_json`, 34 targets, `targets` = 99.7% of the document.
Top-level target keys by exact serialized bytes (174 keys per target):

| Key | Bytes | % of target bytes | Targets | Nulls |
| --- | ---: | ---: | ---: | ---: |
| `publicRipContractV7` | 586,608 | 22.38% | 34 | 0 |
| **`publicRipContractV6`** | **532,879** | **20.33%** | 34 | 0 |
| **`publicRipContractV5`** | **394,150** | **15.04%** | 34 | 0 |
| `financial_rip_v3_payload` | 297,824 | 11.36% | 34 | 12 |
| `financialRipV3` | 295,213 | 11.26% | 34 | 0 |
| `openingExperience` | 165,977 | 6.33% | 34 | 0 |
| `universalSetDesirability` | 73,205 | 2.79% | 34 | 0 |
| **`publicRipContractV4`** | **55,081** | **2.10%** | 34 | 0 |
| `rip` | 41,323 | 1.58% | 34 | 0 |
| `overallRipV7` | 23,782 | 0.91% | 34 | 0 |
| `ripCore` | 23,160 | 0.88% | 34 | 0 |
| `overallRipV6` | 22,614 | 0.86% | 34 | 0 |
| `overallRipV5` | 17,212 | 0.66% | 34 | 0 |
| `rip_core_interpretation` | 12,087 | 0.46% | 34 | 0 |
| `desirabilityCoverage` | 6,800 | 0.26% | 34 | 0 |

**V4 + V5 + V6 = 982,110 bytes = 37.47% of all target bytes.**

---

## Targets consumer map

Every runtime caller of `getRipStatisticsTargets`, and the field families it reads:

| Consumer | File | Limit | Field families read |
| --- | --- | ---: | --- |
| Rankings / Explore | `app/Explore/page.js` | 60 | identity, canonical V7 bundle, pack/profit/safety ranks+tiers, Set Value, 1D movement |
| Explore RIP Statistics | `app/Explore/rip-statistics/page.js` | 150 | as above |
| Market | `app/Market/page.js` | 60 | identity/links, rank context |
| Landing hero | `lib/landing/landingHeroServer.js` | `LANDING_TARGETS_LIMIT` | featured set identity, canonical V7 scores |
| Set route + metadata | `app/TCGs/Pokemon/Sets/[setSlug]/page.js` | 150 | `slug`/`canonical_key`/`set_id` resolution, header identity, rank context, set picker |
| Sitemap | `app/sitemap.js` | 200 | `slug` / `canonical_key` only |

**No consumer reads `publicRipContractV4/V5/V6`.** The canonical resolver
`components/explore/canonicalRipV7.mjs` states it explicitly:

> There is deliberately no third step. `rip`, `ripCore`, `overallRipV6`, `overallRipV5`
> … are all DIFFERENT MODELS, and serving one of them under a canonical label is the
> exact defect this module removes.

Its precedence is `publicRipContractV7` → (`overallRipV7` + `financialRipV3`) shape
fallback → unavailable. There is no V4/V5/V6 fallback path to lose.

---

## Legacy contracts by endpoint — the §5 question

The repo *does* use `publicRipContractV5` / `V6` at runtime. The decisive question was
whether those consumers obtain them **from this artifact**. They do not:

| Reader | Source of V5/V6 | Affected by slimming `_latest`? |
| --- | --- | --- |
| `adaptPokemonSetInsightsPayloadToExplorePayload` | `/tcgs/pokemon/sets/{id}/insights` | No |
| `adaptPokemonSetInsightsCriticalPayloadToExplorePayload` | `/tcgs/pokemon/sets/{id}/insights/critical` | No |
| `collectorAppealBreakdownSelector.mjs` | comment only — it now reads canonical V7 | No |
| `pokemon_onboarding_verification_service` | `pokemon_set_page_snapshot_latest.payload_json` | No |

**Why the set page keeps them.** `_merge_canonical_rip_contract_into_set_payload`
(`backend/scripts/pokemon_snapshot_builders.py:382`) lifts V4/V5/V6 verbatim into the
set page snapshot — but from `get_rip_statistics_targets_payload(...)` at line 1329,
which is the **live in-memory builder**, not the persisted `_latest` row. The set page
snapshot therefore keeps all three regardless of what this artifact stores.

That is the whole safety argument: **the canonical complete build is unchanged; only
the persistence projection is slimmed.**

---

## Safe removal decision

| Field | Rankings-targets consumer | Other-endpoint consumer | Decision |
| --- | --- | --- | --- |
| `publicRipContractV4` | none | set page payload (via live builder); onboarding verification reads it from the *set page* snapshot | **REMOVE from `_latest`** |
| `publicRipContractV5` | none | set Insights critical/full (via live builder) | **REMOVE from `_latest`** |
| `publicRipContractV6` | none | set Insights critical/full (via live builder) | **REMOVE from `_latest`** |

Deliberately **KEPT** in this pass (§7, §8, §22): `publicRipContractV7`,
`overallRipV7`, `financialRipV3`, `financial_rip_v3_payload`, `openingExperience`,
`universalSetDesirability`, `overallRipV5`, `overallRipV6`, `rip`, `ripCore`, and every
alias family. `financial_rip_v3_payload` vs `financialRipV3` (593 kB combined) is
**not** proven duplication — 34 targets carry the camelCase object, 22 the snake_case
one, and 0 pairs are byte-identical. It gets its own phase.

The builders `backend/desirability/public_rip_contract_v{4,5,6}.py` and the producer at
`explore_rip_statistics_service.py:1940-1947` are **untouched**.

---

## External / public contract decision

**Safe.** `/explore/rip-statistics/targets` is an internal website transport:

- Every caller is a Next.js server component in this repo (table above); there is no
  browser-side or third-party client.
- No API documentation, public endpoint documentation, or schema/version marker
  mentions `publicRipContractV4/V5/V6`. The only `.md` files referencing them are this
  repo's own audit and research notes.
- No backend test asserts them in the rankings/targets payload.

No external guarantee is broken, so a versioned slim projection was not required.

---

## Persistence boundary

`publish_explore_rip_rankings_snapshot` (`backend/scripts/pokemon_explore_rankings_publisher.py`):

```
build_explore_rankings_snapshot_row(limit)          # full canonical payload
publication_contract(row)                           # validates FULL
previous_calendar_day_payload(client, market_date)  # history read
attach_daily_rip_rank_movements(payload, previous)  # movement on FULL
attach_publication_metadata(row, snapshot)
validate_publication_payload(row, snapshot, rows)   # validates FULL
────────────────────────────────────────────────────────────────────────
latest_row = {**row, ranking_payload_json: project_latest_rankings_payload(...)}
────────────────────────────────────────────────────────────────────────
rpc publish_pokemon_public_rip_leaderboard(
    p_snapshot = snapshot,      # FULL — history unchanged
    p_rows     = history_rows,  # FULL — history unchanged
    p_latest   = latest_row)    # SLIM — the artifact the API reads
```

The projection runs **after** every validation and after movement, and applies **only**
to `p_latest`. `project_latest_rankings_payload` is non-destructive (it rebuilds dicts
rather than mutating), so the object validation and history were built from is
untouched — pinned by `test_projection_does_not_mutate_the_caller_payload`.

Publication validation is **not weakened**: `_score_contract_problems` still requires a
complete `publicRipContractV7` on every ranked target, and it runs against the full
payload. A candidate missing canonical V7 still fails.

---

## Historical publication safety

- `attach_daily_rip_rank_movements` reads only `set_id`/`id`/`target_id`,
  `overallRipV7.rank`, `financialRipV3.rank`, and `meta` version/cohort strings. It
  never reads V4/V5/V6.
- `previous_calendar_day_payload` reads
  `pokemon_public_rip_leaderboard_snapshots.payload_json`, which this change does
  **not** touch — history keeps the full document, so tomorrow's comparison is
  byte-for-byte identical to today's behaviour.
- History currently holds 14 rows, 15 MB, payloads ranging 518,615 – 2,796,448 bytes.
  Payload size already varies across publications, so the movement path already
  tolerates differently-shaped previous payloads.
- No historical rows are rewritten.

---

## Candidate size

Measured two ways:

| Source | Before | After | Saved | % |
| --- | ---: | ---: | ---: | ---: |
| Publisher dry-run (freshly built) | 2,796,342 | 1,811,726 | 984,616 | **35.2%** |
| Projection applied to the currently persisted row | 2,627,012 | 1,704,952 | 922,060 | **35.1%** |

Keys per target: **174 → 171**.

---

## Consumer parity

`frontend/.perf-audit/targets-consumer-parity.mjs` runs the real consumer modules
against the full and projected payloads and compares **models**, not raw JSON.

- Targets compared: **34**
- Fields per target: **44** → **1,496 field comparisons**
- Scenario checks: target count, ordering, sitemap URLs, landing hero model,
  `default_target`, `meta`
- **Differences: 0**

Field families covered: identity/routing (`id`, `set_id`, `target_id`, `slug`,
`canonical_key`, `name`, `era`, images), canonical bundle shape, Overall RIP /
Financial RIP / Collector Appeal (score, absolute, relative, rank, tier,
`rankedSetCount`), pack cost, EV mean/median, ROI, prob-profit, pack/profit/safety
ranks+tiers, Set Value + as-of + 7D comparison, 1D rank movement, `openingExperience`,
`universalSetDesirability`.

Two guards that make the result non-vacuous:

- Canonical resolution shape on the slim payload is **`publicRipContractV7` for all 34
  targets** — never a degraded fallback.
- **22 of 34** targets carry an available canonical Overall RIP block with ranks
  1..22, identical on both sides. (The other 12 are unranked sets, equally unranked
  before and after.)

API shape parity: exactly `publicRipContractV4/V5/V6` removed per target, **0 keys
added, 0 values changed**, `meta` and `default_target` identical.

---

## Publication dry-run

```
INFO [rankings-publish] _latest payload projection: 2796342 -> 1811726 bytes
     (-984616, -35.2%) removed=publicRipContractV4,publicRipContractV5,publicRipContractV6
INFO [dry-run] validated complete RIP publication market_date=2026-08-12 rows=22
explore rankings snapshot: publication gate decision (dry-run) [allowed_complete]
     allowed=True: batch 2026-08-12 is complete; promotion allowed
```

PASS — cohort complete (22 ranked rows), publication contract satisfied, Set Value
contract satisfied, canonical publication identity correct.

---

## Tests

| Suite | Result |
| --- | --- |
| `test_rankings_latest_payload_projection.py` (new, 8 tests) | 8 passed |
| Publisher guard, snapshot builder, publication contract, publication gate, public snapshot service, explore targets, public-read retry, onboarding verification, financial RIP V3 public contract, `tests/unit/api` | 283 passed, **1 pre-existing failure** |
| Frontend: cache identity, SEO foundation, explore shell, landing, canonical V7, public metric contract, Collector Appeal breakdown | 128 passed |
| Frontend: `explorePageServer.contract.test.js` | 8 passed, **1 pre-existing failure** |
| `npx next build` (isolated `PERF_AUDIT_DIST_DIR`) | exit 0, compiled successfully |

Both failures are pre-existing and unrelated: `test_canonical_top_chase_history_forward_fills…`
and *"getExplorePagePayload set fetch uses timeout and recoverable fallback"*. In each
case the test file and its source are unmodified at HEAD, and no frontend production
code was changed in this pass.

---

## User publication commands

**Dry-run first** (safe, writes nothing):

```bash
cd /d/EVRCalculator
./backend/.venv/Scripts/python.exe -m backend.scripts.build_pokemon_explore_rankings_snapshot --all --dry-run
```

Expect a `_latest payload projection: … -35.2%` line and
`[dry-run] validated complete RIP publication`.

**Then publish:**

```bash
cd /d/EVRCalculator
./backend/.venv/Scripts/python.exe -m backend.scripts.build_pokemon_explore_rankings_snapshot --all --commit
```

---

## Post-publication measurement plan

```bash
# optional: isolated backend for the HTTP leg
./backend/.venv/Scripts/python.exe -m uvicorn backend.api.main:app --host 127.0.0.1 --port 8010 --log-level warning

./backend/.venv/Scripts/python.exe backend/scripts/verify_rankings_payload_slimming.py http://127.0.0.1:8010 25
```

Reports publication id / market date / built-at, target count, persisted payload bytes,
a `SLIM PROJECTION APPLIED: YES/NO` assertion, `publicRipContractV7` coverage, and
same-window PostgREST / service / HTTP p50+p95 over 25 reads.

**Projection, not a measured result:** the persisted document falls 35.2%, and the audit
attributed ~600 ms of the ~667 ms PostgREST call to payload transfer over a ~67 ms fixed
floor. If transfer scales linearly, PostgREST would land near **67 + (600 × 0.648) ≈
455 ms**, i.e. roughly a 210 ms saving, with HTTP near ~600 ms. **This is arithmetic on
prior-window measurements, not a measurement.** The real number requires the published
snapshot; do not treat the above as validated until the harness has been run.

Also worth checking after publish: cold Rankings, warm Rankings, Home → Rankings,
Rankings → Set.

---

## Carry-forward reliability threads

**A. Top Chase 503 — UNRESOLVED LOAD-RELIABILITY THREAD.** 6/40 (15%)
`POKEMON_SET_TOP_CHASE_SNAPSHOT_READ_FAILED` under 40-way concurrency before the
client-side duplicate-request removal; 0/40 in two runs after. The fix was client-side
and cannot have repaired a backend read failure — halving load may simply have moved
the sample below the threshold. **Not fixed, not claimed fixed.**

**B. Pull Rates duplicate — REQUEST-LIFECYCLE FOLLOW-UP.** A genuine duplicate
reproduced on 151 in the pre-Phase-2A production build (the original "instrumentation
error" explanation was wrong). Post-Phase-2A traces show 0 duplicate request kinds, but
no dedicated lifecycle contract test pins single-request semantics. Still open.

Neither blocked this work.
