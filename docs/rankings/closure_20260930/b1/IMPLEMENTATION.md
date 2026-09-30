# Bucket 1 implementation

Date: 2026-09-30  
Baseline commit: `e231a7dad56c42ad4418dc54cd135be5859fed06`  
Branch: `fix/rankings-public-access-b1-20260930`

Bucket 1 implements R01–R09 and R39 only.

## Public reads

- `GET /tcgs/pokemon/rankings/headlines?entity_type=set|era` reads the active published benchmark, filters the database query to `metric_key=overall`, batches identity/artwork, and returns only identity, Overall score/rank/cohort/tier/status, publication identity, and safe benchmark metadata.
- `GET /tcgs/pokemon/rankings/pack-economics-preview` projects Set identity/artwork, product-family count, product count, average pack cost, and market date from the prepared opening-economics snapshot.
- `GET /tcgs/pokemon/rankings/product-catalogue` reads `sealed_products` directly, paginates beyond PostgREST's 1,000-row cap, joins Set/Era identity, classifies product family from product name, and sorts by case-folded product name plus ID. It does not read a ranking table.

The existing wide scorecards, detailed Pack Economics, Product Scores, and Product Economics routes remain gated and unchanged in their analytical payloads.

## UI behavior

- Era and Set RIP Score use the public headline contract for every access tier.
- Set Financial, Collector, and Chase lazy-load the paid scorecard contract only for entitled users.
- Pack Economics chooses the public preview for anonymous/base users and detailed paid contract for entitled users. Protected columns render ordinary `Locked` cells; the public average pack cost and counts remain visible.
- Products always loads the independent catalogue. Anonymous/base Scores and Economics show the same alphabetical catalogue with ordinary locked metric cells. Family controls and search operate on catalogue rows. Paid users continue to receive the existing ranked/economics contracts.
- Entitlement loss clears paid Product state and paid Set state. The identity-scoped cache also changes synchronously with auth identity; public rows remain sourced from public contracts.

No scoring logic, migrations, publications, production data, memberships, deployment configuration, or Buckets 2–7 were changed.

