# FMA-5 release handoff

Date: 2026-09-30 (America/Phoenix)

Final gate: **FMA5_BLOCKED**

Release state: **RELEASE_CODE_READY_BUT_DEPLOYMENT_REQUIRED**. The bounded
Prismatic Evolutions Activity generation is live in database serving authority,
but the production Render backend and Vercel frontend do not contain the merged
FMA stack. No backend or frontend deployment was performed.

## Repository and deployment identity

- Starting `origin/develop`: `61f364d2c6aba321ca77a3f21e977cc6cf5b20a9`
- FMA-2 merge `8d7a6093` is an ancestor of `origin/develop`.
- FMA-4 merge `3f0a4897` is an ancestor of `origin/develop`.
- Required migrations are present in both `backend/db/migrations` and
  `supabase/migrations`:
  - `20260930210000_market_activity_projection_v1.sql`
  - `20260930220000_market_activity_per_market_serving_v1.sql`
- Live Supabase migration history contains the corresponding applied migrations
  (`20260930161143 market_activity_projection_v1` and
  `20260930161145 market_activity_per_market_serving_v1`). The live tables and
  bounded reader/promotion functions exist and match the per-market serving
  model.
- Render production backend: `1320c62c034c89483a9f2b0697f615aa270314f4`,
  deployment `dep-dasogsl9fdbs73ec69t0`, live at
  `https://evrcalculator.onrender.com`. It does **not** contain FMA-2/FMA-4.
- Vercel production frontend: `f6020a88bae15f403f753b1592fb8d11404fe448`,
  deployment `dpl_BHYrPwf59gU4y8ATTPJKne2hm9Tf`, aliased to
  `https://www.inthedex.io`. It does **not** contain FMA-2/FMA-4.
- Backend deploy SHA required: `61f364d2c6aba321ca77a3f21e977cc6cf5b20a9`
- Frontend deploy SHA required: `61f364d2c6aba321ca77a3f21e977cc6cf5b20a9`

## Live database release receipt

- Supabase project: `zwxzxuuawalvwioadhmf`
- Explorer surface generation:
  `81400ef7-dcdb-4eda-923d-381c84f5b936`
- Explorer market date/state: `2026-09-29`, `VALIDATED`
- Activity generation:
  `f5a50000-0002-4a29-8c01-202609300002`
- Market key: `set:7a3dd188-4375-41af-94de-c5247fe0b1a6`
- Roster ref: `SURFACE_V2_GENERATION` pinned to the Explorer generation above
- Roster: one `PREPARED_GENERATION` roster, denominator 174; 174 members, 174
  distinct variants, 174 payloads, and 696 instrument-window rows
- Group windows: 7, 30, 90, and 180 days
- Fixture manifest SHA-256:
  `e6235d9c73dc7ce6e38b81431bcfe60e4a32ae27f2780632aae45d407705e007`

Before promotion, no row existed in `market_activity_market_serving_v1` for the
Prismatic market and the target generation was `VALIDATED` / `RETAINED`.

Promotion called only:

```sql
select public.promote_market_activity_generation_v1(
  'f5a50000-0002-4a29-8c01-202609300002'::uuid
);
```

It returned `true` at `2026-09-30T17:25:31.441981Z`.

After promotion, the sole Activity serving row is:

```text
market_key                     set:7a3dd188-4375-41af-94de-c5247fe0b1a6
activity_generation_id         f5a50000-0002-4a29-8c01-202609300002
previous_activity_generation_id null
```

The generation is now `VALIDATED` / `SERVING`. The canonical Market Explorer
serving pointer remains `81400ef7-dcdb-4eda-923d-381c84f5b936`.

## Real reader and capability receipts

Pre-promotion retained-generation reads succeeded for the group, the first
25-member constituent page (ranks 1-25), and Umbreon instrument detail. An
unknown explicit generation returned no stored payload and is mapped by the
service layer to contract-valid `ACTIVITY_GENERATION_MISMATCH`. Provider calls:
zero.

Before publication, capability discovery was unavailable because no current
per-market Activity serving generation existed. After publication, local merged
backend code against the live database returned:

- `available = true`
- market key `set:7a3dd188-4375-41af-94de-c5247fe0b1a6`
- Activity generation `f5a50000-0002-4a29-8c01-202609300002`
- exact prepared roster ref pinned to
  `81400ef7-dcdb-4eda-923d-381c84f5b936`
- evidence fingerprint
  `d70d8432b7db8ac872307daeedd861205b80d846e7f293b52fd8091119838a90`
- `asOf = 2026-09-29`, `windowDays = 30`, `tier = RAW`
- a wrong roster generation returned unavailable with
  `ROSTER_REVISION_MISMATCH`

The API contract suite in the merged source establishes anonymous 401, Basic
403, Plus prepared access, Premium prepared/custom inheritance, bounded 400 and
500 mappings, and private/no-store responses. These could not be exercised at
the real production HTTP boundary because the deployed backend predates FMA.
The live data reads above used the merged backend service against the production
database, not the old deployed API.

## Exact Prismatic acceptance values

The real 30-day group payload reports:

- label: `Activity for current constituents`
- roster denominator: 174
- observed constituents: 19
- observed completed-sale records lower bound: 488
- proven constituents: 0
- proven sale count: not established (`null`)
- availability: `PARTIAL`
- reason: `WINDOW_NOT_PROVEN`

Interpretation: at least 488 observed completed-sale records occur among the
currently observed constituents in the selected window; completeness is not
established. This is neither 488 total market sales nor 488 proven sales.

Exact identity joins against the pinned Explorer surface were confirmed:

- Umbreon ex #161, Special Illustration Rare, raw holo exact variant
  `9874f528-8009-43af-bd45-74095b43410f`: 63 observed 30-day sales,
  proven count unavailable, median observed sold price $1,075, readiness
  `UNPROVEN`, asks `NOT_COLLECTED`.
- Eevee ex #167, Special Illustration Rare, raw holo exact variant
  `22b18882-1d65-40f8-bfa4-d6dabb5436ea`: 27 observed 30-day sales,
  median $140, readiness `UNPROVEN`, ask state `STALE`, offer qualification
  `NOT_CURRENT`, last captured item-only legacy-unverified lowest ask $70.
  The $70 value must be rendered only as stale/last-known, never as a current or
  live ask.

## Browser, lifecycle, observability, and performance acceptance

Live browser acceptance is pending deployment. Consequently there are no honest
production screenshots for 1440x900, 1366x768, or 390px in this handoff. Prior
fixture/integration screenshots remain under
`backend/artifacts/market_activity_v1/fma3` and
`backend/artifacts/market_activity_v1/fma4`; they are not represented as live
Prismatic evidence.

The merged frontend contract checks passed (4/4), covering bounded proxying,
conditional fixture language, exact-variant local joins, cursor paging, mobile
behavior, instrument detail only on open, discovery per active-set revision,
and group synchronization to the canonical chart range.

The following production acceptance items remain blocked until the two required
deployments are explicitly authorized:

- Plus/Premium end-to-end workflow and Basic 403 at the live API boundary
- logout, identity change, and plan-downgrade paid-cache clearing
- live 1440x900, 1366x768, and 390px screenshots
- browser request counts (expected: capability 1 per active-set revision, group
  1 on enable, constituents 1 per requested page, instrument 1 on explicit
  open, hover/keyboard 0)
- deployed log/error mapping for 401, 403, 400, 500, 503, proxy unavailable,
  `ACTIVITY_GENERATION_EXPIRED`, and `ROSTER_REVISION_MISMATCH`

Database-side request behavior is bounded: capability discovery uses a constant
set of projection-table calls, readers consume immutable precomputed payloads,
and no sold-ledger scan or provider call occurs at request time.

## Evidence limitations

Completeness receipts do not prove the sales windows. `provenSaleCount` must
remain null and observed counts must remain explicitly lower-bound/observed.
Ask freshness and qualification must be preserved exactly. Publication does not
make stale asks current and does not expand evidence coverage.

## Market-local rollback

The current receipt has no previous Activity generation. To withdraw only this
Prismatic Activity publication, use a privileged transaction with short
timeouts:

```sql
begin;
set local lock_timeout = '2s';
set local statement_timeout = '8s';

select market_key
from public.market_activity_market_serving_v1
where market_key = 'set:7a3dd188-4375-41af-94de-c5247fe0b1a6'
for update;

update public.market_activity_market_serving_v1
set activity_generation_id = null,
    previous_activity_generation_id = null,
    promoted_at = clock_timestamp()
where market_key = 'set:7a3dd188-4375-41af-94de-c5247fe0b1a6'
  and activity_generation_id =
      'f5a50000-0002-4a29-8c01-202609300002'::uuid;

update public.market_activity_generations_v1
set serving_state = 'RETAINED'
where activity_generation_id =
      'f5a50000-0002-4a29-8c01-202609300002'::uuid;

commit;
```

Verify the market row has no Activity generation and the target is retained.
This rollback is market-local and must not update
`pokemon_market_explorer_surface_serving_v2` or any canonical pricing authority.

FMA5_BLOCKED
