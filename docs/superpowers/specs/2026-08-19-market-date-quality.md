# Market Date Quality — Frozen Spec

Source: operator contract issued 2026-08-19. Frozen. The plan implements this
verbatim; any deviation is a plan bug.

## Production context

- Aug 19 full scraper batch: 164 succeeded / 3 failed / 3 missing = `incomplete`.
- The 3 failures are legacy deterministic identity conflicts: `base`,
  `exTrainerKit2Plusle`, `exTrainerKitLatios`. They are NOT in the Market cohort.
- Canonical Market cohort Aug 19: 22 / 22 READY. All nine previously stranded
  Market sets completed successful exact-date reconciliation for 2026-08-19.
- The public snapshot builder is blocked by the old full-batch gate:
  `batch 2026-08-19 status=incomplete missing_sets=3` /
  `publication gate CLOSED [blocked_incomplete]`.

## Hard prohibitions

- DO NOT use `--force-publish`.
- DO NOT weaken the full 167-set publication gate globally.
- DO NOT alter the three legacy identity-conflict rows.
- DO NOT rerun scrapes.
- DO NOT run simulations.
- DO NOT mutate production.

## Market quality contract

The Market surface has its own quality authority.

Canonical Market cohort — same eligibility used by Market/index:
- `supports_opening_simulation = true`
- public analytics eligible
- `release_date <= market_date`

READY for date D requires EVERY Market cohort set to have a qualifying
successful exact-date reconciliation run:

- exact set
- exact `market_date`
- `job_name = pokemon_set_scrape`
- `source_system = tcgplayer`
- `job_type = price_scrape`
- `entity_type = set`
- `status = success`
- `items_succeeded >= 1`
- `items_failed = 0`
- `sourceCoverageRatio = 1`
- `acceptedVariantGroups > 0`
- `positiveNmObservationCount >= acceptedVariantGroups`

And Market valuation inputs for `standard`/`top10` must exist for that same
date/cohort.

Statuses: `READY`, `INCOMPLETE`, `DEGRADED`, `LEGACY_VERIFIED`.

- Aug 18 must remain DEGRADED.
- Aug 19 should evaluate READY from current production evidence.

## Blocker 1 — quality filter must precede chain math

The prior implementation filtered persisted index history AFTER chain-link
calculation. That is wrong. A DEGRADED date must never participate in
chain-link mathematics.

Required: determine eligible quality dates FIRST, then perform chain-link
calculation only across accepted dates.

Aug 17 READY / Aug 18 DEGRADED / Aug 19 READY must produce the transition
Aug 17 -> Aug 19. Aug 18 must have zero influence on Aug 19 index levels.
Add regression proving this mathematically.

## Blocker 2 — quality history read must paginate

The prior quality-history read was unpaginated. Implement bounded pagination.
Do not assume Supabase/PostgREST returns the entire table in one request.
Add regression/source assertion proving pagination.

## Blocker 3 — run resolution must not require queue link only

The prior evaluator loaded successful runs only through `queue_job_id`-linked
jobs. Historical/valid run evidence may include a qualifying run where
`queue_job_id` is NULL but exact set authority exists in the run's explicit
metadata/set identity.

Preferred authority order:
1. `queue_job_id` -> `scrape_jobs.set_id` when present
2. otherwise explicit trusted run set identity / metadata field already emitted
   by canonical scraper telemetry

Do NOT infer set identity from names or fuzzy matching. Wrong set/date/job
family must never satisfy readiness.

Tests required for: queue-linked qualifying run; qualifying run with null
`queue_job_id` but explicit exact set identity; wrong set; wrong date; wrong
source/job family; malformed/missing metrics.

## Blocker 4 — publication integration

Test the ACTUAL Market publication commands/entry points, not only isolated
service helpers. The Market surface must NOT be held hostage by unrelated
failures in the full 167-set scrape cohort.

### READY

- Market index history for D may write.
- Market set dashboard artifacts for D may write.
- Global Market Set Value for D may write.
- Market card-mover/history artifacts for D may write when part of the Market surface.
- Market-facing latest/public snapshot authority may advance to D.
- True even if the full 167-set batch is `incomplete` due to failures outside
  the canonical Market cohort.

Required regression: full batch 164/167 with 3 unrelated deterministic
failures; Market cohort 22/22 qualifying; quality READY; expected Market
publication ALLOWED. Do NOT use the global 167-set batch as an additional
requirement after Market quality has independently proven READY.

### INCOMPLETE

The current/recoverable Market date has not yet satisfied the full contract.

- HARD BLOCK publication.
- ZERO Market artifact/index/latest-snapshot upserts.
- Preserve previous good public Market authority.
- Do not partially publish the date. Do not chain through the date.
- Return the normal dedicated deferred/blocked publication result rather than
  pretending success. Exit code 3 is appropriate for a deferred commit-mode
  publication.
- The Market Date Quality row itself MAY be persisted/updated as INCOMPLETE for
  durable diagnostic state. That quality-state write is NOT Market artifact
  publication.
- Dry-run may evaluate/report INCOMPLETE read-only but must not write artifacts.

### DEGRADED

DEGRADED is a terminal bad Market date. It is NOT "publishable but excluded
from chain math."

- HARD BLOCK Market artifact publication for that date.
- ZERO new Market artifact/index/latest-snapshot upserts for that date.
- Preserve the prior good Market public authority.
- Never promote a DEGRADED date as latest.
- Never use a DEGRADED date as an input to later chain-link calculations.
- Existing historical rows produced before this contract are NOT deleted; Aug 18
  incident rows may remain in storage as evidence/audit history.
- Quality filtering happens BEFORE chain math: accepted Aug 17, Aug 19;
  excluded Aug 18. Therefore Aug 17 -> Aug 19, Aug 18 contributes zero
  mathematical influence.
- The quality row SHOULD be persisted as DEGRADED so the exclusion is durable
  and explainable. Do not rewrite/delete Aug 18 source evidence to make history
  look clean.

### LEGACY_VERIFIED

Exists ONLY for historical dates before enforcement of the new contract where
modern exact-run telemetry cannot be fully reconstructed. It must NOT be an
automatic fallback whenever run evidence is missing.

Grant only through an explicit historical verification path:
- a frozen pre-enforcement cutoff, AND
- explicit backfill/allowlist/review logic, AND
- required historical Market valuation/cohort evidence passes legacy rules.

A current/post-enforcement date can NEVER become LEGACY_VERIFIED merely because
its telemetry is incomplete.

- For chain history: accepted, may participate in chain-link math.
- For historical backfill: LEGACY_VERIFIED index rows may be written.
- For current public authority: prefer the latest READY post-enforcement date.
- Do not use LEGACY_VERIFIED to bypass a current INCOMPLETE or DEGRADED date.

Current incident expectation:
- Aug 17 -> READY or LEGACY_VERIFIED depending on the chosen enforcement cutoff
- Aug 18 -> DEGRADED
- Aug 19 -> READY

Either classification for Aug 17 is acceptable only if it follows the explicit
cutoff rule consistently.

### `--force-publish`

Market Date Quality must NOT be bypassable with the existing global
`--force-publish`. Do not honor it as an override of INCOMPLETE, DEGRADED, or
missing Market quality evidence.

Preferred behavior: a Market-specific quality-gated command receiving
`--force-publish` explicitly rejects it, e.g.
`"Market Date Quality cannot be overridden with --force-publish"`, rather than
silently ignoring the flag. The existing global `--force-publish` may remain for
unrelated legacy publication paths.

### Required integration tests

1. READY + full batch complete -> Market writes allowed.
2. READY + full batch incomplete because only non-Market sets failed -> allowed.
3. INCOMPLETE -> zero Market artifact upserts; previous authority unchanged;
   deferred/blocked result.
4. DEGRADED -> zero upserts; previous authority unchanged; deferred/blocked.
5. DEGRADED historical rows already exist -> rows remain stored; no deletion;
   date excluded before chain-link math.
6. Aug 17 accepted + Aug 18 DEGRADED + Aug 19 READY -> Aug 19 chain uses Aug 17
   directly; prove numerically that changing Aug 18 values does not alter the
   Aug 19 index result.
7. LEGACY_VERIFIED pre-enforcement historical date -> accepted for chain/backfill.
8. Missing modern run evidence on a post-enforcement date -> NOT automatically
   LEGACY_VERIFIED; remains INCOMPLETE/DEGRADED per contract.
9. `--force-publish` on INCOMPLETE or DEGRADED -> does NOT publish; preferably
   explicit rejection.
10. No Market-specific change weakens the general publication authority for
    RIP/rankings/set-page/non-Market surfaces.

## Public latest authority

Normal Market "latest" reads must select the latest accepted public Market date;
current production expected to resolve to `2026-08-19` READY. Aug 18 must never
win a latest-public selection after being classified DEGRADED. The existence of
a stored Aug 18 index/source row does not make it public authority.

## Current expected state

- Full scraper batch Aug 19: 164/167 INCOMPLETE
- Market cohort Aug 19: 22/22 READY
- Therefore Market publication Aug 19 = ALLOWED; general full-public publication
  may remain BLOCKED. This separation is intentional.
