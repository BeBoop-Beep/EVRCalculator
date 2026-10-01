# Treatment Panel Recovery V3 — Expanded Modern Evidence

Status: `EXPANSION_FROZEN_PRECOLLECTION`

## Purpose

Treatment Hierarchy V2 successfully repaired the historical-panel blocker and produced a temporally stable estimator, but every Set/family failed support because the pilot intentionally contained only two matched identities per Set/family. Bootstrap sign stability stayed below 0.80 and leave-one-identity influence was far above the frozen 0.50-log-point limit.

V3 changes **only evidence depth**. It does not relax or retune any estimator gate.

## Frozen expansion

The exact same eight Set/family experiments are retained. The frozen Round-23 matched-ladder universe contains 5–37 candidate identities per group.

Selection is deterministic and price-blind:

1. filter to one of the eight V2 Set/family groups;
2. sort candidate ladder identity keys lexicographically;
3. take the first five identities in each group.

Result: 40 identity-group entries and 92 unique canonical cards.

## Provider contract

Unchanged from V2:

- PkmnPrices TCGPlayer price history
- exact Near Mint
- exact provider printing variant
- 180-day horizon
- daily `avg`
- no interpolation / forward fill / nearest-date substitution
- read-only database access
- local artifacts only

Hard provider cap: 18,000 credits. Maximum history-row exposure is 16,560 before bounded identity/card verification overhead.

## Safety

Collection must hold `/tmp/pkmnprices-api.lock` and defer if the live B5 collector owns the provider. No canonical price, Collector Appeal, Overall RIP, Rankings, or Set-page mutation is authorized.

## Next decision

If the expanded panel is recovered cleanly, freeze Treatment Hierarchy V3 before fitting. V3 must reuse the V2 estimator design and numerical support gates unchanged; the only intended experimental change is more matched identities per Set/family.
