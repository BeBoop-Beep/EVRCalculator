# Overall RIP V13 deployment and promotion handoff

No scoring research is pending. The accepted formula is frozen at 0.86 Financial V4 +
0.04 Chase Accessibility V1 + 0.10 Collector Appeal V7.

## Current authority and staged authority

- Active V12 run: `0f83d958-95aa-40f1-bcfa-ec550ec3a379`
- Active V12 rankings generation: `723e7fb8-e671-45b6-9676-89ac3e7d58a2`
- Active V12 set-page generation: `42139262-fea1-4168-89b7-2470c048e675`
- Inactive V13 run: `5a49238e-19c7-4a50-ae35-1e19d8e1fb56`
- Inactive lifecycle status: `superseded` (valid rollback/promote target)
- Inactive V13 rankings generation: `37979f4a-d1ca-4280-8158-9932774758cb`
- Inactive V13 set-page generation: `f983f236-d8ab-44c0-92cf-c2402db760a0`
- V13 formula fingerprint: `9e0bbcb7aa37cde8b92556fd0f008a8c2a39484e7de3f868752ac5e3f3a73497`
- Cohort fingerprint: `1ec4b25ef658b9aab638faad15431859de0c36315481684773cb34a09e080ff3`
- Collector V7 run: `e282f26e-2136-4105-b0a3-f0974c4d9d70`

## Code that must ship before promotion

Deploy the two migration files, `backend/desirability/overall_versioned_publication.py`,
and `backend/db/services/overall_versioned_publication_service.py`. Update the existing
rankings/detail/set-page call sites named in `OVERALL_V13_VERSIONED_PUBLICATION_DEPENDENCY_MAP.md`
to obtain their stable Overall fields from `read_active_overall_rows`; preserve their
existing entitlement projection and standalone Collector V7 fields. This repository
change supplies the generic reader boundary, but the currently running application has
not deployed it, so promotion is prohibited now.

Both migrations are already applied to production as additive, service-role-only,
inert architecture. They do not alter legacy V12 columns, current legacy snapshot
pointers, or history.

## Deployment smoke tests

1. Confirm the current generic pointer and legacy endpoints both read V12.
2. Confirm 276 active generic rows and no mixed publication/generation IDs.
3. Exercise rankings, set pages, sealed-product detail, homepage context, Explore, and
   entitlement tiers; compare stable public fields with predeployment V12 responses.
4. Confirm anon/authenticated cannot read ledger tables or execute the promotion RPC.
5. Confirm the V13 run and both V13 generations remain inactive (`superseded`) until approval.

## Controlled promotion and rollback

Execute only with the service role after smoke-test approval:

```sql
select public.promote_pokemon_overall_rip_publication(
  '5a49238e-19c7-4a50-ae35-1e19d8e1fb56'::uuid
);
```

Rollback requires no recomputation:

```sql
select public.promote_pokemon_overall_rip_publication(
  '0f83d958-95aa-40f1-bcfa-ec550ec3a379'::uuid
);
```

The RPC locks and switches the publication run, rankings generation, and set-page
generation together. It validates status, validation evidence, and publication row
count first. A production subtransaction rehearsal promoted V13, promoted V12, and
intentionally rolled the entire rehearsal back; final readback remained V12 with one
published run.

During final privilege verification, the database connector supplied service-role
authority despite the SQL session's earlier `auth.role()` readback being null. The
probe therefore performed one unintended committed V13 promotion. Immediate readback
detected it and the sanctioned RPC restored V12. Final state is V12 published with
both V12 generations published; V13 and both V13 generations are superseded/inactive.
No legacy V12 row, legacy snapshot pointer, or history row was overwritten.

## Expected post-promotion readback

- Pointer model version: `overall_rip_v13_86_financial_v4_04_chase_accessibility_v1_10_collector_appeal_v7`
- Pointer IDs: the three inactive V13 IDs above
- Rows: 276; rankings generation rows: 276; set-page generation rows: 210
- Persisted V13/V12 comparison: mean delta `-0.2783666666666667`, median `-0.6181`,
  rank correlation `0.982844422882094`, Top-10 overlap `9`, tier movements `29`
- V12 becomes `superseded` and remains an immutable rollback target.
- V13 history starts at actual activation; do not backcast it.

No research rerun or V14 schema migration is needed. Future models create new run,
row, and generation records under the same contract.
