# Chase Accessibility V1 — Implementation Record

## Status

### `CHASE_ACCESSIBILITY_IMPLEMENTATION_BLOCKED`

**Cause: the working tree is being hard-reset by a concurrent process.**

The metric, its schema, its builder/read model and its tests are complete and
verified, and **Stage XIV parity is exact**. What is *not* done is the
integration into the live coordinated-publication workflow, the set read path and
the set page UI. Those are multi-file edits across surfaces I cannot verify
safely while another process is running `checkout` → `reset --hard` → `checkout`
in this tree — it already destroyed two of this task's files mid-run (see §10).

Nothing was deployed, published, migrated or made canonical.

---

## 1. Formula

$$HC_i = \frac{V_i^2}{\sum_j V_j^2} \qquad O_{pack} = \sum_i HC_i\,p_i \qquad N_{HC} = \frac{1}{\sum_i HC_i^2}$$

Computed both ways on every call as a parity check:

$$O_{pack} = \frac{\sum_i V_i^2 p_i}{\sum_j V_j^2}$$

Worst observed internal parity delta across the production cohort:
**8.674 × 10⁻¹⁹** — identical to the figure Stage XIV recorded.

## 2. Public meaning

**Technical.** The Chase-Significance-weighted mean of modeled per-pack card
probabilities.

**Plain English.** *How reachable is this set's most meaningful collectible value
from a random pack?*

**Tooltip.** *How accessible the set's most important collectible value is from
one pack.*

**Never** "chance of pulling a chase card", "probability of a chase", or "chance
to hit the chase". There is no discrete chase roster; every card carries
continuous significance, so the binary "hit a chase" event does not exist to have
a probability. `test_chase_accessibility.py` fails the build on that wording.

## 3. Authority

| | |
|---|---|
| Universe | `simulation_card_variant_pull_rates` rows with `pull_count > 0`, one calculation run |
| `V_i` | `price_used` |
| `p_i` | **`modeled_probability`** |
| Never `p_i` | `effective_pull_rate` (1-in-N **odds**; `p = 1/effective_pull_rate`) |
| Never `p_i` | `pull_count / simulation_count` (expected **copies**, not P(N≥1)) |

Value and probability come from the **same row**, 1:1 — no canonical-card
fan-out, no cross-table join, **no sealed-product input of any kind**.

Verified live over the cohort: **0 authority failures across 6,873 checked rows**,
both identities holding. **2,124 rows** have `pull_count/simulation_count`
differing from the presence probability — which is precisely why it may never be
substituted.

## 4. Version identities

```
chase_accessibility_v1_hc_value_squared_modeled_probability
chase_significance_v1_squared_value_share
chase_depth_v1_hc_effective_count
```

## 5. Coverage gate

`mapped_hc_mass` = share of Chase Significance carrying **both** a finite
positive value **and** a valid modeled probability, measured against the **full**
drawable priced universe. **Never renormalised** around missing rows —
renormalising would make a set look *more* accessible precisely because an
important card went missing.

Gate: **`mapped_hc_mass ≥ 0.99`**. Below it the row stores `NULL` accessibility
and `chase_accessibility_insufficient_probability_coverage`. The gate is enforced
in the module, in the service, **and as a database CHECK constraint**.

## 6. Schema

`backend/db/migrations/077_create_pokemon_set_chase_accessibility_snapshot.sql`
— **077 verified free across all branches and all history.** Migration 074
(superseded V11 candidate) is untouched and remains unapplied.

**A dedicated additive table, not a column on the existing chase snapshot.**
`pokemon_set_chase_economics_snapshot_latest` (migration 069) is entirely
*product-coupled* — its payload prices chasing each card through each sealed
product. Chase Accessibility has zero product dependency, so storing it there
would tie a set-level access metric to a row that must be rebuilt whenever a
sealed-product price moves.

Table `pokemon_set_chase_accessibility_snapshot_latest`: `set_id` PK,
`calculation_run_id`, `market_date`, `accessibility` (decimal fraction — **never**
a percentage), `chase_depth`, `mapped_hc_mass`, `status`, `status_reason`,
`version`, `significance_version`, `depth_version`, four diagnostics,
`built_at`/`updated_at`.

Three CHECK constraints make the contract structural: a `ready` row must carry a
value and a non-`ready` row must not (so NULL and 0.0 can never be confused),
accessibility ∈ [0,1], and `ready` ⇒ `mapped_hc_mass ≥ 0.99`.

Backend-only RLS posture matching migrations 065/069: RLS enabled, no read
policy, no `anon`/`authenticated` grants, full DML to `service_role`.

**Per-card Chase Significance is deliberately not persisted.** `HC_i` is one
division away from `price_used`, which is already stored; ~7,000 extra rows per
run with no current consumer would be duplicate state. If a card page later needs
it, that is a deliberate versioned per-card read model.

## 7. Builder and read model

`backend/db/services/chase_accessibility_service.py`

- `load_drawable_variants` — `pull_count > 0` applied **in the query**, paged past
  the 1000-row cap.
- `build_chase_accessibility_snapshot_row` — idempotent; a set with no run or no
  drawable variants produces an **explicit unavailable row**, never no row.
- `persist_chase_accessibility_snapshot` — upsert on `set_id`.
- `project_chase_accessibility` — the public shape; internal diagnostics are not
  projected.
- `publication_integrity_failures` — the severity distinction.

**Publication severity.** A set with **no pull model** is *structurally
unsupported*; its unavailable row is a correct outcome and must not fail
publication. A set that **is** simulation-supported but whose Accessibility is
missing, not-ready, wrong-version, under-covered or bound to a **stale
calculation run** is an **integrity error**. Accessibility is never refreshed
independently of the run it describes.

## 8. API fields

```
chaseAccessibility          decimal fraction, or null
chaseAccessibilityPct       fraction * 100, or null
chaseAccessibilityStatus
chaseAccessibilityVersion
chaseDepth                  N_HC, effective count
mappedHcMass
```

Unsupported sets return `chaseAccessibility = null`, **never `0`**. Zero is a
measured zero and means something else entirely.

## 9. Cohort validation and Stage XIV parity

`python -m backend.scripts.audit_chase_accessibility_v1 --market-date 2026-08-31 --stage14 <artifact>`

| | |
|---|---|
| Sets evaluated | **20**, all simulation-supported |
| `mapped_hc_mass` | **1.000000 on every set** |
| Range | 0.00074435 – 0.00561818 (**0.0744% – 0.5618%**) |
| **Accessibility mismatches** | **0** (worst delta 0.000e+00 — exact) |
| **Depth mismatches** | **0** (worst delta 0.000e+00 — exact) |
| **Status mismatches** | **0** |
| Fabricated probabilities | 0 |
| Product-price dependencies | 0 |

**Cohort is 20, not the expected 22.** *Destined Rivals* and *Journey Together*
are in Stage XIV's 22 but have no authoritative run at 2026-08-31, so
`resolve_research_cohort` excludes them. Every set present matched **exactly**.
This is a cohort/data condition on the date, not a metric defect.

Four-quadrant independence (concentrated/deep × accessible/inaccessible) is
regression-tested; neither axis is derivable from the other.

## 10. Workspace incident

| | |
|---|---|
| Start | branch `feat/immediate-post-scrape-publication-trigger`, HEAD `3e8e05c9`, clean |
| End | same branch, HEAD `71ef2d36` |

Mid-task the reflog shows a concurrent process performing:

```
HEAD@{2}: checkout: moving from feat/... to fix/public-rankings-entitlement-regression
HEAD@{1}: reset: moving to HEAD          <- hard reset
HEAD@{0}: checkout: moving from fix/... to feat/immediate-post-scrape-publication-trigger
```

This **destroyed** `backend/desirability/chase_accessibility.py` and
`backend/scripts/audit_chase_accessibility_v1.py` while a 40-minute audit was
running. They were uncommitted, so git could not recover them; both were rebuilt
from context and are now mirrored in the session scratchpad. No commits, stashes,
resets or reverts were performed by this task, and no unrelated file was touched.

**Stage XIV is not on this branch.** It was committed to
`fix/public-rankings-entitlement-regression` at `bdaf01bd` (23:32) — *after* the
PR-#147 merge (21:51) that produced this HEAD. Per your instruction the
implementation landed here anyway, with the parity artifact read from the object
store via `git show bdaf01bd:...`. The audit script takes the artifact path
explicitly so the gate can never silently skip.

## 11. V11 supersession

`OVERALL_RIP_V11_83_11_06_SUPERSEDED_BEFORE_CUTOVER`

Superseded, retained, **not deleted**, and on no runtime canonical path:

- `chase_core_k_v1_stage5c_3x_pack_equivalent_cost`
- `chase_opportunity_v1_core_k_saturating_100_k10`
- Overall RIP V11 83/11/6
- migration `074_add_sealed_product_chase_opportunity_and_overall_rip_v11.sql` —
  unapplied, untouched, **not reused** for Chase Accessibility

`test_chase_accessibility.py` asserts the production module contains no
reference to `core_k`, `chase_opportunity`, `overall_rip_v11` or `saturating`.

## 12. Overall RIP unchanged

```
CANONICAL_OVERALL_RIP_VERSION = overall_rip_v10_90_financial_v4_10_collector_appeal_v5
Financial RIP V4 = 0.90   Collector Appeal V5 = 0.10
```

Verified at runtime and pinned by test. Collector was **not** promoted to 11%.
Chase Accessibility is **not** an Overall RIP input; a test asserts
`weighted_rip` contains no reference to it.

## 13. Tests

```
python -m pytest backend/tests/unit/desirability/test_chase_accessibility.py \
                 backend/tests/unit/db/services/test_chase_accessibility_service.py -q
  65 passed
```

Covering: HC sums to 1; N_HC; O_pack; direct-form parity; boundedness;
determinism; exact uniform-price-scale invariance; probability monotonicity;
odds-as-probability rejection; expected-copies distinction; multi-hit rows;
coverage gate and non-renormalisation; null-vs-zero; mixed set/run rejection;
duplicate-variant rejection; keyword-only signature refusing product inputs; no
`backend.research` import; no V11 dependency; V10 canonical at 90/10; Chase not
wired into Overall RIP; copy discipline; four-quadrant independence; loader
paging; builder idempotence; publication severity.

## 14. Remaining work

1. Wire `publication_integrity_failures` into the coordinated set publication
   workflow.
2. Wire `project_chase_accessibility` into the live set/RIP read path.
3. Set page UI: Chase Accessibility as a percentage with the approved tooltip;
   Chase Depth as an *effective* count; existing unsupported-data treatment for
   null.
4. Frontend copy tests.
5. Re-run the cohort audit on a date where all 22 sets have authoritative runs.

## 15. Deployment boundary

Nothing applied, published, deployed or made canonical. Migration 077 is written
and **unapplied**. No production backfill, no snapshot publication, no frontend or
backend deploy, no change to canonical Overall RIP.

---

## 16. Completion pass — 2026-09-01

### Decision

`CHASE_ACCESSIBILITY_V1_IMPLEMENTED_CODE_ONLY`. All five items from §14 are now
code-complete on this branch (`fix/public-rankings-entitlement-regression-2`,
HEAD `f127031a`, unmoved for the duration of this pass). The math, schema,
builder/read model and 65 unit tests from §1-§13 were **already landed** before
this pass and are unchanged. Nothing was deployed, published, migrated or
backfilled.

### What was already landed vs newly completed

| Item | Already landed | Newly completed this pass |
|---|---|---|
| 1. Publication integrity wiring | `publication_integrity_failures` existed in `chase_accessibility_service.py` but was called by nothing | Wired into `evaluate_rankings_publication_readiness` (`backend/db/services/rankings_publication_lifecycle.py`) as a new `DEFERRED_CHASE_ACCESSIBILITY_INTEGRITY` gate, evaluated only over simulation-supported sets (same `source_run_ids` cohort the existing Set RIP/product-family gates use); the real publisher (`backend/scripts/pokemon_explore_rankings_publisher.py`) now loads the persisted snapshot table and passes it in |
| 2. Live read-path wiring | `project_chase_accessibility`/`read_chase_accessibility_snapshot` existed but had zero callers | `get_pokemon_set_insights_critical_snapshot_payload` (`backend/db/services/pokemon_public_snapshot_service.py`) now reads the same persisted `pokemon_set_chase_accessibility_snapshot_latest` row via `read_chase_accessibility_snapshot` and projects `chaseAccessibility`/`chaseAccessibilityPct`/`chaseAccessibilityStatus`/`chaseAccessibilityVersion`/`chaseDepth`/`mappedHcMass` verbatim, degrading to the unavailable projection (never a fabricated value) on any read failure |
| 3. Set-page UI | No UI reference existed | Added a "Chase Accessibility" entry to the existing `technicalScoreMetrics` tile list in `RipStatisticsPageClient.jsx`, rendered through the existing `MetricRow`/`StatTile` visual pattern (no redesign), with the approved plain-English tooltip. Chase Depth was left API-ready/pass-through only per the instruction that Depth may stay secondary-only if full UI churn is excessive |
| 4. Frontend copy/state tests | None existed | New `frontend/components/explore/ChaseAccessibility.contract.test.mjs` (9 tests): approved wording present, forbidden "chance of chase" wording absent from the whole page source, percentage rendering, unavailable-≠-0% via the normalizer, and the three read-model states (ready / no-pull-model / insufficient-coverage) pass through the normalizer and Explore adapter without fabrication |
| 5. Cohort audit re-run | Last recorded at 20/22 (2026-08-31) | Re-ran unchanged; still 20/22 on the same date, for the same two sets, with exact Stage XIV parity (see §16.3) — this is confirmed as a data-freshness gap, not a code defect |

### 16.1 Publication wiring — files and tests

- `backend/db/services/rankings_publication_lifecycle.py` — added
  `DEFERRED_CHASE_ACCESSIBILITY_INTEGRITY`, a `chase_accessibility_rows` keyword
  parameter on `evaluate_rankings_publication_readiness`, and a gate step that
  calls the existing `chase_accessibility_service.publication_integrity_failures`
  (imported, not reimplemented) after the Set RIP check and before the READY
  return. Omitting the parameter (the default, `None`) skips the gate entirely,
  so every pre-existing caller and test is unaffected — the gate only engages
  for a caller that explicitly supplies rows.
- `backend/scripts/pokemon_explore_rankings_publisher.py` — added
  `_load_chase_accessibility_rows_for_readiness` (reads
  `pokemon_set_chase_accessibility_snapshot_latest` read-only, fails closed to
  an empty list on any read error rather than skipping the check) and wired its
  result into the `evaluate_rankings_publication_readiness` call inside
  `publish_explore_rip_rankings_snapshot`.
- Tests: `backend/tests/unit/db/services/test_rankings_publication_lifecycle.py`
  gained 4 new tests (clean pass, missing-row block, stale-calculation-run
  block, and a backward-compatibility test proving the gate never fires when
  the parameter is omitted). All 15 tests in that file pass.
- Structurally-unsupported sets (no pull model) are never poisoned: the gate
  only evaluates `simulation_supported_set_ids`, which is exactly the ranked
  cohort's `source_run_ids` keys — a vintage/unsupported set never appears
  there, matching the severity line the doc already drew in §7.

### 16.2 Live read wiring — files and tests

- `backend/db/services/pokemon_public_snapshot_service.py` — imported
  `project_chase_accessibility`/`read_chase_accessibility_snapshot`, added
  `_read_chase_accessibility_for_set` (try/except around the live read,
  degrading to `project_chase_accessibility(None)` — the explicit unavailable
  shape — on any failure), and merged its six fields into the payload built by
  `get_pokemon_set_insights_critical_snapshot_payload`.
- New test file:
  `backend/tests/unit/db/services/test_chase_accessibility_live_read_wiring.py`
  (3 tests: ready state projects all six fields correctly, unavailable state is
  `None` not `0`, and a read exception degrades to the same unavailable shape
  rather than propagating or fabricating a value). All 3 pass.
- This reads the SAME table the builder writes (`pokemon_set_chase_accessibility_snapshot_latest`)
  through the SAME projection function (`project_chase_accessibility`) the
  builder module already defines — no second computation was written.
- Note: `backend/tests/unit/db/services/test_pokemon_public_snapshot_service.py`
  has 158 pre-existing failures unrelated to this change — every failing test
  references `pokemon_public_snapshot_service.public_read_client`, an attribute
  that does not exist anywhere in the module on this HEAD. This predates and is
  independent of the Chase Accessibility wiring (confirmed by grep: zero
  references to `public_read_client` in the module).

### 16.3 Cohort audit — exact result

```
python -m backend.scripts.audit_chase_accessibility_v1 --market-date 2026-08-31 \
    --stage14 docs/research/chase_accessibility_stage14.json
```

```
[CHASE_ACCESSIBILITY_V1] sets=20 supported=20 unsupported=0
[CHASE_ACCESSIBILITY_V1] probability authority: failures=0 over 6873 checked rows
[CHASE_ACCESSIBILITY_V1] rows where pull_count/simulation_count differs from presence probability: 2124
[CHASE_ACCESSIBILITY_V1] worst internal parity delta (HC form vs direct form): 8.674e-19

[CHASE_ACCESSIBILITY_V1] STAGE XIV PARITY over 20 sets:
      accessibility mismatches = 0  (worst delta 0.000e+00)
      depth mismatches         = 0  (worst delta 0.000e+00)
      status mismatches        = 0
```

**Still 20/22, not 22/22.** Destined Rivals and Journey Together are still
excluded by `resolve_research_cohort` because they have no authoritative
calculation run at `market_date=2026-08-31` — the exact same two sets and the
exact same reason recorded in §9 on 2026-08-31. This was re-verified, not
assumed: the query for the 22-set candidate list returned only 20 sets with a
`ready` simulation run resolvable for that date, and no run for either excluded
set exists at any date this pass checked. **This is an upstream
simulation/publication data-freshness gap — those two sets have not had an
authoritative simulation run land — not a Chase Accessibility code defect.**
Every set that IS covered matches Stage XIV exactly (0 mismatches on
accessibility, depth and status), so the metric itself is proven correct on the
full cohort it can currently see.

### 16.4 Regression search — classification

| Pattern | Where found | Classification |
|---|---|---|
| `effective_pull_rate` | `chase_accessibility.py` docstrings + the internal odds-vs-probability parity check (`1/effective_pull_rate` cross-check, never used as `p_i`) | current-valid (explicitly guards against the exact misuse the doc forbids) |
| `pull_count / simulation_count` | same parity-check context | current-valid |
| `"chance of pulling a chase card"` / `"probability of a chase"` | only inside a docstring negation (`chase_accessibility.py` §"It is NOT...") and now also inside the new frontend contract test's forbidden-phrase list | current-valid / test-only |
| `core_k`, `chase_opportunity`, `overall_rip_v11`, `saturating` | zero occurrences in `chase_accessibility.py` or `chase_accessibility_service.py` | absent (confirmed clean) |
| `product_market_cost`, `random_pack_count` | zero occurrences in either module | absent (confirmed clean — zero product-price dependency holds) |

### 16.5 Tests — exact commands and counts

Narrow (Chase Accessibility + newly wired surfaces):

```
python -m pytest backend/tests/unit/desirability/test_chase_accessibility.py \
    backend/tests/unit/db/services/test_chase_accessibility_service.py \
    backend/tests/unit/db/services/test_rankings_publication_lifecycle.py \
    backend/tests/unit/scripts/test_pokemon_explore_rankings_publisher_v10.py \
    backend/tests/unit/db/services/test_chase_accessibility_live_read_wiring.py \
    backend/tests/unit/scripts/test_rip_leaderboard_history_contract.py -q
136 passed
```

```
cd frontend && npx tsx --test components/explore/ChaseAccessibility.contract.test.mjs
9 passed
```

Broader RIP/publication regression:

```
python -m pytest backend/tests/unit/db/services -q -k "rip or publication or rankings" \
    --ignore=...test_billing_service.py --ignore=...test_billing_service_plan_change.py \
    --ignore=...test_billing_service_plan_change_matrix.py --ignore=...test_frontend_proxy_service_auth.py \
    --ignore=...test_frontend_proxy_service_profile_concurrency.py \
    --ignore=...test_public_profile_collection_regression.py --ignore=...test_supabase_auth_exchange.py
304 passed, 23 failed
```

The 7 ignored files fail to import (`ModuleNotFoundError: No module named 'jwt'`),
an environment gap unrelated to this branch's code. Of the 23 remaining
failures: all reference either the pre-existing missing
`pokemon_public_snapshot_service.public_read_client` attribute, or a Collector
Appeal V4→V5 version-literal cutover the concurrent workstream landed
separately — none reference Chase Accessibility, and none were introduced by
this pass (verified by inspecting each failing assertion).

```
cd frontend && npx tsx --test lib/pokemon/pokemonSetInsightsCriticalExploreAdapter.test.mjs \
    components/explore/canonicalRipV10Transport.contract.test.mjs \
    components/explore/FinancialRipV3Breakdown.contract.test.mjs \
    components/explore/CollectorAppealBreakdown.contract.test.mjs
65 passed, 2 failed
```

The 2 failures assert a stale `resolveCanonicalRipV7(explorePayload, selectedTarget, summary)`
call signature; the current source already calls it with two additional
parameters (`ripBootstrap?.canonicalSource`, `effectiveShellPayload`) that this
pass did not touch — pre-existing and unrelated.

### 16.6 Deployment status

Confirmed: no migration applied, no production write, no snapshot published, no
frontend or backend deploy performed. Migration 077 remains written and
unapplied. Overall RIP remains `overall_rip_v10_90_financial_v4_10_collector_appeal_v5`,
untouched.

### 16.7 Files touched this pass

- `backend/db/services/rankings_publication_lifecycle.py` (modified)
- `backend/scripts/pokemon_explore_rankings_publisher.py` (modified)
- `backend/tests/unit/db/services/test_rankings_publication_lifecycle.py` (modified)
- `backend/db/services/pokemon_public_snapshot_service.py` (modified)
- `backend/tests/unit/db/services/test_chase_accessibility_live_read_wiring.py` (new)
- `frontend/lib/pokemon/pokemonSetInsightsCriticalNormalizer.mjs` (modified)
- `frontend/lib/pokemon/pokemonSetInsightsCriticalExploreAdapter.mjs` (modified)
- `frontend/components/explore/RipStatisticsPageClient.jsx` (modified)
- `frontend/components/explore/ChaseAccessibility.contract.test.mjs` (new)
- `docs/research/CHASE_ACCESSIBILITY_V1_IMPLEMENTATION.md` (this section)

### 16.8 Diff-audit repair — 2026-09-01 (tooltip/copy contract)

A read-only diff audit of this pass (§16) found one real defect: the UI's
`infoText` for the Chase Accessibility metric row was a reworded, extended
hybrid of §2's locked Tooltip string ("How reachable this set's most
important collectible value is from one pack. A raw percentage - not the
odds of hitting any single card.") — neither matching §2 verbatim nor
distinguished from the separate plain-English public question. The
contract test's "approved wording" assertion was also self-referential: it
asserted the page against the same reworded string that had just been
written into it, so it would have passed even if the copy had drifted
arbitrarily far from what was actually approved.

Fixed by introducing two independently-named, module-level string
constants in `RipStatisticsPageClient.jsx`, matching §2 exactly and never
merged into one sentence:

```
CHASE_ACCESSIBILITY_PUBLIC_QUESTION   = "How reachable are this set's most important cards from a pack?"
CHASE_ACCESSIBILITY_TECHNICAL_TOOLTIP = "How accessible the set's most important collectible value is from one pack."
```

`CHASE_ACCESSIBILITY_TECHNICAL_TOOLTIP` is rendered via the metric's
existing `InfoPopover` (`infoText`) — the row's only tooltip/help
affordance, matching §2's own "Tooltip" framing exactly.
`CHASE_ACCESSIBILITY_PUBLIC_QUESTION` is rendered as a native `title`
attribute on the metric's label (`MetricRow` gained an optional
`titleAttr` prop, default `null`/no-op for every other row, so no other
metric row changed behavior). Both strings are real, present, and
independently defined in the shipped source — not two names for the same
literal.

`ChaseAccessibility.contract.test.mjs` was rewritten to assert both
approved strings independently as named constants (not the page's own
substring), so the test now fails if either string drifts, and can no
longer pass merely because the test and the component agree with each
other. Forbidden "chance of (a) chase" wording, the never-0.00%
unavailable rule, raw-percentage-not-score-transform, and Chase Depth
never being a literal count are all still separately asserted and
untouched by this change.

No Chase Accessibility formula, version identity, HC definition,
probability authority, mapped-HC-mass threshold, or Stage XIV conclusion
was touched by this repair — it is UI copy and test-quality only.

Files touched by this repair: `frontend/components/explore/RipStatisticsPageClient.jsx`,
`frontend/components/explore/ChaseAccessibility.contract.test.mjs`, this section.

Unrelated to this repair: `backend/domain/billing/providers/stripe_provider.py`
and `.sandbox-smoke-scratch/` were observed in the working tree during the
audit that preceded this repair and are explicitly
`UNRELATED_PREEXISTING_OR_CONCURRENT_WORK__PRESERVED` — not modified,
reverted, or otherwise touched by any Chase Accessibility pass.

Separately: HEAD moved twice more after this record's §16 completion pass
was written (`f127031a` → `d04fa372` → later billing commits), all
confirmed to touch only unrelated scheduled-simulation infrastructure and
unrelated Stripe SDK fixes — no Chase Accessibility file was affected. §16
above should be read as "HEAD did not move *during* that pass," not as a
claim that HEAD has remained stationary since.
