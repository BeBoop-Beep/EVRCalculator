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
