# FMA-0 report — Explorer Focused Market Activity V1 contracts and evidence readiness

Terminal state: **FMA0_CONTRACT_READY**. The executable rules, schemas,
fixtures and handoffs are committed on branch `fma0-explorer-focused-activity`.

This bucket did not touch frontend components, canonical pricing, Set Value,
the Market Index, RIP, Collector Appeal, Fair Value, population sourcing,
condition conversion or the main Market tab. It made no provider calls, used
no provider credits, and made no cron, credential or watermark change.

## Baselines

| | SHA |
|---|---|
| Reviewed baseline (spec) | `8f73f234620e4a89d0aa72afc0b24d34fde2edbc` (merge of PR #477) |
| Actual starting SHA (`origin/develop`) | `b5c4f5da3122d8717d9efec1472d2c5677704135` (merge of PR #482) |

`git log 8f73f234..HEAD` on the READ FIRST paths shows only
`c00de345`, `6847f16a` and `190563e4`. These are the detached-source VM
installer changes (`infra/oracle/*`) and one Bucket C test. None of the READ
FIRST modules changed between the two SHAs.

## What was delivered

| Item | Path |
|---|---|
| Pure versioned domain | `backend/domain/pokemon/market_activity.py` |
| Schema-subset validator and canonical fingerprints | `backend/domain/pokemon/market_activity_contract.py` |
| Offline generator | `backend/scripts/build_market_activity_v1_contract_artifacts.py` |
| Contract | `docs/research/market_activity_v1/CONTRACT.md` |
| 8 JSON Schemas | `docs/research/market_activity_v1/contracts/` |
| 11 fixtures and manifest | `docs/research/market_activity_v1/fixtures/` |
| Handoffs | `SCHEMA_DECISION.md`, `COLLECTOR_HANDOFF.md` |
| Tests | `backend/tests/unit/domain/pokemon/test_market_activity.py`, `test_market_activity_contract.py` |

**Versions.**
- Contract: `market_activity_v1`
- Domain: `market_activity_domain_v1.0.0`
- Rule sets: identity `fma_exact_identity_v1`, grading
  `fma_grading_identity_v1`, qualifier registry `fma_qualifier_registry_v1`,
  window readiness `fma_window_readiness_v1`, supply
  `fma_supply_provenance_v1`, tie policy `midrank_v1`, membership
  `fma_membership_v1`, display policy `fma_display_policy_v1`
- Fixture set: `market_activity_v1_fixtures_1`
- Manifest canonical SHA-256:
  `04257b05059f86dabc5abd1a33484b780170ad05ae109730c0cb858a77709899`

## Tests

```
python -m pytest -q backend/tests/unit/domain/pokemon/test_market_activity.py \
    backend/tests/unit/domain/pokemon/test_market_activity_contract.py
# Python 3.8.10: 90 passed
py -3.11 -m pytest -q <same two files>
# Python 3.11:   90 passed
python -m backend.scripts.build_market_activity_v1_contract_artifacts --check
# {"drift": []}
```

**Adjacent suites.** The Bucket B, B2 and C script tests and the rest of
`backend/tests/unit/domain/pokemon` all pass, with one exception:
`test_prepared_constituent_summary.py::test_no_historical_observation_leaks_into_the_summary`.
That test does not import any FMA code. It fails because it builds a Supabase
client and needs `SUPABASE_URL`/`SUPABASE_SERVICE_ROLE_KEY`, which this
environment lacks. It is an environmental failure, not a regression.

**Acceptance coverage** (each item maps to named tests):
- attribution: exact, unknown, shared and missing;
- internal ambiguity, no-match and unparsed tokens;
- first edition, unlimited, shadowless, reverse holo and Non-Holo labels;
- incomplete grading, string grades, and unknown qualifiers;
- duplicate and conflicting evidence;
- raw-only versus combined versus grade-filtered stream proof;
- a partially fetched boundary date;
- an open, stale or unreconciled right edge, and late ingestion;
- zero versus missing counts;
- null, future, mixed and repeated source confirmations;
- unknown versus free shipping, and unproven or defaulted quantity;
- thin, all-zero, tied and empty peer groups, and midrank versus strict-below;
- unsupported sealed or graded assets and mismatched generations;
- checkpoint same-timestamp drainage;
- the provider-egress tripwire, which has three parts:
  - an autouse socket patch;
  - a fresh-interpreter import-and-render probe asserting that no client
    modules (`requests`, `psycopg2`, `supabase`, `httpx`, `urllib.request`,
    `backend.db`, `backend.pricing_pipeline`, and others) are loaded;
  - an AST standard-library-only import allowlist.

## Audits

1. **One-candidate EXACT shortcut.**
   - *Mechanism.* In the legacy `resolve_internal_variant` with Bucket B's
     target-only candidate list, `None` or `"Holofoil"` resolves as EXACT.
     This is confirmed by tests.
   - *Impact.* The DB check found 3 of the 3,003 exact USD rows affected:
     "Holofoil" resolved to an Unlimited variant that has a 1st Edition
     sibling. It also found 185 null-variant rows that resolved EXACT; those
     have attribution unknown, so they were already excluded. The other 3,000
     rows are sound under the full-sibling rule.
   - *Action.* No row was rewritten.
2. **Holo-before-Non-Holo.**
   - *Mechanism.* The legacy parser reads "Non-Holo" and "Non Holo" as holo.
     This is confirmed by tests.
   - *Impact.* The DB has **no** stored Non-Holo or Normal labels, so there is
     no evidence that any stored row is wrong.
   - *Action.* The strict parser in the domain fixes the order.
3. **Custom-cache publication atomicity.** The query cache and its constituent
   detail table are replaced in place for each fingerprint, and the page RPC
   has no revision parameter. A fingerprint is a specification, not a
   revision, and it is rejected. `SCHEMA_DECISION.md` specifies a
   publish-time, insert-only revision sidecar. The active adapter is V2
   `read_v2_constituents`, which is generation-pinned and safe.
4. **Supply normalizer defaults.** Missing shipping is stored as 0.00, and
   missing or zero quantity is stored as 1. Both are confirmed by tests. The
   domain classifies these stored rows as `LEGACY_UNVERIFIED` and never
   manufactures provenance.
5. **Watermarks.** The legacy incremental mode advances `CURRENT` and the
   watermark even when `has_more=true`. Details are in
   `COLLECTOR_HANDOFF.md` §2. Nothing was changed.

## Database inspection

This used the connected Supabase project (read-only, sequential, with
`statement_timeout=5s`). It ran aggregates and `information_schema` queries
only, and no broad price-history reads.

| Prior-audit claim | Recheck |
|---|---|
| 5,877 stored sales across 22 canonical cards | **5,877 / 22** confirmed |
| 3,003 exact-attribution + exact-variant USD (1,476 raw / 1,527 graded) | **3,003 (1,476 / 1,527)** confirmed; 3 fail V1's full-sibling edition rule |
| 8 graded records missing grader or grade | **8** (all missing grader; 0 missing grade) |
| 190 offers across 10 variants, all truncated | **190 / 10 / 10 truncated** |
| 4 variants with both exact USD sales and supply | **4** (15 exact-sale variants, 10 supply variants) |
| Supply confirmations Sept 23–24 despite Sept 29 collection | **2026-09-23 20:12Z – 2026-09-24 02:06Z** confirmations vs 2026-09-29 22:08Z collection |
| (additional) sync states | 22 (13 CURRENT, of which 12 are legacy raw-only with no stream label; 9 PARTIAL) |
| (additional) supply runs | 1 (10-target smoke); **no 207-target daily run** |

These counts are recorded evidence, not product data. They are not hardcoded
anywhere, and exact-identity counts do not by themselves make evidence
eligible for publication.

## Unavailable environment checks

- `gh` is not installed in this environment, so `gh pr view 477` and
  `gh issue view 480` could not run. PR #477 is understood from repo state
  (merge `8f73f234`, C2 report: `BUCKET_C2_BLOCKED` on VM host-key
  verification). The DB shows no full-panel run, so the merge is **not**
  runtime-activated. Issue #480's text was not readable; its scope is taken
  from the spec.
- No worktree `.env`; no local Postgres. DB checks used only the read-only
  connector.
- No SSH or VM access was attempted.

## Remaining collection and data limitations

- No auditable walk or right-edge receipts exist yet, so no live window can
  be `PROVEN` today.
- Every current ask snapshot is `STALE` under the 24-hour policy. Depth is
  always a lower bound.
- Shipping and quantity provenance are unknowable for the 190 stored offers.
- Legacy raw-only `CURRENT` states cannot prove graded tiers.
- Peer badges need at least 30 proven peers per tier and window. The current
  proven population is 0.
- The frozen research panel is modern (Scarlet and Violet plus Mega
  Evolution) and price-balanced. It supports no "all Pokemon" claim.

## Next buckets

- **FMA-1:** implement `SCHEMA_DECISION.md`, meaning the tables, the builder,
  the three read endpoints, and a serializer that reproduces every fixture.
- **FMA-3:** build the frontend against the committed fixtures only.
- **Collector workstream (#480 and successors):** adopt the receipts and the
  identity and provenance fixes listed in `COLLECTOR_HANDOFF.md`.
